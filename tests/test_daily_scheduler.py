import importlib.util,json,sys,tempfile,unittest
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
