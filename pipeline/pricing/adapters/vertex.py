"""Google Cloud token pricing. Exact supported models; source evidence precedes facts."""
from datetime import datetime, timezone
from html import escape
import hashlib
import re
from bs4 import BeautifulSoup
from .common import (_parse_html_tables, _make_fact, _parse_price_html, _evidence_id,
                     _drift_warnings, ContentSnapshot, Evidence, ExtractionResult,
                     ModelProfile, ContextBand, TimeCondition)

_MODELS = {
    'vertex-google': {'Gemini 3.8 Flash': 'Gemini 3.8 Flash'},
    'vertex-anthropic': {'Sonnet 5.5': 'Claude Sonnet 5.5', 'Opus 5.5': 'Claude Opus 5.5'},
}


class VertexPricingExtractor:
    version = 'vertex-2'

    def __init__(self, provider_id):
        if provider_id not in _MODELS:
            raise ValueError('unsupported Google Cloud pricing namespace')
        self.provider_id = provider_id

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        soup = BeautifulSoup(snapshot.content, 'html.parser')
        raw_tables = soup.find_all('table')
        facts, evidence, models = [], [], {}
        observed = datetime.fromtimestamp(snapshot.fetched_at, timezone.utc).date()
        seen = set()
        for table in _parse_html_tables(snapshot.content):
            dom = raw_tables[table.table_index]
            panel = dom.find_parent(attrs={'role': 'tabpanel'})
            tab = soup.find(id=panel.get('aria-labelledby')) if panel else None
            label = tab.get_text(' ', strip=True) if tab else ''
            headers = table.rows[0] if table.rows else []
            # Section/tab meaning is mandatory: never infer a platform/region by table order.
            google = self.provider_id == 'vertex-google'
            if google:
                if label not in ('Standard Model', 'Priority', 'Flex/Batch') or len(headers) != 7:
                    continue
                if headers[:3] != ['Model', 'Type', 'Region']:
                    continue
            else:
                if label not in ('Global', 'US Multi-Region (US)', 'EU Multi-Region (EU)'):
                    continue
                if len(headers) != 4 or headers[:2] != ['Model', 'Type']:
                    continue
            if not all('200K' in h and 'tokens' in h for h in headers[3:5] if google) or ('1M' not in ' '.join(headers)):
                continue
            heading = dom.find_previous(['h2', 'h3', 'h4'])
            excerpt = (str(heading) if heading else '') + '<p>' + escape(label) + '</p>' + table.html_fragment
            ev = Evidence(evidence_id=_evidence_id(snapshot.snapshot_id, table.table_index + 1),
                          snapshot_id=snapshot.snapshot_id, locator_type='table_row',
                          locator=f'tables[{table.table_index}]; tab={label}',
                          extractor_version=self.version, excerpt=excerpt,
                          excerpt_hash=hashlib.sha256(excerpt.encode()).hexdigest())
            table_facts = []
            current_name, current_kind = "", ""
            for row in table.rows[table.header_rows:]:
                if len(row) != len(headers):
                    continue
                if row[0]: current_name = row[0]; current_kind = ""
                if row[1]: current_kind = row[1]
                raw_name = current_name
                dated = re.search(r'(through|Starting) ([A-Z][a-z]+ \d{1,2}, \d{4})', raw_name)
                condition = None
                if dated:
                    day = datetime.strptime(dated.group(2), '%B %d, %Y').date()
                    if (dated.group(1) == 'through' and observed > day) or (dated.group(1) == 'Starting' and observed < day):
                        continue
                    if dated.group(1) == 'through':
                        condition = TimeCondition('promotional', 'UTC', 'through ' + dated.group(2))
                    raw_name = raw_name[:dated.start()].rstrip('* ').strip()
                name = _MODELS[self.provider_id].get(raw_name)
                if name is None:
                    continue
                kind = current_kind
                component = None
                if google:
                    if kind == 'Input (text, image, video, audio)': component = 'input'
                    elif kind == 'Text output (response and reasoning)': component = 'output'
                    region = {'Global': 'global', 'Non-global': 'non-global'}.get(row[2])
                    mode, tier = ('batch', 'flex_batch') if label == 'Flex/Batch' else ('realtime', 'priority' if label == 'Priority' else 'standard')
                    columns = [(3, component), (4, component)]
                    if component == 'input': columns.extend([(5, 'cache_read'), (6, 'cache_read')])
                else:
                    region = {'Global': 'global', 'US Multi-Region (US)': 'us', 'EU Multi-Region (EU)': 'eu'}[label]
                    mode, tier = ('batch' if 'Batch' in kind else 'realtime'), 'standard'
                    component = 'input' if kind in ('Input', 'Batch Input') else 'output' if kind in ('Output', 'Batch Output') else 'cache_read' if kind in ('Cache Hit', 'Batch Cache Hit') else 'cache_write' if 'Cache Write' in kind else None
                    if component == 'cache_write':
                        ttl = 'PT5M' if kind.startswith('5m') else 'PT1H' if kind.startswith('1h') else None
                        if ttl is None: continue
                        condition = TimeCondition('cache_ttl', 'UTC', ttl)
                    columns = [(2, component), (3, component)]
                if not component or not region:
                    continue
                for col, comp in columns:
                    if not comp: continue
                    parsed = _parse_price_html(row[col])
                    if not parsed: continue
                    long = (col in (4, 6)) if google else col == 3
                    band = ContextBand(200001, None) if long else ContextBand(0, 200000)
                    fact = _make_fact(snapshot, ev.evidence_id, self.provider_id, name,
                                      comp, mode, parsed, region=region, service_tier=tier,
                                      context_band=band, time_condition=condition)
                    # Repeated identities with different amounts are drift, never silently overwrite.
                    if fact.fact_key in seen:
                        raise ValueError('duplicate Google Cloud price identity')
                    seen.add(fact.fact_key); table_facts.append(fact)
                    models[fact.model_key] = ModelProfile(self.provider_id, fact.model_key, name,
                                                        'other', 'active', evidence_id=ev.evidence_id)
            if table_facts:
                evidence.append(ev); facts.extend(table_facts)
        return ExtractionResult(snapshot.snapshot_id, self.version, list(models.values()), facts,
                                evidence, _drift_warnings(self.provider_id, facts))
