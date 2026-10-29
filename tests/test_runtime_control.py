import importlib.util,json,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runtime_control',BASE/'ops/runtime-control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
class RuntimeControlTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.shared=self.root/'shared';self.shared.mkdir()
  self.files=[self.shared/str(n) for n in range(4)]
  payloads=['root OLD;','upstream agent_api { server OLD; }','location = /feed.xml { types { } try_files $uri =404; }\nlocation = /feed/weekly.xml { types { } try_files $uri =404; }','location / {\ntry_files $uri $uri/ =404;\n}']
  for f,body in zip(self.files,payloads):f.write_text(body)
  self.before=[p.read_bytes() for p in self.files];(self.root/'current').symlink_to('releases/old')
  (self.shared/'runtime-candidate.json').write_text(json.dumps({'code':'a'*10,'slot':'blue','port':8788,'datasetVersion':'ds_test'}))
  self.patches=[patch.object(control,'ROOT',self.root),patch.object(control,'SHARED',self.shared),patch.object(control,'FILES',self.files),patch.object(control,'probe',return_value='ds_test')]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def test_stage_exposes_only_public_client_assets_to_nginx(self):
  package=self.root/'runtime'/('a'*10);server=package/'site/dist/server';server.mkdir(parents=True);(server/'entry.mjs').write_text('code');server.chmod(0o750)
  client=package/'site/dist/client';client.mkdir();icon=client/'favicon.svg';icon.write_text('icon');icon.chmod(0o640)
  with patch.object(control,'run'):control.stage('a'*10)
  self.assertEqual(icon.stat().st_mode&0o777,0o644);self.assertEqual(client.stat().st_mode&0o777,0o755);self.assertEqual(server.stat().st_mode&0o777,0o750)
 def test_nginx_failure_restores_all_includes_and_keeps_old_pointer(self):
  attempts=0
  def run(*args):
   nonlocal attempts
   if args==('nginx','-t'):
    attempts+=1
    if attempts==1:raise subprocess.CalledProcessError(1,args)
  with patch.object(control,'run',side_effect=run):
   with self.assertRaises(subprocess.CalledProcessError):control.activate('a'*10)
  self.assertEqual([p.read_bytes() for p in self.files],self.before)
  self.assertEqual((self.root/'current').readlink(),Path('releases/old'))
  self.assertFalse((self.shared/'runtime-mode').exists())
 def test_success_switches_both_routes_and_pointer_and_preserves_recovery(self):
  with patch.object(control,'run'):result=control.activate('a'*10)
  self.assertEqual(result['status'],'active');self.assertTrue((self.shared/'runtime-mode').exists())
  self.assertIn(b'proxy_pass http://agent_api',self.files[2].read_bytes());self.assertIn(b'8788',self.files[1].read_bytes())
  self.assertEqual((self.root/'current').resolve(),self.root/'runtime'/('a'*10))
  self.assertEqual(Path(result['recovery'],'0').read_bytes(),self.before[0])
 def test_interrupted_switch_recovers_recorded_files_and_pointer(self):
  backup=self.shared/'runtime-recovery'/'test';backup.mkdir(parents=True)
  for n,b in enumerate(self.before):(backup/str(n)).write_bytes(b)
  (backup/'current').write_text('releases/old')
  (self.shared/'runtime-switch-pending.json').write_text(json.dumps({'backup':str(backup)}))
  for f in self.files:f.write_text('partially changed')
  (self.shared/'runtime-mode').write_text('enabled')
  with patch.object(control,'run'):control.recover_pending()
  self.assertEqual([p.read_bytes() for p in self.files],self.before);self.assertFalse((self.shared/'runtime-mode').exists())
if __name__=='__main__':unittest.main()
