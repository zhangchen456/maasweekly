"""Versioned server-side page materializations; no filesystem or Git outputs."""
from pathlib import Path
import hashlib
import json
import sys
from data_store import read, compose_daily, compose_weekly
from english_translation import CACHE, projected_texts


def projections(root, view):
    from arena_projection import from_view
    arena = from_view(view)
    arena_name = 'data/derived/leaderboards/lmarena.json'
    yield 'site/src/data/daily_changes.json', compose_daily(root, view=view)
    yield 'site/src/data/weekly-digest.json', compose_weekly(root, view=view)
    yield 'site/src/data/translations-en.json', {
        'schemaVersion': 1, 'texts': projected_texts(read(root, CACHE, {}, view=view))}
    for name in sorted(view.files):
        if name.startswith(('data/derived/pricing/', 'data/derived/leaderboards/')) \
                and name.count('/') == 3 and name.endswith('.json'):
            yield name, arena if name == arena_name and arena is not None else view.read_json(name)
    if arena is not None and arena_name not in view.files:
        yield arena_name, arena
    for name in ['data/normalized/platform-logos.json']:
        if name in view.files:
            yield name, view.read_json(name)
    sys.path.insert(0, str(Path(__file__).with_name('scripts')))
    from record_archive import index_records
    from pricing.archive import index_price_records
    yield 'site/src/data/record-index.json', index_records(
        value for _, value in view.iter_json('data/records', 'obs_*.json'))
    yield 'site/src/data/price-record-index.json', index_price_records(
        value for _, value in view.iter_json('data/price-records', 'price_*.json'))


def store_projections(connection, root, view, code_commit):
    # The caller commits this transaction together with the verified candidate.
    names = []
    with connection.cursor() as cursor:
        for name, value in projections(root, view):
            body = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
            raw = body.encode()
            sha = hashlib.sha256(raw).hexdigest()
            cursor.execute('''INSERT INTO maas_data.page_projections
              (input_version,code_commit,name,payload_json,sha256,bytes)
              VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
              (view.version, code_commit, name, body, sha, len(raw)))
            cursor.execute('''SELECT sha256,bytes FROM maas_data.page_projections
              WHERE input_version=%s AND code_commit=%s AND name=%s''',
              (view.version, code_commit, name))
            if cursor.fetchone() != (sha, len(raw)):
                raise ValueError('page materialization differs from existing candidate')
            names.append(name)
    return names
