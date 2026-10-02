"""Pinned committed input views for multi-file pipeline writes (AR-04).

Mutable inputs get content-addressed copies; immutable archival leaves are referenced.
These are input checkpoints, not a second fact archive or a public datasetVersion.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path

POINTER = 'data/inputs-current.json'
PENDING = 'data/pipeline-pending.json'
PATTERNS = (
    'data/records/*.json', 'data/record-revisions/*/*.json',
    'data/price-records/*.json', 'data/price-record-revisions/*/*.json',
    'data/diff/*.json', 'data/diff/*.md', 'data/price-facts/current.json', 'data/price-facts/versions/*.json', 'data/price-evidence/*.json', 'data/price-snapshots/*.json',
    'data/normalized/**/*.json', 'data/derived/**/*.json', 'data/editorial/**/*.md',
)
IMMUTABLE = ('data/record-revisions/', 'data/price-record-revisions/', 'data/price-facts/versions/', 'data/price-evidence/', 'data/price-snapshots/')


def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def digest(raw): return hashlib.sha256(raw).hexdigest()


def safe(root: Path, relative: str):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts: raise ValueError('input checkpoint path escape')
    current = root
    for part in p.parts:
        current /= part
        if current.is_symlink(): raise ValueError('input checkpoint symlink')
    if not current.resolve().is_relative_to(root.resolve()): raise ValueError('input checkpoint path escape')
    return current


def atomic(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def put_json(root: Path, relative: str, value): atomic(safe(root, relative), (canonical(value) + '\n').encode())


def role_files(root: Path):
    found = {}
    for pattern in PATTERNS:
        for p in root.glob(pattern):
            if p.is_file(): found[str(p.relative_to(root))] = safe(root, str(p.relative_to(root)))
    return dict(sorted(found.items()))


def capture(root: Path, run_id: str, *, publish=True):
    files = {}
    current = root / 'data/price-facts/current.json'
    if current.exists():
        value = json.loads(current.read_text())
        for fact in value.get('facts', {}).values():
            if not safe(root, 'data/price-facts/versions/' + fact['version_id'] + '.json').exists(): raise ValueError('current fact reference missing')
    weekly_dir = root / 'data/editorial/weekly'
    hashes_path = root / 'data/derived/weekly-inputs.json'
    hashes = json.loads(hashes_path.read_text()) if hashes_path.exists() else None
    for md in weekly_dir.glob('*.md'):
        structured = safe(root, f'data/derived/weekly-structured/{md.stem}.json')
        if not structured.exists() or json.loads(structured.read_text()).get('date') != md.stem: raise ValueError('formal weekly projection missing')
        if hashes is not None and hashes.get(md.stem) != digest(md.read_bytes()): raise ValueError('weekly projection input hash differs')
    for logical, p in role_files(root).items():
        raw = p.read_bytes()
        if p.suffix == '.json': json.loads(raw)
        target = p
        if logical.startswith(('data/records/', 'data/price-records/')):
            record = json.loads(raw)
            folder = 'record-revisions' if logical.startswith('data/records/') else 'price-record-revisions'
            revision = safe(root, f'data/{folder}/{record["id"]}/{record["revision"]}.json')
            if not revision.exists() or json.loads(revision.read_bytes()) != record:
                raise ValueError('current record differs from immutable revision: ' + record['id'])
            target = revision; raw = revision.read_bytes()
        elif not logical.startswith(IMMUTABLE):
            checksum = digest(raw)
            target = safe(root, f'data/input-objects/{checksum}{p.suffix}')
            if target.exists():
                if target.read_bytes() != raw: raise ValueError('immutable input object collision')
            else: atomic(target, raw)
        files[logical] = {'path': str(target.relative_to(root)), 'bytes': len(raw), 'sha256': digest(raw)}
    version = 'in_' + digest(canonical(files).encode())
    relative = f'data/input-manifests/{version}.json'
    manifest = {'schemaVersion': 1, 'inputVersion': version, 'originRunId': run_id, 'files': files}
    target = safe(root, relative)
    if not target.exists(): put_json(root, relative, manifest)
    if publish:
        pointer = {'schemaVersion': 1, 'inputVersion': version, 'manifestPath': relative}
        old_path = safe(root, POINTER)
        if old_path.exists():
            old = json.loads(old_path.read_text())
            previous = old['inputVersion'] if old['inputVersion'] != version else old.get('previousInputVersion')
            if previous: pointer['previousInputVersion'] = previous
        put_json(root, POINTER, pointer)
    return version


class InputView:
    def __init__(self, root: Path, pointer):
        self.root = root
        if pointer.get('schemaVersion') != 1: raise ValueError('input pointer schema')
        self.version = pointer['inputVersion']
        if not isinstance(self.version, str) or not re.fullmatch(r'in_[0-9a-f]{64}', self.version):
            raise ValueError('input pointer version')
        if pointer['manifestPath'] != f'data/input-manifests/{self.version}.json': raise ValueError('input manifest path')
        manifest = json.loads(safe(root, pointer['manifestPath']).read_text())
        self.files = manifest['files']
        if manifest.get('schemaVersion') != 1 or manifest.get('inputVersion') != self.version or 'in_' + digest(canonical(self.files).encode()) != self.version:
            raise ValueError('input manifest integrity')
        self._verified = set()
    def path(self, logical):
        entry = self.files[logical]
        p = safe(self.root, entry['path'])
        if logical not in self._verified:
            raw = p.read_bytes()
            if len(raw) != entry['bytes'] or digest(raw) != entry['sha256']: raise ValueError('input checkpoint file integrity: ' + logical)
            self._verified.add(logical)
        return p
    def glob(self, pattern):
        return [(logical, self.path(logical)) for logical in sorted(self.files) if Path(logical).match(pattern)]


def load_view(root: Path):
    p = safe(root, POINTER)
    return InputView(root, json.loads(p.read_text())) if p.exists() else None


def assert_no_pending(root: Path):
    if safe(root, 'data/storage-restore-pending.json').exists(): raise ValueError('storage restore pending; candidate build blocked')
    if safe(root, PENDING).exists(): raise ValueError('pipeline run pending; recover or discard before building a candidate')


def restore_mutable(root: Path, view: InputView):
    # Restore only compatibility current inputs; never delete immutable archival leaves.
    expected = {logical for logical in view.files if not logical.startswith(IMMUTABLE)}
    for logical, p in role_files(root).items():
        if logical.startswith(IMMUTABLE): continue
        if logical not in expected: p.unlink()
    for logical in sorted(expected): atomic(safe(root, logical), view.path(logical).read_bytes())


def prune_checkpoints(root: Path, pointer):
    """Keep current + previous runtime checkpoints; source/fact/evidence archives are untouched.
    Historical input hashes remain in run records and Git commits. Full checkpoints are a
    bounded recovery cache, not the evidence history or public cursor retention policy.
    """
    retained = {pointer['inputVersion']}
    if pointer.get('previousInputVersion'): retained.add(pointer['previousInputVersion'])
    referenced = set()
    for version in retained:
        view = InputView(root, {'schemaVersion': 1, 'inputVersion': version, 'manifestPath': f'data/input-manifests/{version}.json'})
        referenced.update(entry['path'] for entry in view.files.values() if entry['path'].startswith('data/input-objects/'))
    pending = safe(root, PENDING)
    if pending.exists(): raise ValueError('cannot prune pending runtime checkpoints')
    folder = safe(root, 'data/input-manifests')
    for path in folder.glob('in_*.json'):
        if re.fullmatch(r'in_[0-9a-f]{64}', path.stem) and path.stem not in retained: safe(root, str(path.relative_to(root))).unlink()
    for path in safe(root, 'data/input-objects').glob('*'):
        relative = str(path.relative_to(root))
        if re.fullmatch(r'[0-9a-f]{64}\.(json|md)', path.name) and relative not in referenced: safe(root, relative).unlink()
