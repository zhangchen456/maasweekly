"""Compatibility reader: verified legacy bytes or manifest-addressed blobs, never a URL."""
from pathlib import Path
from blob_store import BlobIntegrityError, checksum, safe_path
from storage_migration import validate_manifest


class SnapshotReader:
    def __init__(self, root: Path, manifest=None, reader=None):
        self.root = root
        self.manifest = validate_manifest(manifest) if manifest is not None else None
        self.reader = reader

    def get(self, logical: str) -> bytes:
        if not logical.startswith('data/snapshots/'): raise BlobIntegrityError('snapshot namespace required')
        path = safe_path(self.root, logical)
        entry = self.manifest['files'].get(logical) if self.manifest else None
        if path.exists():
            raw = path.read_bytes()
            if entry and (checksum(raw) != entry['rawSha256'] or len(raw) != entry['bytes']): raise BlobIntegrityError('legacy snapshot differs from pinned manifest')
            return raw
        if not entry or self.reader is None: raise FileNotFoundError('snapshot unavailable')
        return self.reader.get(entry['rawSha256'], expected_bytes=entry['bytes'])
