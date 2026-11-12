import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import daily_scheduler as s
class SchedulerTests(unittest.TestCase):
 def fixture(self,root,state=None,through='2026-11-06'):
  (root/'public-data/v1').mkdir(parents=True,exist_ok=True);(root/'pipeline-monitor').mkdir(exist_ok=True)
  (root/'public-data/v1/publication.json').write_text(json.dumps({'dataThrough':through}))
  if state:(root/'pipeline-monitor/daily.json').write_text(json.dumps(state))
 def test_missing_trigger_catches_up_but_late_trigger_and_failure_never_duplicate(self):
  now=datetime(2026,11,7,6,tzinfo=s.ZONE);start=int(now.timestamp()*1000)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();self.fixture(root);self.assertEqual(s.decision(root,now),'start')
   for state in ['running','failed']:
    self.fixture(root,{'startedAt':start,'state':state});self.assertEqual(s.decision(root,now),'already_attempted')
   self.fixture(root,{'startedAt':start,'state':'succeeded'},'2026-11-07');self.assertEqual(s.decision(root,now),'already_published')
   self.fixture(root,{'startedAt':start-86400000,'state':'failed'});self.assertEqual(s.decision(root,now),'start')
   self.assertEqual(s.decision(root,now.replace(hour=14)),'outside_window')
 def test_credentials_are_opt_in_encrypted_and_no_plaintext_is_persisted(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();directory=root/'scheduler';directory.mkdir();keys={'LLM_API_KEY':'secret-digest','TRANSLATION_API_KEY':'secret-translate'}
   with patch.object(s.subprocess,'run') as run:s.remember_credentials(root,keys);run.assert_not_called()
   (directory/'enabled').touch()
   with patch.object(s.subprocess,'run',return_value=type('Result',(),{'returncode':0,'stdout':b'ENCRYPTED'})()) as run:
    s.remember_credentials(root,keys);self.assertIn('secret-digest',run.call_args.kwargs['input'].decode());self.assertNotIn('secret',str(run.call_args.args))
   self.assertEqual((directory/'credentials.enc').read_bytes(),b'ENCRYPTED')
   self.assertEqual((directory/'credentials.enc').stat().st_mode&0o777,0o600)
   with self.assertRaises(ValueError):s.remember_credentials(root,{})
 def test_publisher_can_accept_delayed_github_after_local_trigger_window(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();self.fixture(root)
   self.assertEqual(s.decision(root,datetime(2026,11,7,14,tzinfo=s.ZONE),enforce_window=False),'start')
 def test_scheduled_request_uses_the_same_independent_job_unit_as_ci(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();shared=root/'shared';shared.mkdir();self.fixture(shared)
   directory=shared/'scheduler';directory.mkdir();(directory/'enabled').touch();(directory/'credentials.enc').write_bytes(b'ENCRYPTED')
   (root/'locks').mkdir();(root/'locks/release.lock').touch()
   secrets={'LLM_API_KEY':'PRIVATE-digest','TRANSLATION_API_KEY':'PRIVATE-translate'}
   results=[type('R',(),{'returncode':0,'stdout':json.dumps(secrets).encode()})(),type('R',(),{'returncode':0})()]
   with patch.object(s,'ROOT',root),patch.object(s.sys,'argv',['daily_scheduler.py']),patch.object(s,'decision',return_value='start'),patch.object(s.pwd,'getpwnam',return_value=type('P',(),{'pw_gid':os.getgid()})()),patch.object(s.subprocess,'run',side_effect=results) as run:
    s.main()
   args=run.call_args_list[-1]
   self.assertEqual(args.args[0],['/bin/bash','/usr/local/lib/maasweekly/data-job.sh']);self.assertEqual(args.kwargs['timeout'],6000)
   self.assertEqual(json.loads(args.kwargs['input'])['runContext']['GITHUB_EVENT_NAME'],'server_schedule')
   self.assertNotIn('PRIVATE',str(args.args))
   self.assertTrue(all(b'PRIVATE' not in p.read_bytes() for p in shared.rglob('*') if p.is_file()))
 def test_check_mode_never_reconciles_or_decrypts(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();shared=root/'shared';shared.mkdir();self.fixture(shared)
   directory=shared/'scheduler';directory.mkdir();(directory/'enabled').touch()
   with patch.object(s,'ROOT',root),patch.object(s.sys,'argv',['daily_scheduler.py','--check']),patch.object(s,'reconcile_interrupted') as reconcile,patch.object(s.subprocess,'run') as run:
    s.main()
   reconcile.assert_not_called();run.assert_not_called()
