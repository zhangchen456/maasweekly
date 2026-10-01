#!/usr/bin/env python3
"""Read-only old/new source reconciliation; all generated outputs live in temporary directories."""
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'pipeline'))
def module(name, source):
    spec = importlib.util.spec_from_file_location(name, source); obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj
legacy = module('legacy_loaders', BASE / 'docs/architecture/refactoring-2026-10/acceptance/AR-03/legacy-loaders.py')
exporter = module('exporter', BASE / 'pipeline/scripts/export-public-data.py')
with patch('public_export.loaders.load_all', legacy.load_all): old = exporter.build_release(BASE)
new = exporter.build_release(BASE)
assert old['datasetVersion'] == new['datasetVersion']
manifest = json.loads((BASE / 'data/public/v1/manifest.json').read_text())
assert manifest['datasetVersion'] == new['datasetVersion']
results = []
with tempfile.TemporaryDirectory(prefix='maas-ar03-reconcile-') as folder:
    root = Path(folder); (root / 'old').mkdir(); (root / 'new').mkdir()
    exporter.write_release(old, root / 'old', old['datasetVersion']); exporter.write_release(new, root / 'new', new['datasetVersion'])
    for name in exporter.BUSINESS_FILES:
        before = (root / 'old' / name).read_bytes(); after = (root / 'new' / name).read_bytes()
        existing = BASE / 'data/public/v1' / next(f['path'] for f in manifest['files'] if f['path'].endswith('/' + name))
        assert before == after == existing.read_bytes(), name
        results.append({'collection': name, 'bytes': len(after), 'sha256': hashlib.sha256(after).hexdigest(), 'oldNewPublishedBytesEqual': True})
report = {'datasetVersion': new['datasetVersion'], 'dataThrough': new['dataThrough'], 'collections': results,
          'source': 'same current archival facts; frozen legacy loader vs standard loader; temporary output only'}
target = Path(sys.argv[1]); target.write_text(json.dumps(report, indent=2) + '\n'); print('Seven collections old/new/published byte-identical')
