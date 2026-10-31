import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'ops'))
from runtime_safety import accepts_runtime,publication_identity,wait_runtime,capacity_budget,CapacityError,require_capacity,GIB
from pipeline_monitor import RunJournal
spec=importlib.util.spec_from_file_location('writer_launch',BASE/'ops/data-writer/launch.py');launch=importlib.util.module_from_spec(spec);spec.loader.exec_module(launch)
CODE='a'*40
MANIFEST={'datasetVersion':'ds_'+'b'*64,'site':{'inputVersion':'in_'+'c'*64,'codeCommit':CODE,'formatVersion':1}}
def healthy():return dict(schemaVersion=1,ready=True,processCode=CODE,publication=publication_identity(MANIFEST),lastReloadError=None,lastReloadAt='2026-11-01T00:00:00Z')
class ReliabilityTests(unittest.TestCase):
 def test_exact_loaded_identity_and_error_are_required(self):
  self.assertTrue(accepts_runtime(healthy(),MANIFEST,CODE))
  for field,value in [('inputVersion','in_'+'d'*64),('codeCommit','d'*40),('formatVersion',2),('datasetVersion','ds_'+'d'*64)]:
   h=healthy();h['publication'][field]=value;self.assertFalse(accepts_runtime(h,MANIFEST,CODE))
  for field,value in [('processCode','d'*40),('ready',False),('lastReloadError','failed'),('lastReloadAt',None)]:
   h=healthy();h[field]=value;self.assertFalse(accepts_runtime(h,MANIFEST,CODE))
 def test_same_dataset_old_input_times_out_then_new_input_passes(self):
  old=healthy();old['publication']['inputVersion']='in_'+'d'*64
  with self.assertRaises(RuntimeError):wait_runtime(8788,MANIFEST,CODE,timeout=0,read=lambda:old)
  self.assertEqual(wait_runtime(8788,MANIFEST,CODE,timeout=0,read=healthy),healthy())
 def test_capacity_boundaries_include_reserve_peak_and_inodes(self):
  kwargs=dict(free_bytes=20*GIB,total_bytes=40*GIB,free_inodes=500000,database_bytes=GIB,public_bytes=100000,workspace_bytes=2*GIB,workspace_files=200000,package_bytes=256*1024**2)
  for operation in ['code','update','rebuild','publish','import','prepare']:
   result=capacity_budget(operation,**kwargs);self.assertTrue(result['allowed'])
   for field,value in [('free_bytes',result['requiredFreeBytes']-1),('free_inodes',result['requiredInodes']-1)]:
    self.assertFalse(capacity_budget(operation,**{**kwargs,field:value})['allowed'])
   self.assertTrue(capacity_budget(operation,**{**kwargs,'free_bytes':result['requiredFreeBytes'],'free_inodes':result['requiredInodes']})['allowed'])
  with self.assertRaises(ValueError):capacity_budget('unknown',**kwargs)
 def test_preflight_refusal_cannot_start_writer_backup_or_publish(self):
  with tempfile.TemporaryDirectory() as tmp:
   shared=Path(tmp).resolve();(shared/'public-data/v1').mkdir(parents=True)
   (shared/'public-data/v1/publication.json').write_text(json.dumps(MANIFEST));(shared/'runtime.json').write_text(json.dumps({'port':8788}))
   journal=RunJournal(shared,CODE,'rebuild')
   with patch.object(launch,'SHARED',shared),patch.object(launch,'wait_runtime',return_value=healthy()),patch.object(launch,'require_capacity',side_effect=CapacityError('full')),patch.object(launch,'docker') as docker,patch.object(launch,'command') as command:
    with self.assertRaises(CapacityError):launch.execute(Path('/runtime')/CODE,'rebuild',b'{}',journal)
    docker.assert_not_called();command.assert_not_called()
   self.assertEqual(json.loads((shared/'public-data/v1/publication.json').read_text()),MANIFEST)
 def test_journal_preserves_published_but_failed_acceptance(self):
  with tempfile.TemporaryDirectory() as tmp:
   shared=Path(tmp).resolve();journal=RunJournal(shared,CODE,'rebuild',{'GITHUB_RUN_ID':'123','GITHUB_REPOSITORY':'owner/repo','TOKEN':'secret'})
   journal.input_version=MANIFEST['site']['inputVersion'];journal.dataset_version=MANIFEST['datasetVersion']
   journal.phase('ssr-validation',lambda:None);journal.published=True;journal.finish(RuntimeError('SECRET'))
   rows=[json.loads(p.read_text()) for p in (shared/'pipeline-monitor/inbox').glob('*.json')]
   final=next(v for v in rows if v['batch']['runs'][0]['kind']=='data-pipeline');run=final['batch']['runs'][0]
   self.assertEqual((run['result'],run['publication'],run['validation']),('partial','completed','passed'))
   self.assertEqual(final['contexts'][0]['codeCommit'],CODE);self.assertNotIn('SECRET',json.dumps(rows));self.assertNotIn('TOKEN',json.dumps(rows))
   self.assertEqual(json.loads((shared/'pipeline-monitor/current.json').read_text())['state'],'failed')
 def test_root_helper_install_is_hash_checked_and_rolls_back(self):
  import hashlib
  spec=importlib.util.spec_from_file_location('install_reliability',BASE/'ops/install-reliability.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
  for fail in [False,True]:
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp).resolve();package=root/'runtime'/CODE;(package/'tooling/ops').mkdir(parents=True);(package/'metadata').mkdir();(root/'shared').mkdir();(root/'locks').mkdir()
    (root/'current').symlink_to(package);(root/'shared/runtime.json').write_text(json.dumps({'code':CODE}))
    body=b'new helper';(package/'tooling/ops/helper.py').write_bytes(body)
    (package/'metadata/runtime-manifest.json').write_text(json.dumps({'runtimeHealthVersion':1,'files':[{'path':'tooling/ops/helper.py','sha256':hashlib.sha256(body).hexdigest()}]}))
    target=root/'helper.py';target.write_bytes(b'old helper')
    with patch.object(installer,'ROOT',root),patch.object(installer,'MAPPING',{'ops/helper.py':str(target)}),patch.object(installer.os,'geteuid',return_value=0),patch.object(installer.subprocess,'run',side_effect=[RuntimeError('reload failed'),None] if fail else None):
     if fail:
      with self.assertRaises(RuntimeError):installer.main()
      self.assertEqual(target.read_bytes(),b'old helper')
     else:
      installer.main();self.assertEqual(target.read_bytes(),body)
    self.assertEqual(next((root/'shared/reliability-install').glob('*/helper.py')).read_bytes(),b'old helper')
 def test_pr_and_release_share_gate_without_path_blind_spots(self):
  import yaml
  workflow=yaml.load((BASE/'.github/workflows/data-store-tests.yml').read_text(),Loader=yaml.BaseLoader)
  self.assertNotIn('paths',workflow['on'].get('pull_request') or {})
  self.assertIn('scripts/test-runtime.py',(BASE/'.github/workflows/data-store-tests.yml').read_text())
  self.assertIn('scripts/test-runtime.py',(BASE/'scripts/build-runtime-release.sh').read_text())
if __name__=='__main__':unittest.main()
