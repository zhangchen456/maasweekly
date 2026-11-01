"""Shared pages must not merge independent logical source observations or recovery."""
import copy,importlib.util,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pipeline'));sys.path.insert(0,str(ROOT/'tests'))
from test_public_export import FixtureRepo
from run_protocol import RunJournal
from data_store import read
from staged_fetch import fetch,source_key,wanted
from public_export.projector import SourceStatusIndex
spec=importlib.util.spec_from_file_location('identity_fetch',ROOT/'pipeline/scripts/fetch_sources.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
spec=importlib.util.spec_from_file_location('identity_monitor',ROOT/'scripts/monitor-collect.py');collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
URL='https://example.test/shared';A='example-blog';B='example-changelog'
REGISTRY=[{'source_id':sid,'display_name':'Example','source_type':kind,'type_label':kind,'primary_url':URL,'url_aliases':[URL]} for sid,kind in [(A,'blog'),(B,'changelog')]]
class SourceIdentityTests(unittest.TestCase):
 def setUp(self):
  self.fx=FixtureRepo();self.root=self.fx.root;self.addCleanup(self.fx.cleanup)
  config=self.root/'pipeline/config';config.mkdir(parents=True,exist_ok=True)
  (config/'source_registry.json').write_text(json.dumps({'sources':REGISTRY}))
  (config/'public_providers.json').write_text(json.dumps({'sourceToProvider':{A:'example',B:'example'},'pricingSourceKeyToSourceId':{}}))
 def test_shared_page_collects_distinct_successes_through_public_status_and_monitor(self):
  (self.root/'pipeline/config/maas_official_sources.json').write_text(json.dumps({'platforms':[{'name':'Example','sources':{'changelog':URL,'blog':URL}}]}))
  module.configure_root(self.root);self.addCleanup(module.configure_root,ROOT)
  with RunJournal(self.root,'sources','shared_live') as run,patch.object(sys,'argv',['sources']),patch.object(module,'_fetch_page',return_value=('Official shared page content without a content change',None)) as transport:
   module.main();self.assertEqual(transport.call_count,2);self.assertEqual(len(run.data['sources']),2)
   stamps={row['sourceId']:row['lastSuccessAt'] for row in run.data['sources'].values()};run.finish('success')
  index=SourceStatusIndex({},REGISTRY,read(self.root,'data/normalized/source-runtime.json'))
  self.assertEqual(index.status_of(A)['state'],'ok');self.assertEqual(index.status_of(B)['state'],'ok')
  rows=collector.collect(self.root)[0][0]['runs'][0]['sources'];self.assertEqual({r['sourceId'] for r in rows},{A,B})
  for row in rows:self.assertEqual(row['successAt'],int(stamps[row['sourceId']]*1000))
  self.assertEqual(collector.collect(self.root),collector.collect(self.root))
 def test_real_unchanged_fetch_refreshes_each_stream_with_its_own_new_timestamp(self):
  stamps=[]
  for number in range(2):
   with RunJournal(self.root,'sources',f'unchanged_{number}') as run:
    for sid in [A,B]:fetch(URL,lambda:('identical official document',None),version='v1',source_id=sid,identity=sid)
    stamps.append({row['sourceId']:row['lastSuccessAt'] for row in run.data['sources'].values()})
    if number:
     self.assertEqual({row['outcome'] for row in run.data['sources'].values()},{'unchanged'})
    run.finish('success')
  for sid in [A,B]:self.assertGreater(stamps[1][sid],stamps[0][sid])
 def test_failure_does_not_borrow_another_stream_success_and_retry_is_scoped(self):
  with RunJournal(self.root,'sources','mixed') as run:
   fetch(URL,lambda:('valid document',None),version='v1',source_id=A,identity=A)
   fetch(URL,lambda:(None,'JSON 结构非法'),version='v1',source_id=B,identity=B)
   run.data['selectedSources']=[source_key(URL,B)];self.assertFalse(wanted(URL,A));self.assertTrue(wanted(URL,B));run.finish('partial')
  state=read(self.root,'data/normalized/source-runtime.json');self.assertIsNone(state[source_key(URL,B)]['lastSuccessAt'])
  index=SourceStatusIndex({},REGISTRY,state);self.assertEqual(index.status_of(A)['state'],'ok');self.assertEqual(index.status_of(B)['state'],'failing')
 def test_recovery_and_offline_preview_keep_each_original_observation_time(self):
  try:
   with RunJournal(self.root,'sources','recover_shared') as run:
    fetch(URL,lambda:('document A',None),version='v1',source_id=A,identity=A)
    fetch(URL,lambda:('document B',None),version='v1',source_id=B,identity=B)
    original=copy.deepcopy(run.data['sources']);raise RuntimeError('crash')
  except RuntimeError:pass
  with RunJournal(self.root,'sources','recover_shared',recover=True) as run:
   for sid in [A,B]:
    value,_=fetch(URL,lambda:self.fail('recovery must not fetch'),version='v1',source_id=sid,identity=sid)
    self.assertEqual(value,'document '+('A' if sid==A else 'B'))
    self.assertEqual(run.data['sources'][source_key(URL,sid)]['lastSuccessAt'],original[source_key(URL,sid)]['lastSuccessAt'])
   run.finish('success');saved=copy.deepcopy(run.data['sources'])
  before=(self.root/'data/normalized/source-runtime.json').read_bytes()
  with RunJournal(self.root,'sources','offline_shared') as run:
   run.data.update(offline=True,sources=saved)
   for sid in [A,B]:fetch(URL,lambda:self.fail('offline fetch'),version='v1',source_id=sid,identity=sid)
   self.assertEqual((self.root/'data/normalized/source-runtime.json').read_bytes(),before);run.finish('success')
 def test_legacy_snapshot_reuse_is_limited_to_its_recorded_identity(self):
  try:
   with RunJournal(self.root,'sources','legacy') as run:
    fetch(URL,lambda:('legacy document',None),version='v1',source_id=A)
    stamp=run.data['sources'][source_key(URL)]['lastSuccessAt'];raise RuntimeError('crash')
  except RuntimeError:pass
  with RunJournal(self.root,'sources','legacy',recover=True) as run:
   self.assertEqual(fetch(URL,lambda:self.fail('old identity refetched'),version='v1',source_id=A,identity=A)[0],'legacy document')
   self.assertEqual(run.data['sources'][source_key(URL)]['lastSuccessAt'],stamp)
   fetch(URL,lambda:(None,'JSON 结构非法'),version='v1',source_id=B,identity=B)
   self.assertIsNone(run.data['sources'][source_key(URL,B)].get('lastSuccessAt'));run.finish('partial')
 def test_failed_first_scoped_attempt_preserves_only_same_identity_legacy_success(self):
  with RunJournal(self.root,'sources','old_success') as run:
   fetch(URL,lambda:('same identity successful document',None),version='v1',source_id=A);run.finish('success')
  original=read(self.root,'data/normalized/source-runtime.json')[source_key(URL)]['lastSuccessAt']
  with RunJournal(self.root,'sources','new_failed') as run:
   fetch(URL,lambda:(None,'JSON 结构非法'),version='v1',source_id=A,identity=A);run.finish('failed')
  row=read(self.root,'data/normalized/source-runtime.json')[source_key(URL,A)]
  self.assertEqual(row['outcome'],'failed');self.assertEqual(row['lastSuccessAt'],original)
 def test_historical_context_wins_and_ambiguous_url_does_not_invent_stream(self):
  daily={'days':[{'date':'2026-10-31','changed':[{'platform':'Example','source_type':'blog','url':URL}],'failed':[{'platform':'Example','source_type':'changelog','url':URL}]}]}
  for registry in [REGISTRY,list(reversed(REGISTRY))]:
   index=SourceStatusIndex(daily,registry);self.assertEqual(index.status_of(A)['state'],'ok');self.assertEqual(index.status_of(B)['state'],'failing')
   unknown=SourceStatusIndex({'days':[{'date':'2026-10-31','changed':[{'url':URL}]}]},registry)
   self.assertEqual(unknown.status_of(A)['state'],'unknown');self.assertEqual(unknown.status_of(B)['state'],'unknown')
 def test_all_live_platform_slots_resolve_their_own_registry_identity(self):
  config=json.loads((ROOT/'pipeline/config/maas_official_sources.json').read_text());registry=json.loads((ROOT/'pipeline/config/source_registry.json').read_text())['sources']
  for platform in config['platforms']:
   for kind in module.P0_KEYS+module.P1_KEYS:
    url=platform['sources'].get(kind)
    if not url:continue
    expected=next(row['source_id'] for row in registry if row.get('display_name')==platform['name'] and row.get('source_type')==kind)
    self.assertEqual(module.resolve_source_id(url,platform['name'],kind),expected)
  with self.assertRaises(ValueError):module.resolve_source_id('https://mistral.ai/news/')
if __name__=='__main__':unittest.main()
