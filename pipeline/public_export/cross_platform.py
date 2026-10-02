"""Verified explicit relations; legacy identities are never inferred or rewritten."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .loaders import ExportError

KEYS = ('developers', 'platforms', 'upstreamModels', 'availabilities')


def validate(catalog):
    present = [k in catalog for k in KEYS]
    if not any(present): return []  # Historical catalogs remain valid.
    if not all(present) or not all(isinstance(catalog[k], list) for k in KEYS):
        return ['cross-platform catalog incomplete']
    errors = []
    def index(key, id_key):
        result = {}
        for row in catalog[key]:
            if not isinstance(row, dict) or not isinstance(row.get(id_key), str) or row[id_key] in result:
                errors.append('cross-platform invalid/duplicate ' + key); continue
            result[row[id_key]] = row
        return result
    developers = index('developers', 'developerId'); platforms = index('platforms', 'platformId')
    upstream = index('upstreamModels', 'upstreamModelId'); avail = index('availabilities', 'availabilityId')
    models = {m['modelId'] for m in catalog.get('models', [])}
    for group in (developers, platforms):
        for row in group.values():
            if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', next(v for k,v in row.items() if k.endswith('Id'))): errors.append('invalid relation id')
            if not isinstance(row.get('displayName'), str) or not row['displayName'].strip(): errors.append('empty relation name')
    seen_models = set()
    for row in upstream.values():
        if not isinstance(row.get('upstreamModelId'), str) or not re.fullmatch(r'[a-z0-9-]+:[a-z0-9.-]+', row['upstreamModelId']): errors.append('invalid upstream id')
        if row.get('developerId') not in developers or row.get('modelId') not in models or row.get('modelId') in seen_models:
            errors.append('upstream reference invalid/ambiguous')
        seen_models.add(row.get('modelId'))
        if not isinstance(row.get('modelName'), str) or not row['modelName'].strip(): errors.append('empty upstream model name')
    tuples = set()
    for row in avail.values():
        u = upstream.get(row.get('upstreamModelId'))
        if not u or row.get('platformId') not in platforms or row.get('modelId') != u.get('modelId'):
            errors.append('availability reference invalid')
        ids = row.get('apiModelIds')
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x.strip() for x in ids) or len(set(ids)) != len(ids):
            errors.append('availability API identifiers invalid')
        if row.get('availabilityId') != str(row.get('upstreamModelId')) + '@' + str(row.get('platformId')): errors.append('availability identity mismatch')
        pair = (row.get('upstreamModelId'), row.get('platformId'))
        if pair in tuples: errors.append('ambiguous upstream/platform relationship')
        tuples.add(pair)
        if not isinstance(row.get('sourceId'), str) or not row['sourceId']: errors.append('availability source missing')
    for row in list(upstream.values()) + list(avail.values()):
        ev = row.get('evidence')
        if not isinstance(ev, dict): errors.append('relation evidence missing'); continue
        parsed = urlsplit(ev.get('url', ''))
        if parsed.scheme != 'https' or not parsed.hostname or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', ev.get('verifiedAt', '')):
            errors.append('relation evidence invalid')
    return errors


def load(root: Path, catalog):
    folder = root / 'data/model-registry'
    paths = [folder / 'upstream-models.json', folder / 'availabilities.json']
    if not any(p.exists() for p in paths): return {}, {}
    if not all(p.exists() for p in paths): raise ExportError('cross-platform registry incomplete')
    upstream = json.loads(paths[0].read_text())['upstreamModels']
    avail = json.loads(paths[1].read_text())['availabilities']
    developers = json.loads((folder/'developers.json').read_text())['developers']
    platforms = json.loads((folder/'platforms.json').read_text())['platforms']
    developer_ids = {u['developerId'] for u in upstream}; platform_ids = {a['platformId'] for a in avail}
    result = {'upstreamModels': upstream, 'availabilities': [
        {k:v for k,v in a.items() if k not in ('pricingSourceKey', 'pricingModelKey')} for a in avail]}
    for key, rows, wanted, identity in [('developers',developers,developer_ids,'developerId'), ('platforms',platforms,platform_ids,'platformId')]:
        selected = [r for r in rows if r[identity] in wanted]
        if any(r.get('verificationStatus') != 'verified' for r in selected): raise ExportError('unverified relationship entity')
        result[key] = [{identity:r[identity],'displayName':r['displayName']} for r in selected]
    errors = validate({**catalog, **result})
    if errors: raise ExportError('; '.join(errors))
    quotes = {}
    for a in avail:
        key = (a['pricingSourceKey'], a['pricingModelKey'])
        if key in quotes: raise ExportError('ambiguous price availability mapping')
        quotes[key] = a
    return result, quotes


def annotate(prices, mapping):
    for price in prices:
        # sourceId can serve multiple developers; match exact modelId/modelKey too.
        candidates = [a for a in mapping.values() if a['sourceId'] == price['sourceId'] and a['pricingModelKey'] == price['modelKey'] and a['modelId'] == price.get('modelId')]
        if len(candidates) > 1: raise ExportError('ambiguous public price platform')
        if candidates:
            a = candidates[0]
            price.update(platformId=a['platformId'], upstreamModelId=a['upstreamModelId'], availabilityId=a['availabilityId'])


def validate_prices(catalog, prices):
    mapping = {a['availabilityId']:a for a in catalog.get('availabilities', [])}
    errors = []
    for price in prices:
        if not any(k in price for k in ('platformId','upstreamModelId','availabilityId')): continue
        row = mapping.get(price.get('availabilityId'))
        if not row or any(row.get(k) != price.get(k) for k in ('platformId','upstreamModelId','modelId','sourceId')):
            errors.append('price platform reference invalid')
    return errors
