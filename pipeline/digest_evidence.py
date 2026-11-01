"""Evidence-first daily digest: the model selects facts; it cannot author prices or sunsets."""
import hashlib, json, re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

VERSION = 1
SUNSET = re.compile(r'\b(?:deprecated|deprecation|retired|retirement|end.of.life|shut.down)\b|停止服务|停止支持|正式下线', re.I)
RELEASE = re.compile(r'\b(?:released|launch(?:ed)?|introducing)\b|正式发布|正式上线', re.I)
DATE = re.compile(r'20\d\d[-/.年]\d{1,2}[-/.月]\d{1,2}日?')
NEGATION = re.compile(r'\b(?:not|never|no longer deprecated)\b|不会|不再下线|未下线|取消下线', re.I)

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
                 'url':c['url'],'quote':quote,'eligibleTypes':types,'effectiveDates':dates,
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
    conditions = {k:fact[k] for k in ['region','service_tier','billing_mode','context_band','time_condition','effective_at'] if fact.get(k) is not None}
    return (f"{fact['model_key']} · {fact['component']}：{fact['amount']} {fact['currency']} / "
            f"{fact['unit_quantity']} {fact['unit_name']}；条件："+json.dumps(conditions, ensure_ascii=False, sort_keys=True))

def validate_selection(value, entries):
    if not isinstance(value, dict) or set(value) != {'highlights'} or not isinstance(value['highlights'], list) or len(value['highlights']) > 25:
        raise ValueError('invalid digest schema')
    groups=[];summaries={};seen=set()
    for group in value['highlights']:
        if not isinstance(group, dict) or set(group) != {'platform','items'} or not isinstance(group['platform'], str) or not isinstance(group['items'], list) or not 1 <= len(group['items']) <= 3:
            raise ValueError('invalid digest group')
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
