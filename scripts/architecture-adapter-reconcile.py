#!/usr/bin/env python3
"""Compare frozen monolith and source-local adapters on every checked-in pricing fixture."""
import dataclasses
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(BASE / 'pipeline'))
from pricing.base import ContentSnapshot
from pricing.extractors import get_extractor
spec = importlib.util.spec_from_file_location('pricing.legacy_extractors', BASE / 'docs/architecture/refactoring-2026-10/acceptance/AR-04/legacy-extractors.py')
legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
results=[]
for p in sorted((BASE / 'tests/fixtures/pricing').glob('*')):
    if p.suffix not in ('.html', '.md'): continue
    provider = p.stem.split('_')[0].split('-')[0]
    extractor = get_extractor(provider + ':pricing')
    if extractor is None: continue
    content = p.read_text(); snapshot = ContentSnapshot(snapshot_id='fixed', source_key=provider+':pricing', url='https://example.com', fetched_at=1750000000, http_status=200, content_type='text/html', sha256=hashlib.sha256(content.encode()).hexdigest(), content=content)
    before=dataclasses.asdict(legacy.get_extractor(provider+':pricing').extract(snapshot)); after=dataclasses.asdict(extractor.extract(snapshot))
    assert before==after, p.name
    results.append({'fixture':p.name,'facts':len(after['price_facts']),'evidence':len(after['evidence']),'warnings':after['warnings'],'equal':True})
assert len(results)>=16
Path(sys.argv[1]).write_text(json.dumps({'fixtures':results,'versionsUnchanged':True},ensure_ascii=False,indent=2)+'\n')
print('Adapter facts/evidence/warnings identical:',len(results),'fixtures')
