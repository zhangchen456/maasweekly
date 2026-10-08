import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
collector=load('monitor-collect');recorder=load('monitor-record')
class MonitorCollection(unittest.TestCase):
 def fixture(self,root):
  p=root/'pipeline/config';p.mkdir(parents=True)
  (p/'source_registry.json').write_text(json.dumps({'sources':[{'source_id':'example-pricing','display_name':'Example','type_label':'价格','source_type':'pricing','primary_url':'https://example.test'}]}))
  (p/'public_providers.json').write_text(json.dumps({'sourceToProvider':{'example-pricing':'example'},'pricingSourceKeyToSourceId':{'example:pricing':'example-pricing'}}))
 def write(self,root,d):
  p=root/'data/price-runs/2026-10-01/r.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d));return p
 def run_record(self):return {'runId':'r1','family':'prices','state':'committed','startedAt':'2026-10-01T00:00:00+00:00','completedAt':'2026-10-01T00:01:00+00:00','outcome':'partial','sources':{'example:pricing':{'outcome':'failed','failurePhase':'parse','errorCode':'SECRET_AUTH_ERROR','latestAttemptAt':1790812800}}}
 def test_fixed_projection_redacts_raw_errors_and_unknown_times(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);d=self.run_record();d['secret']='PRIVATE_KEY';self.write(root,d)
   batches,skipped=collector.collect(root);r=batches[0]['runs'][0];s=r['sources'][0]
   self.assertEqual(s['outcome'],'parse_failed');self.assertIsNone(s['successAt']);self.assertEqual(r['publication'],'not_run');self.assertNotIn('SECRET',json.dumps(batches));self.assertNotIn('PRIVATE_KEY',json.dumps(batches));self.assertEqual(skipped,0)
 def test_legacy_missing_time_not_backfilled_and_replay_not_live_success(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);d=self.run_record();d.update(offline=True);d['sources']['example:pricing'].update(outcome='success',lastSuccessAt=1790812800)
   self.write(root,d);r=collector.collect(root)[0][0]['runs'][0];self.assertEqual(r['sources'][0]['outcome'],'not_run');self.assertIsNone(r['sources'][0]['dataThrough'])
   d.pop('startedAt');d.pop('completedAt');self.write(root,d);self.assertEqual(collector.collect(root)[1],1)
 def test_only_existing_validation_result_not_new_price_rule(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);d=self.run_record();d['sources']['example:pricing'].update(outcome='success',validation='failed',rejectedCount=1)
   self.write(root,d);r=collector.collect(root)[0][0]['runs'][0];self.assertEqual(r['validation'],'failed');self.assertEqual(r['sources'][0]['coverage'],'partial');self.assertEqual(r['sources'][0]['errorCode'],'validation_failed')
 def test_deterministic_repeated_collection_and_symlink_rejection(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);p=self.write(root,self.run_record());self.assertEqual(collector.collect(root),collector.collect(root));p.unlink();p.symlink_to(ROOT/'pipeline/config/source_registry.json');self.assertRaises(ValueError,collector.collect,root)
 def test_mutable_journals_not_imported(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);d=self.run_record();d['state']='running';self.write(root,d);self.assertEqual(collector.collect(root)[1],1)
 def test_wrapper_preserves_exit_no_raw_error_and_never_arbitrary_shell(self):
  with tempfile.TemporaryDirectory() as t:
   with patch.dict('os.environ',{'MAAS_MONITOR_OUTPUT':t},clear=True),patch.object(recorder.subprocess,'call',return_value=7) as execute,patch('sys.argv',['monitor-record.py','public-validation']):
    self.assertEqual(recorder.main(),7);self.assertEqual(execute.call_args.args[0],['python3','pipeline/scripts/export-public-data.py','--check'])
    r=json.loads(next(Path(t).glob('*.json')).read_text());self.assertEqual(r['state'],'failed');self.assertEqual(r['validation'],'failed');self.assertEqual(r['publication'],'not_run');self.assertEqual(r['errorCode'],'validation_failed')
 def test_release_completed_only_after_fixed_online_verify(self):
  with tempfile.TemporaryDirectory() as t:
   with patch.dict('os.environ',{'MAAS_MONITOR_OUTPUT':t,'RELEASE_ID':'rl_1234567890_123456789abc'},clear=True),patch.object(recorder.subprocess,'call',return_value=0) as execute,patch('sys.argv',['monitor-record.py','release-verify']):
    self.assertEqual(recorder.main(),0);r=json.loads(next(Path(t).glob('*.json')).read_text());self.assertEqual(r['publication'],'completed');self.assertEqual(r['outputVersion'],'rl_1234567890_123456789abc');self.assertEqual(execute.call_args.args[0],['ops/verify-release.sh','--online','--expect-release','rl_1234567890_123456789abc'])
 def test_interrupted_stage_retains_snapshot_then_success_has_original_id(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);stages=root/'stages';stages.mkdir()
   with patch.dict('os.environ',{'MAAS_MONITOR_OUTPUT':str(stages)},clear=True),patch.object(recorder.subprocess,'call',side_effect=KeyboardInterrupt),patch('sys.argv',['monitor-record.py','public-validation']):
    self.assertRaises(KeyboardInterrupt,recorder.main)
   p=next(stages.glob('*.json'));initial=json.loads(p.read_text());self.assertEqual(initial['state'],'running')
   r=collector.collect(root,stages)[0][0]['runs'][0];self.assertEqual(r['state'],'needs_review');self.assertIsNone(r['finishedAt']);self.assertNotEqual(r['id'],initial['id'])
   initial.update(state='succeeded',finishedAt=initial['startedAt']+1000,observedAt=initial['startedAt']+1000,result='success',validation='passed');p.write_text(json.dumps(initial));finished=collector.collect(root,stages)[0][0]['runs'][0];self.assertEqual(finished['id'],initial['id'])
 def test_alias_failures_not_hidden_by_successful_endpoint(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);self.fixture(root);d=self.run_record();d['sources']['alias']={'sourceId':'example-pricing','outcome':'success','lastSuccessAt':1790812801};self.write(root,d)
   r=collector.collect(root)[0][0]['runs'][0];self.assertEqual(len(r['sources']),1);self.assertEqual(r['sources'][0]['outcome'],'parse_failed');self.assertEqual(r['sources'][0]['coverage'],'partial')
if __name__=='__main__':unittest.main()
