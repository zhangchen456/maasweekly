"""Exercise retention and deletion against real disposable package trees."""
from contextlib import redirect_stdout
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_cleanup', BASE / 'ops/runtime-cleanup.py')
cleanup = importlib.util.module_from_spec(spec); spec.loader.exec_module(cleanup)


class RuntimeCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ['runtime', 'incoming', 'shared/state', 'shared/slots', 'shared/public-data/v1', 'locks']:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.sentinel = self.root / 'shared/public-data/v1/business.json'; self.sentinel.write_text('retain business data')
        self.paths = {n: self.package(n) for n in range(1, 9)}
        for name, n in [('runtime.json', 1), ('runtime-previous.json', 2), ('runtime-candidate.json', 1)]:
            (self.root / 'shared' / name).write_text(json.dumps({'code': self.code(n)}))
        (self.root / 'current').symlink_to(self.paths[1])

    def code(self, n): return f'{n:040x}'

    def package(self, n):
        path = self.root / 'runtime' / self.code(n); path.mkdir()
        files = []
        for name, text in [('site/dist/server/entry.mjs', f'code-{n}'), ('tooling/code-commit', self.code(n))]:
            p = path / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
            files.append({'path': name, 'bytes': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        (path / 'metadata').mkdir()
        p = path / cleanup.MANIFEST
        p.write_text(json.dumps({'format': 'maas-runtime-candidate-v1', 'codeCommit': self.code(n),
                                 'pageFormatVersion': 1, 'dataIncluded': False, 'files': files}))
        os.utime(p, (n, n))
        (path / 'data/public').mkdir(parents=True)
        (path / 'data/public/v1').symlink_to(self.root / 'shared/public-data/v1')
        return path

    def upload(self, n, young=False):
        # Use distinguishable commit prefixes for real upload IDs in this test.
        path = self.root / 'incoming' / f'rl_{n:010x}_000000000000'
        code = f'{n:010x}' + 'a' * 30
        source = self.root / 'runtime' / code
        shutil.copytree(self.paths[n], source, symlinks=True)
        m = json.loads((source / cleanup.MANIFEST).read_text()); m['codeCommit'] = code
        # The code-commit file remains declared fixture content; identity comes from manifest.
        (source / cleanup.MANIFEST).write_text(json.dumps(m)); os.utime(source / cleanup.MANIFEST, (n, n))
        shutil.copytree(source, path, symlinks=True, ignore=shutil.ignore_patterns('data'))
        stamp = 9900 if young else 1
        os.utime(path / cleanup.MANIFEST, (stamp, stamp)); os.utime(path, (stamp, stamp))
        return path, source

    def run_apply(self, now=10000):
        public, packages, uploads = cleanup.plan(self.root, now)
        result = cleanup.apply(self.root, public, packages, uploads)
        self.assertEqual(self.sentinel.read_text(), 'retain business data')
        return result

    def test_union_of_old_current_rollback_and_latest_three_is_retained(self):
        plan, _, _ = cleanup.plan(self.root, 10000)
        self.assertEqual(set(plan['protected']), {self.code(n) for n in [1, 2, 6, 7, 8]})
        self.assertEqual(plan['removeRuntime'], [self.code(n) for n in [3, 4, 5]])
        self.assertTrue(all(p.exists() for p in self.paths.values()), 'plan must not delete')
        self.run_apply()
        self.assertEqual({p.name for p in (self.root / 'runtime').iterdir()}, set(plan['protected']))
        self.assertEqual(self.run_apply()['removed'], [], 'repeat is idempotent')

    def test_slot_and_candidate_are_protected_and_pending_switch_blocks(self):
        (self.root / 'shared/runtime-candidate.json').write_text(json.dumps({'code': self.code(3)}))
        (self.root / 'shared/slots/green.env').write_text('MAAS_RELEASE_DIR=' + str(self.paths[4]) + '\n')
        plan, _, _ = cleanup.plan(self.root, 10000)
        self.assertNotIn(self.code(3), plan['removeRuntime']); self.assertNotIn(self.code(4), plan['removeRuntime'])
        (self.root / 'shared/runtime-switch-pending.json').write_text('{}')
        with self.assertRaises(ValueError): cleanup.plan(self.root, 10000)
        self.assertTrue(all(p.exists() for p in self.paths.values()))

    def test_broken_rollback_or_pointer_prevents_all_deletions(self):
        file = self.paths[2] / 'site/dist/server/entry.mjs'; file.write_text('changed')
        with self.assertRaises(ValueError): self.run_apply()
        self.assertTrue(all(p.exists() for p in self.paths.values()))
        (self.root / 'current').unlink(); (self.root / 'current').symlink_to(self.paths[3])
        with self.assertRaises(ValueError): cleanup.plan(self.root, 10000)

    def test_modified_historical_package_and_unmanaged_files_survive(self):
        (self.paths[3] / 'customer.txt').write_text('untracked work')
        (self.paths[4] / 'site/dist/server/entry.mjs').write_text('uncommitted modification')
        result = self.run_apply()
        self.assertEqual(result['status'], 'completed_with_skips')
        self.assertTrue(self.paths[3].exists()); self.assertTrue(self.paths[4].exists()); self.assertFalse(self.paths[5].exists())
        self.assertEqual(len(result['skipped']), 2)

    def test_installed_upload_removed_before_its_old_runtime(self):
        upload, runtime = self.upload(3)
        result = self.run_apply()
        self.assertFalse(upload.exists()); self.assertFalse(runtime.exists())
        self.assertLess(result['removed'].index(str(upload)), result['removed'].index(str(runtime)))
        self.assertTrue(list((self.root / 'shared/runtime-cleanup').glob('*.jsonl')))

    def test_young_upload_temporarily_protects_counterpart_then_expires(self):
        upload, runtime = self.upload(3, young=True)
        plan, _, _ = cleanup.plan(self.root, 10000)
        self.assertIn(runtime.name, plan['protected']); self.assertNotIn(upload.name, plan['removeUploads'])
        self.run_apply(10000); self.assertTrue(runtime.exists()); self.assertTrue(upload.exists())
        self.run_apply(20000); self.assertFalse(runtime.exists()); self.assertFalse(upload.exists())

    def test_unknown_and_symlink_paths_are_not_followed(self):
        alias = self.root / 'runtime' / self.code(9); alias.symlink_to(self.root / 'shared')
        unknown = self.root / 'runtime/build-tools'; unknown.mkdir(); (unknown / 'keep').write_text('tooling')
        self.run_apply()
        self.assertTrue(alias.is_symlink()); self.assertTrue((unknown / 'keep').exists())
        (self.root / 'shared/runtime-previous.json').unlink()
        with self.assertRaises(ValueError): cleanup.plan(self.root, 10000)

    def test_runtime_in_use_by_background_process_is_retained(self):
        proc = self.root / 'proc'; proc.mkdir()
        for pid, target in [('101', self.paths[3] / 'site'), ('102', self.root / 'shared'),
                            ('103', self.root / 'runtime' / self.code(99))]:
            (proc / pid).mkdir(); (proc / pid / 'cwd').symlink_to(target)
        (proc / '104').mkdir()  # A process exiting while /proc is scanned.
        live = cleanup.active_process_codes(self.root, proc)
        self.assertEqual(live, {self.code(3)})
        public, packages, uploads = cleanup.plan(self.root, 10000, live_codes=live)
        cleanup.apply(self.root, public, packages, uploads)
        self.assertTrue(self.paths[3].exists()); self.assertFalse(self.paths[4].exists())

    def test_tree_changed_after_verification_is_not_deleted(self):
        original = cleanup.verify
        def changed(package, root, **kwargs):
            result = original(package, root, **kwargs)
            if package['path'] == self.paths[3]: (package['path'] / 'late-work.txt').write_text('new work')
            return result
        with patch.object(cleanup, 'verify', side_effect=changed), self.assertRaises(ValueError): self.run_apply()
        self.assertTrue((self.paths[3] / 'late-work.txt').exists())
        self.assertTrue(all(p.exists() for p in self.paths.values()))

    def test_busy_release_lock_defers_without_applying(self):
        with (self.root / 'locks/release.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            output = io.StringIO()
            with patch.object(cleanup, 'ROOT', self.root), patch.object(cleanup.os, 'geteuid', return_value=0), \
                    patch('sys.argv', ['cleanup', '--apply']), patch.object(cleanup, 'apply') as apply, redirect_stdout(output):
                cleanup.main()
            apply.assert_not_called(); self.assertEqual(json.loads(output.getvalue())['status'], 'deferred')


if __name__ == '__main__': unittest.main()
