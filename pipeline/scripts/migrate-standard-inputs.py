#!/usr/bin/env python3
"""One-time explicit import of current published compatibility inputs into standard ownership."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'pipeline'))
from data_store import (DAILY, PRICE_EVENTS, PRICING, EDITORIAL, STRUCTURED, compose_daily,
                        compose_weekly, save_observations, save_day_summaries, save_weekly, write)

def migrate(root):
    marker = root / 'data/normalized/input-migration.json'
    if marker.exists(): return json.loads(marker.read_text())
    daily = json.loads((root / 'site/src/data/daily_changes.json').read_text())
    weeks = json.loads((root / 'site/src/data/weekly-digest.json').read_text())
    save_observations(root, daily)
    save_day_summaries(root, daily.get('days', []))
    write(root, PRICE_EVENTS, {d['date']: d['price_changes'] for d in daily.get('days', []) if d.get('price_changes')})
    save_weekly(root, weeks)
    assert compose_daily(root) == daily, 'daily projection differs'
    assert compose_weekly(root) == weeks, 'weekly projection differs'
    files = {}
    for src, dst in [('site/src/data/pricing', PRICING), ('site/src/content/weekly', EDITORIAL),
                     ('site/src/content/weekly-structured', STRUCTURED)]:
        for p in sorted((root / src).rglob('*')):
            if not p.is_file() or p.suffix not in (".json", ".md"): continue
            if p.is_symlink(): raise ValueError('migration input symlink')
            out = root / dst / p.relative_to(root / src); out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, out)
            files[str(out.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    timeline = root / 'site/src/content/timeline.json'
    if timeline.exists():
        target = root / 'data/derived/timeline.json'; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(timeline, target)
        files['data/derived/timeline.json'] = hashlib.sha256(timeline.read_bytes()).hexdigest()
    report = {'schemaVersion': 1, 'migration': 'AR-03', 'authority': 'published weekly content; raw weekly remains import source',
              'legacyLlmProvenance': 'unknown; no historical regeneration', 'files': files,
              'weeklyCount': len(list((root / EDITORIAL).glob('*.md')))}
    write(root, 'data/normalized/input-migration.json', report)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--input-root', type=Path, default=BASE)
    args = parser.parse_args(); print(json.dumps(migrate(args.input_root.resolve()), ensure_ascii=False, indent=2))
