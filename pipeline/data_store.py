"""Standard inputs and the sole legacy-site projector (AR-03).

Facts remain in records/price-facts/evidence. No consumer falls back to site data.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

DAILY = 'data/normalized/source-streams.json'
PRICE_EVENTS = 'data/normalized/price-events.json'
SUMMARIES = 'data/derived/day-summaries.json'
WEEKLY = 'data/derived/weekly-rollup.json'
WEEK_SUMMARIES = 'data/derived/week-summaries.json'
PRICING = 'data/derived/pricing'
EDITORIAL = 'data/editorial/weekly'
STRUCTURED = 'data/derived/weekly-structured'


def read(root: Path, rel: str, default=None):
    p = root / rel
    if not p.exists():
        if default is not None: return default
        raise FileNotFoundError(f'standard input missing: {rel}; run migrate-standard-inputs.py')
    current = root
    for part in Path(rel).parts:
        if part == '..': raise ValueError('standard input path escape')
        current /= part
        if current.is_symlink(): raise ValueError('standard input symlink')
    if not p.resolve().is_relative_to(root.resolve()): raise ValueError('standard input path escape')
    return json.loads(p.read_text(encoding='utf-8'))


def write(root: Path, rel: str, value):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, p)


def compose_daily(root: Path):
    data = read(root, DAILY)
    summaries = read(root, SUMMARIES, {})
    prices = read(root, PRICE_EVENTS, {})
    days = {d['date']: dict(d) for d in data.get('days', [])}
    oldest = min(days) if days else None
    for date, events in prices.items():
        if oldest and date < oldest: continue
        if date not in days:
            days[date] = {'date': date, 'stats': {}, 'changed': [], 'first_fetch': False, 'failed': []}
        if events: days[date]['price_changes'] = events
    for date, day in days.items():
        summary = summaries.get(date, {})
        if summary.get('highlights'): day['highlights'] = summary['highlights']
        for change in day.get('changed', []):
            key = change.get('id') or f"{change.get('platform')}|{change.get('source_type')}"
            text = summary.get('sourceSummaries', {}).get(key)
            if text: change['llm_summary'] = text
    # Preserve frozen source window order; price-only days follow the established ascending order.
    return {**data, 'days': list(days.values())}


def save_observations(root: Path, data):
    clean = {**data, 'days': []}
    for day in data.get('days', []):
        d = {k: v for k, v in day.items() if k not in ('highlights', 'price_changes')}
        d['changed'] = [{k: v for k, v in c.items() if k != 'llm_summary'} for c in day.get('changed', [])]
        clean['days'].append(d)
    write(root, DAILY, clean)


def legacy_provenance():
    return {'status': 'legacy_unknown', 'inputSha256': None, 'inputRefs': [], 'promptVersion': None, 'model': None}


def provenance(value, prompt, model, input_text=None):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    refs = sorted({str(c['id']) for c in [*value.get('changed', []), *value.get('price_changes', [])] if c.get('id')}) if isinstance(value, dict) else []
    return {'status': 'success', 'inputSha256': hashlib.sha256((input_text if input_text is not None else raw).encode()).hexdigest(), 'inputRefs': refs,
            'promptVersion': hashlib.sha256(prompt.encode()).hexdigest(), 'model': model}


def save_day_summaries(root: Path, days, metadata=None):
    out = read(root, SUMMARIES, {})
    for day in days:
        sources = {c.get('id') or f"{c.get('platform')}|{c.get('source_type')}": c['llm_summary']
                   for c in day.get('changed', []) if c.get('llm_summary')}
        if day.get('highlights') or sources:
            prev = out.get(day['date'], {})
            out[day['date']] = {'highlights': day.get('highlights', []), 'sourceSummaries': sources,
                                'provenance': (metadata or {}).get(day['date'], prev.get('provenance', legacy_provenance()))}
    write(root, SUMMARIES, out)


def record_summary_failure(root: Path, rel: str, key: str, model: str):
    entries = read(root, rel, {})
    entry = entries.setdefault(key, {'provenance': {'status': 'failed'}})
    entry['lastAttempt'] = {'status': 'failed', 'model': model, 'reason': 'generation_failed'}
    write(root, rel, entries)


def compose_weekly(root: Path):
    weeks = read(root, WEEKLY, [])
    stories = read(root, WEEK_SUMMARIES, {})
    for week in weeks:
        story = stories.get(week['week'], {}).get('story')
        if story: week['story'] = story
    return weeks


def save_week_summaries(root: Path, weeks, metadata=None):
    stories = read(root, WEEK_SUMMARIES, {})
    for week in weeks:
        if week.get('story'):
            prev = stories.get(week['week'], {})
            stories[week['week']] = {'story': week['story'], 'provenance': (metadata or {}).get(week['week'], prev.get('provenance', legacy_provenance()))}
    write(root, WEEK_SUMMARIES, stories)


def save_weekly(root: Path, weeks, metadata=None):
    write(root, WEEKLY, [{k: v for k, v in week.items() if k != 'story'} for week in weeks])
    save_week_summaries(root, weeks, metadata)


def project_site(root: Path):
    """Only this boundary writes site JSON/content compatibility outputs."""
    write(root, 'site/src/data/daily_changes.json', compose_daily(root))
    write(root, 'site/src/data/weekly-digest.json', compose_weekly(root))
    for folder, target, pattern in [(PRICING, 'site/src/data/pricing', '*.json'),
                                    (EDITORIAL, 'site/src/content/weekly', '*.md'),
                                    (STRUCTURED, 'site/src/content/weekly-structured', '*.json')]:
        source = root / folder
        for p in sorted(source.rglob(pattern)):
            out = root / target / p.relative_to(source); out.parent.mkdir(parents=True, exist_ok=True)
            if p.is_symlink(): raise ValueError('projection symlink rejected')
            out.write_bytes(p.read_bytes())
    timeline = root / 'data/derived/timeline.json'
    if timeline.exists():
        (root / 'site/src/content/timeline.json').write_bytes(timeline.read_bytes())
    # Existing archival index algorithms remain authoritative; compatibility indexes are rebuildable.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
    import record_archive
    from pricing import archive
    write(root, 'site/src/data/record-index.json', record_archive.build_index(root / 'data/records'))
    write(root, 'site/src/data/' + archive.INDEX_PRICE, archive.build_price_index(root / 'data/price-records'))
    write(root, 'site/src/data/' + archive.INDEX_EVIDENCE, archive.build_evidence_index(root / 'data/price-evidence'))
