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
        stamp = time.time() - age * 86400
        os.utime(path, (stamp, stamp))
        return path

    def run_cleanup(self, dry=False):
        result = subprocess.run([sys.executable, '-c', CODE, str(self.root),
                                 'dry-run' if dry else 'apply'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_expired_packages_cannot_protect_each_other(self):
        old_a = self.release(4, 4, age=10, refs=[4, 5])
        old_b = self.release(5, 5, age=10, refs=[4, 5])
        plan = json.loads(self.run_cleanup(dry=True))
        self.assertEqual({r['rid'] for r in plan['remove']}, {old_a.name, old_b.name})
        self.assertTrue(old_a.exists())
        self.run_cleanup()
        self.assertFalse(old_a.exists())
        self.assertFalse(old_b.exists())
        self.assertTrue(self.current.exists())
        self.assertTrue(self.previous.exists())

    def test_live_history_recent_packages_unknown_paths_and_symlinks_survive(self):
        history = self.release(3, 3, age=10)
        recent = self.release(4, 4, age=2)
        unknown = self.root / 'releases/unmanaged'; unknown.mkdir()
        (self.root / 'releases/rl_0000000009_000000000009').symlink_to(unknown)
        self.run_cleanup()
        self.assertTrue(history.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(unknown.exists())

    def test_unreadable_protected_manifest_skips_every_deletion(self):
        old = self.release(4, 4, age=10)
        (self.current / 'data/public/v1/manifest.json').write_text('broken')
        self.assertIn('skipped', self.run_cleanup())
        self.assertTrue(old.exists())

    def test_unreadable_candidate_manifest_is_kept(self):
        old = self.release(4, 4, age=10)
        (old / 'data/public/v1/manifest.json').write_text('broken')
        self.run_cleanup()
        self.assertTrue(old.exists())


if __name__ == '__main__':
    unittest.main()
