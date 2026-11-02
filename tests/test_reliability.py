import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'ops'))
from runtime_safety import accepts_runtime,publication_identity,wait_runtime,capacity_budget,CapacityError,require_capacity,GIB
from pipeline_monitor import RunJournal,export_sources
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
 def test_candidate_acceptance_uses_full_publication_not_public_manifest(self):
  with tempfile.TemporaryDirectory() as tmp:
   shared=Path(tmp).resolve();(shared/'public-data/v1').mkdir(parents=True);store=shared/'data-store';(store/'writer').mkdir(parents=True)
   pointer=shared/'public-data/v1/publication.json';pointer.write_text(json.dumps(MANIFEST));(shared/'runtime.json').write_text(json.dumps({'port':8788}))
   candidate=shared/'public-data/candidates'/('e'*32);candidate.mkdir(parents=True)
   expected=copy.deepcopy(MANIFEST);expected['site']['inputVersion']='in_'+'d'*64
   (candidate/'manifest.json').write_text(json.dumps({'datasetVersion':expected['datasetVersion']}));(candidate/'publication.json').write_text(json.dumps(expected))
   (store/'writer/candidate.json').write_text(json.dumps({'candidate':'/public/candidates/'+candidate.name}))
   def docker(root,mode,body):
    if mode=='publish':pointer.write_text(json.dumps(expected))
   journal=RunJournal(shared,CODE,'rebuild')
   with patch.object(launch,'SHARED',shared),patch.object(launch,'STORE',store),patch.object(launch,'wait_runtime',return_value=healthy()) as wait,patch.object(launch,'require_capacity'),patch.object(launch,'docker',side_effect=docker),patch.object(launch,'candidate_permissions'),patch.object(launch,'command'):
    launch.execute(Path('/runtime')/CODE,'rebuild',b'{}',journal)
    self.assertEqual(wait.call_args.args,(8788,expected,CODE));self.assertTrue(journal.published);self.assertEqual(journal.validation,'passed')
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
 def test_monitor_export_preserves_immutable_runtime_inventory(self):
  import hashlib,shutil
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();package=root/'runtime'/CODE;tooling=package/'tooling';shared=root/'shared'
   (tooling/'scripts').mkdir(parents=True);(tooling/'pipeline/config').mkdir(parents=True)
   (shared/'data-store/writer/data').mkdir(parents=True)
   shutil.copy2(BASE/'scripts/monitor-collect.py',tooling/'scripts/monitor-collect.py')
   (tooling/'pipeline/config/source_registry.json').write_text(json.dumps({'sources':[]}))
   (tooling/'pipeline/config/public_providers.json').write_text(json.dumps({'sourceToProvider':{},'pricingSourceKeyToSourceId':{}}))
   def inventory():return {str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*') if p.is_file()}
   original=inventory()
   # Exercise the real collector twice, as startup/failure/retry exports do.
   for _ in range(2):
    result=export_sources(shared,package)
    self.assertEqual(result['runs'],0);self.assertEqual(inventory(),original)
   self.assertFalse(list(package.rglob('__pycache__')))
 def test_daily_receipt_survives_rebuild_and_retains_actual_failure_stage(self):
  with tempfile.TemporaryDirectory() as tmp:
   shared=Path(tmp).resolve();journal=RunJournal(shared,CODE,'update',{'GITHUB_REPOSITORY':'owner/repo','GITHUB_RUN_ID':'123'})
   def fail():raise RuntimeError('private upstream error')
   with self.assertRaises(RuntimeError):journal.phase('capacity-preflight',fail)
   journal.finish(RuntimeError('private error'))
   daily=shared/'pipeline-monitor/daily.json';original=daily.read_bytes();value=json.loads(original)
   self.assertEqual(value['failureStage'],'capacity-preflight');self.assertEqual(value['state'],'failed')
   self.assertEqual(value['runLink'],'https://github.com/owner/repo/actions/runs/123');self.assertNotIn('private',original.decode())
   rebuild=RunJournal(shared,CODE,'rebuild');rebuild.finish()
   self.assertEqual(daily.read_bytes(),original)
   self.assertEqual(json.loads((daily.parent/'current.json').read_text())['mode'],'rebuild')
 def test_alert_environment_is_scoped_and_daily_bootstrap_preserves_timestamp(self):
  from types import SimpleNamespace
  spec=importlib.util.spec_from_file_location('install_alerts',BASE/'ops/install-reliability.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();(root/'shared/state').mkdir(parents=True);(root/'shared/pipeline-monitor').mkdir()
   (root/'shared/agent.env').write_text('RESEND_API_KEY="test-key"\nMAAS_MAIL_FROM="MaaS <mail@example.com>"\nDB_PASSWORD="never-copy"\n')
   body=installer.alert_environment(root,'operator@example.com').decode()
   self.assertEqual({line.split('=')[0] for line in body.splitlines()},{'RESEND_API_KEY','MAAS_MAIL_FROM','MAAS_DATA_ALERT_TO'})
   self.assertNotIn('never-copy',body)
   with self.assertRaises(ValueError):installer.alert_environment(root,'operator@example.com\nOTHER=value')
   current=root/'shared/pipeline-monitor/current.json';current.write_text(json.dumps({'mode':'update','updatedAt':12345}))
   with patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=123,pw_gid=456)),patch.object(installer.os,'chown'):
    installer.prepare_alert_state(root);daily=current.with_name('daily.json')
    self.assertEqual(json.loads(daily.read_text())['updatedAt'],12345);self.assertEqual(daily.stat().st_mode&0o777,0o640)
    self.assertEqual((root/'shared/state/data-alerts').stat().st_mode&0o777,0o700)
    current.write_text(json.dumps({'mode':'rebuild','updatedAt':99999}));installer.prepare_alert_state(root)
    self.assertEqual(json.loads(daily.read_text())['updatedAt'],12345)
    daily.unlink();daily.symlink_to(current)
    with self.assertRaises(ValueError):installer.prepare_alert_state(root)
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
 def test_worker_receipt_directory_has_scoped_ownership_and_rejects_links(self):
  from types import SimpleNamespace
  spec=importlib.util.spec_from_file_location('install_worker_state',BASE/'ops/install-reliability.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);parent=root/'shared/state';parent.mkdir(parents=True);parent.chmod(0o755)
   with patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=123,pw_gid=456)),patch.object(installer.os,'chown') as chown:
    installer.prepare_worker_state(root)
    directory=parent/'worker-runtime';self.assertEqual(directory.stat().st_mode&0o777,0o750);self.assertEqual(parent.stat().st_mode&0o777,0o755)
    chown.assert_called_once_with(directory,123,456)
    directory.rmdir();directory.symlink_to(root)
    with self.assertRaises(ValueError):installer.prepare_worker_state(root)
if __name__=='__main__':unittest.main()
