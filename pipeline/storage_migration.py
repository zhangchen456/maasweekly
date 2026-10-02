"""Explicit local snapshot migration; copy, verification and restore are separate operations."""
from __future__ import annotations
import json
import fcntl
import mimetypes
import re
from pathlib import Path
from blob_store import BlobStore, BlobIntegrityError, checksum, safe_path
from input_snapshot import canonical, atomic, assert_no_pending

RESTORE_PENDING = 'data/storage-restore-pending.json'


def raw_files(root: Path):
    return sorted(p for p in (root/'data/snapshots').rglob('*') if p.is_file())


def build_manifest(root: Path, source_commit: str):
    lock_path = safe_path(root, 'data/.pipeline.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as stream:
        try: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('another input writer is active') from None
        return _build_manifest_locked(root, source_commit)


def _build_manifest_locked(root: Path, source_commit: str):
    assert_no_pending(root)
    if not re.fullmatch('[0-9a-f]{40}', source_commit): raise ValueError('fixed source commit required')
    files = {}
    by_hash = {}
    for p in raw_files(root):
        logical = p.relative_to(root).as_posix(); raw = safe_path(root, logical).read_bytes(); digest = checksum(raw)
        files[logical] = {'blobId':'blob_'+digest, 'rawSha256':digest, 'bytes':len(raw),
                          'contentType':mimetypes.guess_type(p.name)[0] or 'application/octet-stream'}
        by_hash.setdefault(digest, []).append(logical)
    evidence = {}
    for p in (root/'data/price-evidence').glob('*.json'):
        record = json.loads(safe_path(root, p.relative_to(root).as_posix()).read_bytes())
        evidence.setdefault(record['snapshotContentId'], []).append(record['id'])
    snapshots = {}
    for p in sorted((root/'data/price-snapshots').glob('*.json')):
        raw = safe_path(root, p.relative_to(root).as_posix()).read_bytes(); record = json.loads(raw)
        refs = by_hash.get(record['content_sha256'], [])
        snapshots[record['id']] = {'metadataPath':p.relative_to(root).as_posix(), 'metadataSha256':checksum(raw),
             'semanticContentHash':record['content_sha256'], 'rawPaths':refs,
             'rawState':'available' if refs else 'legacy_raw_missing',
             'evidenceIds':sorted(evidence.get(record['id'], []))}
    public = root/'data/public/v1/manifest.json'
    dataset = json.loads(public.read_text())['datasetVersion'] if public.exists() else None
    pointer = root/'data/inputs-current.json'
    input_version = json.loads(pointer.read_text())['inputVersion'] if pointer.exists() else None
    body = {'schemaVersion':1, 'scope':'raw-snapshots-local-drill', 'sourceCommit':source_commit,
            'datasetVersion':dataset, 'inputVersion':input_version, 'files':files, 'snapshots':snapshots}
    return {**body, 'migrationVersion':'sm_'+checksum(canonical(body).encode())}


def validate_manifest(value):
    if value.get('schemaVersion') != 1 or value.get('scope') != 'raw-snapshots-local-drill': raise BlobIntegrityError('storage manifest schema')
    body = {k:v for k,v in value.items() if k != 'migrationVersion'}
    if value.get('migrationVersion') != 'sm_'+checksum(canonical(body).encode()): raise BlobIntegrityError('storage manifest checksum')
    for logical, entry in value['files'].items():
        if not logical.startswith('data/snapshots/') or Path(logical).is_absolute() or '..' in Path(logical).parts: raise BlobIntegrityError('restore logical path escape')
        if not re.fullmatch('[0-9a-f]{64}', entry['rawSha256']) or entry['blobId'] != 'blob_'+entry['rawSha256']: raise BlobIntegrityError('storage blob identity')
        if not isinstance(entry['bytes'], int) or entry['bytes'] < 0: raise BlobIntegrityError('storage object size')
    for ref in value['snapshots'].values():
        for logical in ref['rawPaths']:
            if logical not in value['files'] or value['files'][logical]['rawSha256'] != ref['semanticContentHash']: raise BlobIntegrityError('snapshot blob reference')
    return value


def objects(manifest):
    validate_manifest(manifest)
    unique = {}
    for logical, entry in manifest['files'].items():
        old = unique.setdefault(entry['rawSha256'], {**entry, 'sourcePath':logical})
        if old['bytes'] != entry['bytes']: raise BlobIntegrityError('same hash with inconsistent size')
    return unique


def copy_objects(root: Path, manifest, store: BlobStore, *, only=None, max_objects=None):
    unique = objects(manifest); copied = existing = total = processed = 0; failures = []
    if max_objects is not None and max_objects < 0: raise ValueError('negative copy limit')
    if only is not None and not only.issubset(unique): raise ValueError('failed list contains unknown objects')
    selected_count = len(unique) if only is None else len(only)
    for digest, entry in unique.items():
        if only is not None and digest not in only: continue
        if max_objects is not None and processed >= max_objects: break
        processed += 1
        try:
            raw = safe_path(root, entry['sourcePath']).read_bytes()
            if len(raw) != entry['bytes'] or checksum(raw) != digest: raise BlobIntegrityError('source changed after manifest')
            created = store.putIfAbsent(digest, raw)
            store.verify(digest, expected_bytes=entry['bytes'])
            copied += int(created); existing += int(not created); total += len(raw)
        except (OSError, ValueError) as error:
            failures.append({'sha256':digest, 'code':type(error).__name__})
    return {'complete':processed==selected_count and not failures, 'copiedObjects':copied, 'existingObjects':existing, 'verifiedBytes':total, 'failures':failures}


def verify_objects(manifest, store: BlobStore):
    failures = []; verified = 0
    for digest, entry in objects(manifest).items():
        try: store.verify(digest, expected_bytes=entry['bytes']); verified += 1
        except (OSError, ValueError) as error: failures.append({'sha256':digest,'code':type(error).__name__})
    return {'verifiedObjects':verified, 'failures':failures}


def restore(root: Path, manifest, reader, *, max_files=None):
    validate_manifest(manifest)
    lock_path = safe_path(root, 'data/.pipeline.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as stream:
        try: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('another input writer is active') from None
        if safe_path(root, 'data/pipeline-pending.json').exists(): raise ValueError('pipeline recovery pending; storage restore forbidden')
        return _restore_locked(root, manifest, reader, max_files=max_files)


def _restore_locked(root: Path, manifest, reader, *, max_files=None):
    validate_manifest(manifest)
    if max_files is not None and max_files < 0: raise ValueError('negative restore limit')
    marker = safe_path(root, RESTORE_PENDING)
    if marker.exists() and json.loads(marker.read_text()).get('migrationVersion') != manifest['migrationVersion']:
        raise BlobIntegrityError('another restore is pending')
    atomic(marker, (canonical({'schemaVersion':1,'migrationVersion':manifest['migrationVersion']})+'\n').encode())
    restored = existing = total = 0
    for logical, entry in manifest['files'].items():
        if max_files is not None and restored+existing >= max_files: return {'complete':False,'restoredFiles':restored,'existingFiles':existing,'bytes':total}
        path = safe_path(root, logical)
        if path.exists():
            raw = path.read_bytes()
            if checksum(raw) != entry['rawSha256'] or len(raw) != entry['bytes']: raise BlobIntegrityError('restore target differs; refusing overwrite')
            existing += 1; continue
        raw = reader.get(entry['rawSha256'], expected_bytes=entry['bytes'])
        atomic(path, raw); restored += 1; total += len(raw)
    # Reverify all local files before declaring complete, including resumed existing files.
    for logical, entry in manifest['files'].items():
        raw = safe_path(root, logical).read_bytes()
        if checksum(raw) != entry['rawSha256'] or len(raw) != entry['bytes']: raise BlobIntegrityError('restored file checksum')
    marker.unlink()
    return {'complete':True,'restoredFiles':restored,'existingFiles':existing,'bytes':total}


def cleanup_plan(store_root: Path, manifests, *, now: float, grace_seconds: float):
    if not manifests or grace_seconds < 0: raise ValueError('reference manifests and nonnegative grace required')
    referenced = set()
    for manifest in manifests: referenced.update(objects(manifest))
    rows = []
    for p in sorted((store_root/'sha256').glob('*/*')):
        if p.is_symlink(): raise BlobIntegrityError('cleanup store symlink')
        if not p.is_file() or not re.fullmatch('[0-9a-f]{64}', p.name): continue
        if p.name not in referenced and now-p.stat().st_mtime >= grace_seconds:
            rows.append({'blobId':'blob_'+p.name,'bytes':p.stat().st_size,'ageSeconds':now-p.stat().st_mtime})
    return {'dryRun':True,'referenceManifestCount':len(manifests),'referencedObjects':len(referenced),'candidates':rows}
