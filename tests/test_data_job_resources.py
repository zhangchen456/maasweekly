"""Fault-path tests use fixture memory samples and disposable local child processes."""
import importlib.util,json,os,signal,stat,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'ops'))
import data_job_resources as r
import pipeline_monitor as pm

class ResourceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();(self.root/'shared').mkdir()
 def guard(self,sample=None,clock=None):
  read=Path.read_text
  def text(path,*a,**kw):
   if str(path)=='/sys/fs/cgroup/cgroup.controllers':return 'cpu io memory pids'
   return read(path,*a,**kw)
  with patch.object(r,'disk_device',return_value=('/dev/vda','253:0')),patch.object(Path,'read_text',text):
   return r.DataJobResources(self.root,'pipeline_'+'a'*32,sample=sample or (lambda:{'availableBytes':3*1024**3,'totalBytes':4*1024**3}),clock=clock or time.monotonic)
 def test_dynamic_budget_keeps_reserve_and_disables_container_swap(self):
  g=self.guard(lambda:{'availableBytes':1800*r.MIB,'totalBytes':4*1024**3});g.admit();args=g.container_arguments('update')
  memory=int(args[args.index('--memory')+1]);self.assertLessEqual(memory,1800*r.MIB-r.RESERVE);self.assertLessEqual(memory,r.MAX_WRITER)
  self.assertEqual(int(args[args.index('--memory-swap')+1]),memory)
  self.assertEqual(args[args.index('--device-read-bps')+1],'/dev/vda:16777216')
  self.assertEqual(args[args.index('--device-write-bps')+1],'/dev/vda:16777216')
  self.assertIn('maas.pipeline.job='+g.job_id,args)
 def test_partition_io_limit_targets_whole_device_not_partition(self):
  sysfs=self.root/'sys';devfs=self.root/'dev';devfs.mkdir();node=sysfs/'devices/block/vda';(node/'vda3').mkdir(parents=True);(node/'slaves').mkdir();(node/'dev').write_text('1:0');(node/'vda3/partition').write_text('3');(sysfs/'dev/block').mkdir(parents=True);(sysfs/'dev/block/1:3').symlink_to(node/'vda3');(devfs/'vda').touch()
  original=os.stat
  def info(path,*a,**kw):
   if Path(path)==self.root/'shared':return type('S',(),{'st_dev':os.makedev(1,3)})()
   if Path(path)==devfs/'vda':return type('S',(),{'st_mode':stat.S_IFBLK,'st_rdev':os.makedev(1,0)})()
   return original(path,*a,**kw)
  with patch.object(r.os,'stat',side_effect=info):self.assertEqual(r.disk_device(self.root/'shared',sysfs,devfs),(str(devfs/'vda'),'1:0'))
  (node/'slaves/dm').touch()
  with patch.object(r.os,'stat',side_effect=info):
   with self.assertRaisesRegex(ValueError,'layered'):r.disk_device(self.root/'shared',sysfs,devfs)
 def test_insufficient_start_never_launches_a_child(self):
  g=self.guard(lambda:{'availableBytes':r.MIN_WRITER+r.RESERVE-1,'totalBytes':4*1024**3})
  with patch.object(r.subprocess,'Popen') as start:
   with self.assertRaises(r.ResourcePressure):g.admit()
  start.assert_not_called()
 def test_transient_dip_resets_but_sustained_pressure_fails(self):
  values=iter([r.RESERVE-1,r.RESERVE+1,r.RESERVE-1,r.RESERVE-1]);g=self.guard(lambda:{'availableBytes':next(values),'totalBytes':4*1024**3})
  for _ in range(3):g.check()
  with self.assertRaises(r.ResourcePressure):g.check()
  self.assertEqual(g.state['reason'],'host_memory_headroom')
 def test_unreadable_metrics_fail_closed(self):
  g=self.guard(Mock(side_effect=OSError('private sample detail')))
  with self.assertRaisesRegex(r.ResourcePressure,'host_resource_measurement_failed'):g.check()
  self.assertNotIn('private',(g.directory/'current.json').read_text())
 def test_overall_deadline_is_not_reset_for_each_phase(self):
  now=[10.0];g=self.guard(clock=lambda:now[0]);now[0]+=r.JOB_SECONDS
  with self.assertRaisesRegex(r.ResourcePressure,'job_deadline'):g.check()
 def child(self,output):
  return [sys.executable,'-c','import os,sys,time;from pathlib import Path;Path(sys.argv[1]).write_text(str(os.getpid()));sys.stdin.buffer.read();time.sleep(30)',str(output)]
 def assert_reaped(self,path):
  if path.exists():
   with self.assertRaises(ProcessLookupError):os.kill(int(path.read_text()),0)
 def test_low_memory_stops_real_child_and_never_logs_input(self):
  values=iter([2*1024**3,100*r.MIB,100*r.MIB]);g=self.guard(lambda:{'availableBytes':next(values),'totalBytes':4*1024**3});pid=self.root/'pid';abort=Mock()
  with patch.object(r,'POLL_SECONDS',.15):
   with self.assertRaises(r.ResourcePressure):g.run(self.child(pid),input=b'PRIVATE-SECRET-ONLY-STDIN',stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,on_abort=abort)
  abort.assert_called_once();self.assert_reaped(pid);self.assertNotIn('PRIVATE-SECRET',(g.directory/'current.json').read_text())
 def test_cleanup_callback_failure_still_reaps_child(self):
  g=self.guard();pid=self.root/'pid'
  with patch.object(r,'POLL_SECONDS',.05):
   with self.assertRaises(subprocess.TimeoutExpired):g.run(self.child(pid),input=b'',timeout=.2,on_abort=Mock(side_effect=RuntimeError('cleanup')))
  self.assert_reaped(pid);self.assertTrue(g.state['cleanupNeedsReview'])
 def test_multiple_communicate_polls_do_not_resend_stdin(self):
  g=self.guard();output=self.root/'count';secret=b'x'*200000
  args=[sys.executable,'-c','import sys,time;from pathlib import Path;n=len(sys.stdin.buffer.read());time.sleep(.2);Path(sys.argv[1]).write_text(str(n))',str(output)]
  with patch.object(r,'POLL_SECONDS',.03):self.assertEqual(g.run(args,input=secret).returncode,0)
  self.assertEqual(int(output.read_text()),len(secret))
 def test_sigterm_is_caught_and_child_is_stopped(self):
  g=self.guard();pid=self.root/'pid';previous=r.install_signal_handlers();timer=threading.Timer(.2,lambda:os.kill(os.getpid(),signal.SIGTERM))
  try:
   timer.start()
   with self.assertRaises(r.JobInterrupted):g.run(self.child(pid),input=b'')
  finally:
   timer.join()
   for number,handler in previous.items():signal.signal(number,handler)
  self.assert_reaped(pid)
 def test_cgroup_limits_must_really_be_enforced(self):
  g=self.guard();g.container_arguments('resume');Path(g.container['cidfile']).write_text('b'*64);cg=self.root/'cgroup';cg.mkdir();g.cgroup=cg
  for name,value in {'memory.max':str(g.container['memoryLimitBytes']),'memory.swap.max':'0','memory.current':'100000','memory.swap.current':'0','io.max':'253:0 rbps=16777216 wbps=16777216'}.items():(cg/name).write_text(value)
  g.inspect_container();self.assertTrue(g.container['verified'])
  for name,value in [('memory.swap.max','1'),('io.max','253:0 rbps=max wbps=16777216'),('io.max','253:3 rbps=16777216 wbps=16777216')]:
   (cg/'memory.swap.max').write_text('0');(cg/name).write_text(value)
   with self.assertRaises(r.ResourcePressure):g.inspect_container()
 def test_orphan_with_wrong_owner_is_never_stopped(self):
  cid='b'*64;value={'State':{'Running':True},'Config':{'Labels':{'maas.pipeline.job':'pipeline_'+'f'*32}},'Image':'x','Name':'/maas-data-writer','Id':cid}
  with patch.object(r.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,stdout=cid),subprocess.CompletedProcess([],0,stdout=json.dumps([value]))]) as run:
   with self.assertRaises(r.ResourcePressure):r.stop_orphan_writer(self.root/'shared',{'id':'pipeline_'+'a'*32,'codeCommit':'c'*40})
  self.assertEqual(run.call_count,2)
 def test_owned_orphan_must_be_verified_stopped(self):
  cid='b'*64;job={'id':'pipeline_'+'a'*32,'codeCommit':'c'*40};value={'State':{'Running':True},'Config':{'Labels':{'maas.pipeline.job':job['id']}},'Name':'/maas-data-writer','Id':cid}
  responses=[subprocess.CompletedProcess([],0,stdout=cid),subprocess.CompletedProcess([],0,stdout=json.dumps([value])),subprocess.CompletedProcess([],0,stdout=''),subprocess.CompletedProcess([],0,stdout='')]
  with patch.object(r.subprocess,'run',side_effect=responses) as run:result=r.stop_orphan_writer(self.root/'shared',job)
  self.assertTrue(result['stopped']);self.assertEqual(run.call_args_list[2].args[0],['docker','stop','--time','10',cid])

class ReconciliationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.shared=Path(self.tmp.name).resolve();self.j=pm.RunJournal(self.shared,'c'*40,'update',now=lambda:1000);self.j.current('writer-update','running');self.pointer=self.shared/'pipeline-monitor/daily.json';self.original=self.pointer.read_bytes()
 def reconcile(self,**kw):return pm.reconcile_interrupted(self.shared,stop_orphan=lambda job:{'stopped':True},now=9000,alive=lambda job:False,**kw)
 def test_dead_attempt_gets_valid_failed_receipt_without_fake_success(self):
  checkpoint=self.shared/'checkpoint';checkpoint.write_text('unchanged')
  result=self.reconcile();v=json.loads(self.pointer.read_text());self.assertEqual(result,[{'id':self.j.id,'state':'failed'}]);self.assertEqual(v['errorCode'],'interrupted');self.assertEqual(v['failureStage'],'writer-update');self.assertEqual(checkpoint.read_text(),'unchanged')
  reports=[json.loads(p.read_text()) for p in (self.shared/'pipeline-monitor/inbox').glob('*.json')];self.assertEqual(reports[0]['batch']['runs'][0]['errorCode'],'interrupted');self.assertEqual(reports[0]['contexts'],[])
  self.assertEqual(self.reconcile(),[])
 def test_surviving_process_is_never_reconciled(self):
  stop=Mock();self.assertEqual(pm.reconcile_interrupted(self.shared,stop_orphan=stop,now=9000,alive=lambda job:True),[]);stop.assert_not_called();self.assertEqual(self.pointer.read_bytes(),self.original)
 def test_failed_orphan_cleanup_preserves_running_state_and_checkpoint(self):
  with self.assertRaises(r.ResourcePressure):pm.reconcile_interrupted(self.shared,stop_orphan=Mock(side_effect=r.ResourcePressure('unknown owner')),now=9000,alive=lambda job:False)
  self.assertEqual(self.pointer.read_bytes(),self.original)
 def test_existing_durable_terminal_receipt_wins(self):
  self.j.validation='passed';self.j.published=True;self.j.finish()
  current=self.shared/'pipeline-monitor/current.json';current.write_bytes(self.original);self.pointer.write_bytes(self.original)
  count=len(list((self.shared/'pipeline-monitor/inbox').glob('*.json')));self.reconcile();self.assertEqual(json.loads(self.pointer.read_text())['state'],'succeeded');self.assertEqual(len(list((self.shared/'pipeline-monitor/inbox').glob('*.json'))),count)
 def test_partial_publication_remains_failed(self):
  self.j.validation='passed';self.j.published=True;self.j.finish(RuntimeError('acceptance failed'))
  (self.shared/'pipeline-monitor/current.json').write_bytes(self.original);self.pointer.write_bytes(self.original)
  self.reconcile();self.assertEqual(json.loads(self.pointer.read_text())['state'],'failed')
 def test_crash_after_pointer_commit_preserves_partial_publication(self):
  self.j.input_version='in_'+'d'*64;self.j.dataset_version='ds_'+'e'*64
  self.j.phase('ssr-validation',lambda:None);self.j.current('publication','running')
  publication=self.shared/'public-data/v1/publication.json';publication.parent.mkdir(parents=True)
  publication.write_text(json.dumps({'datasetVersion':self.j.dataset_version,'site':{'inputVersion':self.j.input_version,'codeCommit':self.j.code}}))
  self.reconcile();self.assertEqual(json.loads(self.pointer.read_text())['state'],'failed')
  runs=[r for p in (self.shared/'pipeline-monitor/inbox').glob('*.json') for r in json.loads(p.read_text())['batch']['runs'] if r['id']==self.j.id+'_job']
  self.assertEqual(len(runs),1);self.assertEqual((runs[0]['state'],runs[0]['result'],runs[0]['publication']),('succeeded','partial','completed'))
 def test_unvalidated_target_does_not_claim_publication(self):
  self.j.current('publication','running');publication=self.shared/'public-data/v1/publication.json';publication.parent.mkdir(parents=True)
  publication.write_text(json.dumps({'datasetVersion':None,'site':{'inputVersion':None,'codeCommit':self.j.code}}))
  self.reconcile();runs=[r for p in (self.shared/'pipeline-monitor/inbox').glob('*.json') for r in json.loads(p.read_text())['batch']['runs']]
  self.assertEqual(runs[0]['publication'],'not_run')
 def test_boot_identity_prevents_pid_reuse(self):
  job={'pid':os.getpid(),'processStart':'42','bootId':'old-boot'}
  with patch.object(pm,'boot_id',return_value='new-boot'):self.assertFalse(pm.process_alive(job))

if __name__=='__main__':unittest.main()
