import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'pipeline'))
from blob_store import FilesystemBlobStore
spec = importlib.util.spec_from_file_location('transfer', BASE / 'ops/verify-shadow-transfer.py')
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = FilesystemBlobStore(self.root / 'store')
        self.raw = b'original bytes\x00'
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.name = f'sha256/{self.sha[:2]}/{self.sha}'

    def archive(self, name=None, raw=None, symlink=False):
        with tarfile.open(self.root / 'blobs.tar.gz', 'w:gz') as archive:
            info = tarfile.TarInfo(name or self.name)
            if symlink:
                info.type = tarfile.SYMTYPE
                info.linkname = '/tmp/forbidden'
                archive.addfile(info)
            else:
                body = self.raw if raw is None else raw
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))

    def manifest(self):
        (self.root / 'parity.json').write_text('{"status":"passed"}')
        (self.root / 'shadow.dump').write_bytes(b'database backup')
        (self.root / 'raw-manifest.json').write_text('{}')
        names = ['blobs.tar.gz', 'shadow.dump', 'raw-manifest.json', 'parity.json']
        result = {'phase': 'shadow-only', 'files': {name: {
            'sha256': hashlib.sha256((self.root / name).read_bytes()).hexdigest(),
            'bytes': (self.root / name).stat().st_size} for name in names}}
        (self.root / 'transfer-manifest.json').write_text(json.dumps(result))

    def test_verified_transfer_and_repeat_are_idempotent(self):
        self.archive()
        self.manifest()
        transfer.validate_bundle(self.root)
        self.assertEqual(transfer.unpack(self.root, self.store), 1)
        self.assertEqual(transfer.unpack(self.root, self.store), 1)
        self.assertEqual(self.store.get(self.sha), self.raw)

    def test_corrupt_transfer_is_rejected_before_unpack(self):
        self.archive()
        self.manifest()
        (self.root / 'shadow.dump').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            transfer.validate_bundle(self.root)

    def test_symlink_or_path_escape_are_not_extracted(self):
        for name, symlink in [('../escape', False), (self.name, True), ('/absolute', False)]:
            self.archive(name, symlink=symlink)
            with self.assertRaises(ValueError):
                transfer.unpack(self.root, self.store)
        self.assertFalse((self.root.parent / 'escape').exists())

    def test_hash_mismatch_and_corrupt_existing_object_are_rejected(self):
        self.archive(raw=b'wrong object')
        with self.assertRaises(ValueError):
            transfer.unpack(self.root, self.store)
        self.archive()
        self.store.putIfAbsent(self.sha, self.raw)
        self.store.path(self.sha).write_bytes(b'bad')
        with self.assertRaises(ValueError):
            transfer.unpack(self.root, self.store)

    def test_only_genuine_bounded_appledouble_metadata_is_skipped(self):
        for magic, valid in [(b'\x00\x05\x16\x07', True), (b'fake', False)]:
            with tarfile.open(self.root / 'blobs.tar.gz', 'w:gz') as archive:
                info = tarfile.TarInfo('._sha256')
                raw = magic + b'\0' * 22
                info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
                obj = tarfile.TarInfo(self.name)
                obj.size = len(self.raw)
                archive.addfile(obj, io.BytesIO(self.raw))
            if valid:
                self.assertEqual(transfer.unpack(self.root, self.store), 1)
                self.assertFalse((self.store.root / '._sha256').exists())
            else:
                with self.assertRaises(ValueError):
                    transfer.unpack(self.root, self.store)


if __name__ == '__main__':
    unittest.main()
