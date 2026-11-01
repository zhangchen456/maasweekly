"""Evidence-first daily digest: the model selects facts; it cannot author prices or sunsets."""
import hashlib, json, re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

VERSION = 1
SUNSET = re.compile(r'\b(?:retired|retirement|end.of.life|shut.down|discontinued)\b|停止服务|正式下线', re.I)
RELEASE = re.compile(r'\b(?:released|launch(?:ed)?|introducing)\b|正式发布|正式上线', re.I)
DATE = re.compile(r'20\d\d[-/.年]\d{1,2}[-/.月]\d{1,2}日?')
NEGATION = re.compile(r'\b(?:not|never|delayed|postponed|no longer deprecated)\b|不会|不再下线|未下线|取消下线|延期|推迟', re.I)

def archived_prices(root, date, prices):
    """Upgrade old flat events only from matching immutable, already validated facts."""
    result=[]
    for original in prices[:20]:
        p=dict(original)
        if not p.get('currentFact') and re.fullmatch(r'price_[a-f0-9]{64}', str(p.get('id', ''))):
            try:
                record=json.loads((root/'data/price-records'/f"{p['id']}.json").read_text())
                if record['id']!=p['id'] or record['date']!=date:continue
                for field,key in [('afterVersionId','currentFact'),('beforeVersionId','previousFact')]:
                    version=record.get(field)
                    if not version:continue
                    if not re.fullmatch(r'pfv_[a-f0-9]{64}',version):raise ValueError('invalid fact reference')
                    fact=json.loads((root/'data/price-facts/versions'/f'{version}.json').read_text())
                    if fact['version_id']!=version:raise ValueError('fact identity mismatch')
                    p[key]=fact
                fact=p['currentFact']
                if any(p.get(a)!=fact.get(b) for a,b in [('provider','provider_id'),('model','model_key'),('component','component'),('currency','currency'),('unit_quantity','unit_quantity'),('unit_name','unit_name')]):continue
                if Decimal(str(p['current']))!=Decimal(str(fact['amount'])):continue
                if p.get('previous') is not None and Decimal(str(p['previous']))!=Decimal(str(p['previousFact']['amount'])):continue
            except (OSError, KeyError, ValueError, InvalidOperation):continue
        result.append(p)
    return result

def safe_url(value):
    try:
        u = urlsplit(value)
        return isinstance(value, str) and u.scheme == 'https' and bool(u.hostname) and not u.username and not u.password
    except (ValueError, TypeError):return False

def catalog(date, changed, prices, aliases):
    entries = {}
    def add(entry):
        entry['observedDate'] = date
        key = 'de_'+hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        entries[key] = {'id':key, **entry}
    for c in changed[:25]:
        if c.get('kind') != 'substantive' or not safe_url(c.get('url')):continue
        # A removed row is not evidence of service termination. Only current text is eligible.
        lines = [*c.get('added_lines', [])[:12], *[p['after'] for p in c.get('pairs', [])[:12]]]
        for raw in lines:
            if not isinstance(raw, str) or len(raw) > 1000:continue  # embedded page configuration is not an announcement
            quote = raw.strip()
            if not quote or len(quote) > 320:continue
            types = ['other']
            if RELEASE.search(quote) and not NEGATION.search(quote):types.append('release')
            dates = DATE.findall(quote)
            if SUNSET.search(quote) and dates and not NEGATION.search(quote):types.append('sunset')
            add({'platform':c['platform'],'sourceType':c['source_type'],'sourceId':c.get('id'),
                 'url':c['url'],'quote':quote,'eligibleTypes':types,'mentionedDates':dates,
                 'recordUrl':c.get('permalink'),'kind':'source'})
    for p in prices[:20]:
        if not safe_url(p.get('evidence_url')):continue
        # New producers attach both complete fact versions. Old events cannot
        # establish that currencies/units/context stayed comparable.
        fact = p.get('currentFact')
        if not isinstance(fact, dict):continue
        try:
            if not Decimal(str(fact['amount'])).is_finite():continue
        except (KeyError, InvalidOperation):continue
        required = ['model_key','component','currency','unit_quantity','unit_name','region','service_tier']
        if any(fact.get(k) is None or fact.get(k) == '' for k in required):continue
        add({'platform':aliases.get(str(p['provider']).casefold(), p['provider']), 'sourceType':'pricing',
             'sourceId':p.get('id'),'url':p['evidence_url'],'kind':'price','eligibleTypes':['pricing'],
             'currentFact':fact,'previousFact':p.get('previousFact'),
             'recordUrl':('/item/'+p['id']+'/') if p.get('id') else None})
    return entries

def price_text(fact):
    conditions = [f"区域 {fact['region']}", f"服务档位 {fact['service_tier']}"]
    if fact.get('billing_mode'):conditions.append('计费方式 '+fact['billing_mode'])
    band = fact.get('context_band')
    if isinstance(band, dict):
        low = band.get('min_input_tokens', band.get('min', 0))
        high = band.get('max_input_tokens', band.get('max'))
        conditions.append(f"输入长度 {low}–{high if high is not None else '不限'} tokens")
    elif band:conditions.append('输入长度条件 '+str(band))
    when = fact.get('time_condition')
    if isinstance(when, dict):conditions.append('适用时段 '+' '.join(str(when[k]) for k in ['period','tz','schedule'] if when.get(k)))
    elif when:conditions.append('适用时段 '+str(when))
    if fact.get('effective_at'):conditions.append('生效时间 '+str(fact['effective_at']))
    return (f"{fact['model_key']} · {fact['component']}：{fact['amount']} {fact['currency']} / "
            f"{fact['unit_quantity']} {fact['unit_name']}；"+'，'.join(conditions))

def validate_selection(value, entries):
    if not isinstance(value, dict) or set(value) != {'highlights'} or not isinstance(value['highlights'], list) or len(value['highlights']) > 25:
        raise ValueError('invalid digest schema')
    groups=[];summaries={};seen=set();platforms=set()
    for group in value['highlights']:
        if not isinstance(group, dict) or set(group) != {'platform','items'} or not isinstance(group['platform'], str) or not isinstance(group['items'], list) or not 1 <= len(group['items']) <= 3:
            raise ValueError('invalid digest group')
        if group['platform'] in platforms:raise ValueError('duplicate platform group')
        platforms.add(group['platform'])
        items=[]
        for item in group['items']:
            if not isinstance(item, dict) or set(item) != {'type','evidenceId'}:raise ValueError('invalid digest item')
            key=item['evidenceId']
            if not isinstance(key, str) or key not in entries or key in seen:raise ValueError('unknown or duplicate evidence')
            e=entries[key]
            if group['platform'] != e['platform'] or item['type'] not in e['eligibleTypes']:raise ValueError('unsupported classification or platform')
            seen.add(key)
            if e['kind'] == 'price':
                text='当前报价：'+price_text(e['currentFact'])
                if e['previousFact']:text+='；此前报价：'+price_text(e['previousFact'])
                else:text+='（本次新增收录，不代表首次发布）'
            else:text='官方页面新增内容：'+e['quote']
            proof={k:v for k,v in e.items() if k != 'eligibleTypes'}
            items.append({'type':item['type'],'text':text,'evidenceVersion':VERSION,'evidence':[proof]})
            summaries.setdefault(e['platform']+'|'+e['sourceType'], []).append(text)
        groups.append({'platform':group['platform'],'logo_summary':'官方来源变化摘录','items':items})
    return {'highlights':groups,'source_summaries':{k:'；'.join(v) for k,v in summaries.items()}}
