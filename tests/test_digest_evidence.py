import copy, json, sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from digest_evidence import catalog, validate_selection, archived_prices

class DigestEvidenceTests(unittest.TestCase):
 def source(self,added=None,removed=None):
  return {'platform':'A','source_type':'changelog','kind':'substantive','url':'https://official.test/log','id':'obs_1','added_lines':added or [],'removed_lines':removed or []}
 def select(self,entries,kind='other',**extra):
  return validate_selection({'highlights':[{'platform':'A','items':[{'type':kind,'evidenceId':next(iter(entries)),**extra}]}]},entries)
 def test_removed_model_never_proves_sunset(self):
  self.assertEqual(catalog('2026-11-01',[self.source(removed=['Model Alpha retired 2026-12-01'])],[],{}),{})
  e=catalog('2026-11-01',[self.source(['Model Beta replaces Model Alpha'])],[],{})
  for kind in ['sunset','release','pricing']:
   with self.assertRaises(ValueError):self.select(e,kind)
 def test_sunset_needs_current_explicit_statement_and_date(self):
  for text in ['Model Alpha deprecated','Model Alpha not deprecated on 2026-12-01']:
   with self.assertRaises(ValueError):self.select(catalog('2026-11-01',[self.source([text])],[],{}),'sunset')
  e=catalog('2026-11-01',[self.source(['Model Alpha will be retired on 2026-12-01'])],[],{})
  item=self.select(e,'sunset')['highlights'][0]['items'][0]
  self.assertEqual(item['evidence'][0]['effectiveDates'],['2026-12-01'])
  self.assertEqual(item['evidence'][0]['observedDate'],'2026-11-01')
 def test_no_generated_text_or_unbound_evidence(self):
  e=catalog('2026-11-01',[self.source(['Model Alpha released'])],[],{})
  with self.assertRaises(ValueError):self.select(e,text='服务已下线')
  result=self.select(e,'release');self.assertIn('Model Alpha released',result['highlights'][0]['items'][0]['text'])
  for obj in [[],{'highlights':'bad'},{'highlights':[{'platform':'B','items':[{'type':'other','evidenceId':next(iter(e))}]}]}, {'highlights':[{'platform':'A','items':[{'type':'other','evidenceId':'fake'}]}]}]:
   with self.assertRaises(ValueError):validate_selection(obj,e)
 def test_no_price_from_unstructured_page_or_incomplete_legacy_event(self):
  e=catalog('2026-11-01',[self.source(['input price $2 per million tokens'])],[],{})
  with self.assertRaises(ValueError):self.select(e,'pricing')
  self.assertEqual(catalog('2026-11-01',[],[{'provider':'A','evidence_url':'https://official.test','current':'2'}],{}),{})
 def test_currency_context_cache_component_and_units_preserved(self):
  f={'model_key':'Model A','component':'cached_input','amount':'0.250000','currency':'USD','unit_quantity':1000000,'unit_name':'token','region':'global','service_tier':'standard','context_band':{'min':200000,'max':None},'time_condition':None}
  prev={**f,'amount':'1.000000','currency':'CNY','context_band':{'min':0,'max':200000}}
  event={'provider':'A','evidence_url':'https://official.test/pricing','currentFact':f,'previousFact':prev}
  item=self.select(catalog('2026-11-01',[],[event],{}),'pricing')['highlights'][0]['items'][0]
  self.assertEqual(item['evidence'][0]['currentFact'],f)
  for s in ['cached_input','0.250000 USD','1.000000 CNY','200000','1000000 token']:self.assertIn(s,item['text'])
 def test_quote_url_and_identity_are_bound_and_config_is_excluded(self):
  c=self.source(['A'*1001]);self.assertEqual(catalog('2026-11-01',[c],[],{}),{})
  c=self.source(['quote']);a=catalog('2026-11-01',[c],[],{});c['added_lines']=['changed'];b=catalog('2026-11-01',[c],[],{});self.assertNotEqual(set(a),set(b))
  for url in ['javascript:alert(1)','https://user:pass@official.test']:
   c['url']=url;self.assertEqual(catalog('2026-11-01',[c],[],{}),{})
 def test_legacy_price_is_enriched_only_from_matching_archived_version(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);rid='price_'+'a'*64;vid='pfv_'+'b'*64
   (root/'data/price-records').mkdir(parents=True);(root/'data/price-facts/versions').mkdir(parents=True)
   record={'id':rid,'date':'2026-11-01','afterVersionId':vid}
   (root/'data/price-records'/f'{rid}.json').write_text(json.dumps(record))
   fact={'version_id':vid,'provider_id':'A','model_key':'Model','component':'cache_read','currency':'USD','unit_quantity':1000000,'unit_name':'token','amount':'0.250000','context_band':{'min':100,'max':200}}
   (root/'data/price-facts/versions'/f'{vid}.json').write_text(json.dumps(fact))
   price={'id':rid,'provider':'A','model':'Model','component':'cache_read','currency':'USD','unit_quantity':1000000,'unit_name':'token','current':'0.25'}
   self.assertEqual(archived_prices(root,'2026-11-01',[price])[0]['currentFact'],fact)
   for bad in [{**price,'currency':'CNY'},{**price,'current':'0.3'},{**price,'unit_name':'second'}]:self.assertEqual(archived_prices(root,'2026-11-01',[bad]),[])
   self.assertEqual(archived_prices(root,'2026-11-02',[price]),[])

if __name__=='__main__':unittest.main()
