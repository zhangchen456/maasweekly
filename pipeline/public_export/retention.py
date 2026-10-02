"""Public retention references must be recoverable. Never mutate immutable release bytes."""
import json
import re
from pathlib import Path
from .loaders import ExportError
from .validator import validate_release_files

DS = re.compile(r'ds_[0-9a-f]{64}')


def excluded_versions(path):
    config = json.loads(Path(path).read_text())
    rows = config['exclusions']
    if config.get('schemaVersion') != '1.0' or not isinstance(rows, list):
        raise ExportError('invalid retention exclusion policy')
    result = set()
    for row in rows:
        ds = row.get('datasetVersion')
        if not isinstance(ds, str) or not DS.fullmatch(ds) or not row.get('reason') or not row.get('record') or ds in result:
            raise ExportError('invalid/duplicate retention exclusion')
        result.add(ds)
    return result


def checked_references(root, rows, current, *, exclusions=frozenset(), pending_current=False):
    if not isinstance(rows, list): raise ExportError('retainedVersions must be an array')
    result, removed, seen = [], [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('datasetVersion'), str) or not DS.fullmatch(row['datasetVersion']):
            raise ExportError('invalid retained dataset reference')
        ds = row['datasetVersion']
        if ds in seen: raise ExportError('duplicate retained dataset reference')
        seen.add(ds)
        folder = Path(root) / 'releases' / ds
        if ds != current and ds in exclusions and not folder.exists() and not folder.is_symlink():
            removed.append(ds); continue
        if ds == current and pending_current and not folder.exists():
            result.append(row); continue
        manifest = folder / 'manifest.json'
        if folder.is_symlink() or not folder.is_dir() or manifest.is_symlink() or not manifest.is_file():
            raise ExportError('retained release unavailable: ' + ds)
        payload = json.loads(manifest.read_text())
        if payload.get('datasetVersion') != ds: raise ExportError('retained manifest version mismatch: ' + ds)
        errors = validate_release_files(Path(root), payload)
        if errors: raise ExportError('retained release integrity failed: ' + ds + ': ' + '; '.join(errors[:2]))
        result.append(row)
    if current not in {r['datasetVersion'] for r in result}: raise ExportError('current release must be retained')
    return result, removed


def remove_known_missing(root, rows, *, exclusions, protected):
    kept, removed = [], []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('datasetVersion'), str) or not DS.fullmatch(row['datasetVersion']):
            raise ExportError('invalid retained dataset reference')
        ds = row['datasetVersion']; folder = Path(root) / 'releases' / ds
        if ds not in protected and ds in exclusions and not folder.exists() and not folder.is_symlink(): removed.append(ds)
        else: kept.append(row)
    return kept, removed
