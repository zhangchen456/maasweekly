"""Verified content-addressed blob interface, local adapter and bounded build cache (AR-06).

No network credentials, bucket URLs or deployment changes. Hashes identify exact bytes;
semantic snapshot identities remain in archival metadata and migration manifests.
"""
from __future__ import annotations
import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol


class BlobIntegrityError(ValueError): pass


def checksum(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    if root.is_symlink(): raise BlobIntegrityError('blob root symlink rejected')
    root = root.absolute()
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts: raise BlobIntegrityError('blob path escape')
    current = root
    for part in rel.parts:
        current /= part
        if current.is_symlink(): raise BlobIntegrityError('blob path symlink rejected')
    if not current.resolve().is_relative_to(root.resolve()): raise BlobIntegrityError('blob path escape')
    return current


class BlobStore(Protocol):
    def putIfAbsent(self, sha256: str, raw: bytes) -> bool: ...
    def get(self, sha256: str, *, expected_bytes: int | None = None) -> bytes: ...
    def verify(self, sha256: str, *, expected_bytes: int | None = None) -> bool: ...


class FilesystemBlobStore:
    def __init__(self, root: Path): self.root = root.absolute()

    def path(self, sha256: str) -> Path:
        if not re.fullmatch('[0-9a-f]{64}', sha256): raise BlobIntegrityError('invalid blob hash')
        return safe_path(self.root, f'sha256/{sha256[:2]}/{sha256}')

    def get(self, sha256: str, *, expected_bytes: int | None = None) -> bytes:
        raw = self.path(sha256).read_bytes()
        if checksum(raw) != sha256: raise BlobIntegrityError('blob checksum mismatch')
        if expected_bytes is not None and len(raw) != expected_bytes: raise BlobIntegrityError('blob byte count mismatch')
        return raw

    def verify(self, sha256: str, *, expected_bytes: int | None = None) -> bool:
        self.get(sha256, expected_bytes=expected_bytes)
        return True

    def putIfAbsent(self, sha256: str, raw: bytes) -> bool:
        if checksum(raw) != sha256: raise BlobIntegrityError('upload checksum mismatch')
        target = self.path(sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists(): self.verify(sha256, expected_bytes=len(raw)); return False
        fd, name = tempfile.mkstemp(prefix='.upload-', dir=target.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            try: os.link(temp, target)  # Atomic create-if-absent; never overwrite an existing object.
            except FileExistsError:
                self.verify(sha256, expected_bytes=len(raw)); return False
            self.verify(sha256, expected_bytes=len(raw))
            return True
        finally: temp.unlink(missing_ok=True)


class CachedBlobReader:
    """Cache is expendable; full object store retention is governed separately by manifests."""
    def __init__(self, backend: BlobStore, cache: Path, max_bytes: int = 64 * 1024 * 1024):
        if max_bytes < 0: raise ValueError('negative cache budget')
        self.backend = backend; self.cache = FilesystemBlobStore(cache)
        self.max_bytes = max_bytes; self.hits = 0; self.misses = 0
        self.prune()

    def prune(self):
        safe_path(self.cache.root, '.')
        paths = []
        if self.cache.root.exists():
            for p in self.cache.root.glob('sha256/*/*'):
                if p.is_symlink(): raise BlobIntegrityError('cache symlink rejected')
                if p.is_file() and re.fullmatch('[0-9a-f]{64}', p.name): paths.append(p)
        total = sum(p.stat().st_size for p in paths)
        for p in sorted(paths, key=lambda p: (p.stat().st_mtime_ns, p.name)):
            if total <= self.max_bytes: break
            total -= p.stat().st_size; p.unlink()
        return total

    def get(self, sha256: str, *, expected_bytes: int | None = None) -> bytes:
        path = self.cache.path(sha256)
        if path.exists():
            try: raw = self.cache.get(sha256, expected_bytes=expected_bytes)
            except BlobIntegrityError: path.unlink()  # A bad cache never authorizes bad bytes.
            else:
                self.hits += 1; os.utime(path, None); return raw
        self.misses += 1
        raw = self.backend.get(sha256, expected_bytes=expected_bytes)
        if len(raw) <= self.max_bytes:
            self.cache.putIfAbsent(sha256, raw); self.prune()
        return raw
