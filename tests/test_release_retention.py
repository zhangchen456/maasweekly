"""Exercise the production cleanup implementation in a disposable release tree."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'ops/server/maasweekly-activate'
CODE = HELPER.read_text().split('retention_cleanup() {')[1].split("<<'PYEOF'\n")[1].split('\nPYEOF')[0]


class ReleaseRetentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'releases').mkdir()
        self.current = self.release(1, 1, age=12, refs=[1, 3])
        self.previous = self.release(2, 2, age=12, refs=[2])
        (self.root / 'current').symlink_to(self.current)
        (self.root / 'previous').symlink_to(self.previous)

    def release(self, n, ds, age, refs=()):
        path = self.root / 'releases' / f'rl_{n:010x}_{ds:012x}'
        public = path / 'data/public/v1'
        public.mkdir(parents=True)
        (public / 'manifest.json').write_text(json.dumps({
            'datasetVersion': f'ds_{ds:064x}',
            'retainedVersions': [{'datasetVersion': f'ds_{v:064x}'} for v in refs]}))
        metadata = path / 'metadata'
        metadata.mkdir()
        (metadata / 'release-manifest.json').write_text(json.dumps({'gitCommitTimestamp': n}))
        for version in {ds, *refs}:
            embedded = public / 'releases' / f'ds_{version:064x}'
            embedded.mkdir(parents=True)
            file = embedded / 'changes.json'
            file.write_text('[]')
            (embedded / 'manifest.json').write_text(json.dumps({'files': [
                {'path': str(file.relative_to(public)), 'bytes': 2}]}))
        stamp = time.time() - age * 86400
        os.utime(path, (stamp, stamp))
        return path

    def run_cleanup(self, dry=False, code=0):
        result = subprocess.run([sys.executable, '-c', CODE, str(self.root),
                                 'dry-run' if dry else 'apply'], text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stderr)
        return result.stdout + result.stderr if code else result.stdout

    def test_twenty_seven_same_dataset_releases_keep_three_even_when_recent(self):
        packages = [self.current, self.previous] + [self.release(n, 1, age=0) for n in range(3, 28)]
        (self.root / 'current').unlink(); (self.root / 'current').symlink_to(packages[-1])
        (self.root / 'previous').unlink(); (self.root / 'previous').symlink_to(packages[-2])
        plan = json.loads(self.run_cleanup(dry=True))
        self.assertEqual(len(plan['remove']), 24)
        self.assertTrue(all(p.exists() for p in packages))
        self.run_cleanup()
        self.assertEqual({p.name for p in (self.root / 'releases').iterdir()}, {p.name for p in packages[-3:]})
        self.assertEqual(json.loads(self.run_cleanup(dry=True))['remove'], [])

    def test_rollback_pointers_take_priority_and_unknown_paths_survive(self):
        newest = self.release(9, 9, age=0)
        old = self.release(8, 8, age=0)
        unknown = self.root / 'releases/unmanaged'; unknown.mkdir()
        alias = self.root / 'releases/rl_0000000099_000000000099'; alias.symlink_to(unknown)
        self.run_cleanup()
        self.assertTrue(self.current.exists()); self.assertTrue(self.previous.exists())
        self.assertTrue(newest.exists()); self.assertFalse(old.exists())
        self.assertTrue(alias.is_symlink()); self.assertTrue(unknown.exists())

    def test_corrupt_protected_data_prevents_all_deletions(self):
        old = self.release(3, 3, age=10)
        self.release(4, 4, age=0)
        (self.current / 'data/public/v1/manifest.json').write_text('broken')
        self.assertIn('skipped', self.run_cleanup(code=6))
        self.assertTrue(old.exists())

    def test_missing_embedded_history_prevents_all_deletions(self):
        old = self.release(3, 3, age=0)
        self.release(4, 4, age=0)
        (self.current / 'data/public/v1/releases' / f'ds_{3:064x}' / 'changes.json').unlink()
        self.run_cleanup(code=6)
        self.assertTrue(old.exists())

    def test_invalid_release_order_metadata_prevents_deletions(self):
        old = self.release(3, 3, age=0)
        (old / 'metadata/release-manifest.json').write_text('broken')
        self.run_cleanup(code=6)
        self.assertTrue(old.exists())


if __name__ == '__main__':
    unittest.main()
