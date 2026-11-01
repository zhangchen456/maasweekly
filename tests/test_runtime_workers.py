import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'ops'))
import runtime_workers as workers
import test_runtime_control as legacy
control=legacy.control

class WorkerSwitchTests(unittest.TestCase):
 def setUp(self):
  legacy.RuntimeControlTests.setUp(self)
  for code in ['a'*10,'b'*10]:
   p=self.root/'runtime'/code/'metadata';p.mkdir(parents=True);(p/'runtime-manifest.json').write_text(json.dumps({'components':{'workerProtocol':1}}))
  (self.root/'current').unlink();(self.root/'current').symlink_to(self.root/'runtime'/('b'*10))
  (self.shared/'runtime.json').write_text(json.dumps({'code':'b'*10,'slot':'green','port':8789}))
  self.drain=patch.object(workers,'drain');self.start=patch.object(workers,'start_and_verify',return_value={'editorial':{'code':'a'*10},'diagnostic':{'code':'a'*10}})
  self.drain_mock=self.drain.start();self.start_mock=self.start.start();self.addCleanup(self.drain.stop);self.addCleanup(self.start.stop)
 # Inherited generic tests use a legacy fixture. Exercise worker transitions separately.
 def test_worker_failure_recovers_pointer_and_restarts_old_workers(self):
  self.start_mock.side_effect=[RuntimeError('not ready'),{}]
  with patch.object(control,'run'),self.assertRaises(RuntimeError):control.activate('a'*10)
  self.assertEqual((self.root/'current').resolve(),self.root/'runtime'/('b'*10))
  self.assertEqual(json.loads((self.shared/'runtime.json').read_text())['code'],'b'*10)
  self.assertEqual(self.start_mock.call_args.args[1],self.root/'runtime'/('b'*10))
  self.assertEqual(self.drain_mock.call_count,2)
  self.assertFalse((self.shared/'runtime-switch-pending.json').exists())
 def test_pending_survives_failed_recovery(self):
  self.start_mock.side_effect=RuntimeError('failure')
  with patch.object(control,'run'),self.assertRaises(RuntimeError):control.activate('a'*10)
  self.assertTrue((self.shared/'runtime-switch-pending.json').exists())
 def test_actual_identity_is_committed_only_after_worker_ready(self):
  def ready(root,package):
   self.assertTrue((self.shared/'runtime-switch-pending.json').exists());self.assertEqual((root/'current').resolve(),package)
   return {'editorial':{'pid':123,'code':package.name},'diagnostic':{'pid':124,'code':package.name}}
  self.start_mock.side_effect=ready
  with patch.object(control,'run'):result=control.activate('a'*10)
  self.drain_mock.assert_called_once();self.assertEqual(result['workers']['editorial']['pid'],123)
  self.assertEqual(json.loads((self.shared/'runtime.json').read_text())['workers'],result['workers'])

class WorkerDrainTests(unittest.TestCase):
 def test_drain_timeout_never_issues_stop_or_kill9(self):
  with patch.object(workers,'state',return_value={'MainPID':'42'}),patch.object(workers.subprocess,'run') as run:
   with self.assertRaises(RuntimeError):workers.drain(timeout=0)
   self.assertEqual(run.call_count,2)
   for call in run.call_args_list:
    self.assertIn('--signal=SIGTERM',call.args[0]);self.assertNotIn('stop',call.args[0])
 def test_inactive_workers_need_no_signal(self):
  with patch.object(workers,'state',return_value={'MainPID':'0'}),patch.object(workers.subprocess,'run') as run:workers.drain();run.assert_not_called()
 def test_active_wrong_version_cannot_pass(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'runtime'/'a';(p/'metadata').mkdir(parents=True);(p/'metadata/runtime-manifest.json').write_text('{"components":{"workerProtocol":1}}')
   with patch.object(workers,'state',return_value={'MainPID':'999999999','ActiveState':'active'}),patch.object(workers.subprocess,'run'):
    with self.assertRaises(RuntimeError):workers.start_and_verify(root,p,timeout=0)

if __name__=='__main__':unittest.main()
