"""Daily publication SLA, durable incident lifecycle and exactly keyed mail retries."""
import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import daily_data_alert as alert

SENDER='MaaS Daily <hello@example.com>'
TO='operator@example.com'
def epoch(value):return datetime.fromisoformat(value).replace(tzinfo=alert.ZONE).timestamp()
NOW=epoch('2026-11-02T13:15:00')

def sample(now=NOW):
    daily={'id':'pipeline_'+'a'*32,'state':'succeeded','mode':'update','stage':'finished','failureStage':None,
           'startedAt':int((now-3600)*1000),'updatedAt':int((now-60)*1000)}
    return dict(checkedAt=now,today=alert.day(now),dataThrough=alert.day(now),consistent=True,sourcesHealthy=True,
                githubKnown=True,githubError=False,runtimeError=False,inputError=False,jobAlive=False,
                daily=daily,current=copy.deepcopy(daily),github=dict(id=123,status='completed',conclusion='success',createdAt=now-3600,updatedAt=now-60))

class Mailer:
    def __init__(self,error=None):self.calls=[];self.error=error
    def send(self,key,mail):
        self.calls.append((key,copy.deepcopy(mail)))
        if self.error:raise self.error
        return 'accepted-id'

class DailyAlerts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name).resolve()/'state';self.store=alert.AlertStore(self.path)
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def observe(self,s,**kw):return self.store.observe(s,SENDER,TO,**kw)
    def jobs(self):return [dict(row) for row in self.store.db.execute('SELECT * FROM jobs ORDER BY rowid')]
    def failed(self):
        s=sample();s['daily']['state']='failed';s['current']=copy.deepcopy(s['daily']);s['github']['conclusion']='failure';return s
    def healthy_after(self):
        s=sample(NOW+300);s['current']['updatedAt']=int((NOW+100)*1000);return s
    def test_beijing_deadline_and_old_success_do_not_disguise_stale_data(self):
        for timestamp,late in [('2026-11-02T07:00:00',False),('2026-11-02T12:59:59',False),('2026-11-02T13:00:00',True)]:
            s=sample(epoch(timestamp));s['dataThrough']='2026-11-01'
            self.assertEqual('publication_late' in alert.conditions(s),late)
        s=sample();s['dataThrough']='2026-11-01';s['current']['mode']='rebuild'
        self.assertIn('publication_late',alert.conditions(s))
    def test_workflow_failure_before_server_run_is_detected(self):
        s=sample();s['daily']['updatedAt']=int((NOW-1000)*1000);s['current']=copy.deepcopy(s['daily'])
        s['github']['conclusion']='failure';s['github']['updatedAt']=NOW-10
        self.assertIn('workflow_failed',self.observe(s)['alerts']);self.assertEqual(len(self.jobs()),1)
    def test_healthy_is_quiet_and_transient_checks_are_debounced(self):
        self.assertEqual(self.observe(sample())['queued'],0)
        s=sample();s['runtimeError']=True
        self.assertEqual(self.observe(s)['queued'],0)
        self.assertIn('runtime_unavailable',self.observe(s)['alerts'])
        self.assertEqual(self.observe(sample())['queued'],0)
    def test_github_outage_requires_three_checks(self):
        s=sample();s.update(githubError=True,githubKnown=False)
        self.assertEqual(self.observe(s)['queued'],0);self.assertEqual(self.observe(s)['queued'],0)
        self.assertEqual(self.observe(s)['alerts'],['github_check_unavailable'])
    def test_dead_process_and_running_time_limits(self):
        s=sample();s['daily']['state']='running';s['jobAlive']=False
        self.assertIn('task_interrupted',alert.conditions(s))
        s['jobAlive']=True;s['daily']['startedAt']=int((NOW-100*60-1)*1000)
        self.assertIn('task_timeout',alert.conditions(s))
        s=sample();s['github'].update(status='queued',createdAt=NOW-110*60-1)
        self.assertIn('task_timeout',alert.conditions(s))
    def test_old_failure_is_superseded_only_by_later_verified_publication(self):
        s=self.failed();s['current']['state']='succeeded';s['current']['updatedAt']=int(NOW*1000)
        self.assertNotIn('task_failed',alert.conditions(s));self.assertNotIn('workflow_failed',alert.conditions(s))
        s['dataThrough']='2026-11-01';self.assertIn('task_failed',alert.conditions(s))
    def test_restart_deduplicates_and_new_reason_escalates_once(self):
        s=self.failed();self.observe(s);mailer=Mailer();self.store.deliver(mailer,NOW)
        self.store.close();self.store=alert.AlertStore(self.path)
        for _ in range(3):self.assertEqual(self.observe(s)['queued'],0)
        s['dataThrough']='2026-11-01';self.assertEqual(self.observe(s)['queued'],1)
        self.assertEqual(self.observe(s)['queued'],0);self.assertEqual(len(self.jobs()),2)
    def test_retry_does_not_recover_then_two_terminal_healthy_checks_do(self):
        self.observe(self.failed());self.store.deliver(Mailer(),NOW)
        s=sample(NOW+300);s['daily']['state']='running';s['jobAlive']=True;s['current']=copy.deepcopy(s['daily']);s['github']['status']='in_progress'
        for _ in range(3):self.assertTrue(self.observe(s)['episodeOpen'])
        s=self.healthy_after();self.assertEqual(self.observe(s)['queued'],0)
        self.assertEqual(self.observe(s)['queued'],1);self.assertFalse(self.store.load()['episode'])
        self.assertEqual(self.observe(s)['queued'],0)
        self.assertEqual([j['kind'] for j in self.jobs()],['alert','recovery'])
    def test_missing_new_terminal_success_prevents_premature_recovery(self):
        self.observe(self.failed());s=sample(NOW+300)
        s['current']['updatedAt']=int((NOW-100)*1000);s['github']['updatedAt']=NOW-100
        for _ in range(3):self.assertTrue(self.observe(s)['episodeOpen'])
    def test_healthy_next_day_does_not_resolve_yesterday_with_old_data(self):
        s=self.failed();self.observe(s)
        h=sample(epoch('2026-11-03T06:00:00'));h['dataThrough']='2026-11-01'
        for _ in range(3):self.assertTrue(self.observe(h)['episodeOpen'])
    def test_unsent_alert_is_cancelled_without_phantom_recovery(self):
        self.observe(self.failed());h=self.healthy_after();self.observe(h);self.observe(h)
        self.assertEqual([j['status'] for j in self.jobs()],['cancelled'])
        self.assertEqual(self.store.deliver(Mailer(),NOW+600)['accepted'],0)
    def test_timeout_retry_freezes_payload_key_and_recovers_unknown_acceptance(self):
        self.observe(self.failed());m=Mailer(alert.MailFailure('timeout_or_unknown',True));self.store.deliver(m,NOW)
        self.store.deliver(m,NOW+300);self.assertEqual(m.calls[0],m.calls[1])
        h=self.healthy_after();self.observe(h);self.observe(h)
        self.assertEqual([j['kind'] for j in self.jobs()],['alert','recovery']);self.assertEqual(self.jobs()[0]['status'],'cancelled')
    def test_unknown_acceptance_stops_before_provider_idempotency_expires(self):
        self.observe(self.failed());m=Mailer(alert.MailFailure('timeout_or_unknown',True));self.store.deliver(m,NOW)
        result=self.store.deliver(m,NOW+23*3600);self.assertEqual(result['review'],1);self.assertEqual(len(m.calls),1)
    def test_process_crash_marks_attempt_uncertain_before_network(self):
        self.observe(self.failed())
        class Crash:
            def send(inner,*args):
                self.assertEqual(self.jobs()[0]['uncertain'],1)
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.store.deliver(Crash(),NOW)
        self.assertEqual(self.store.deliver(Mailer(),NOW+23*3600)['review'],1)
    def test_explicit_rejection_can_safely_retry(self):
        self.observe(self.failed());m=Mailer(alert.MailFailure('provider_rejected',False));self.store.deliver(m,NOW)
        self.assertEqual(self.jobs()[0]['uncertain'],0)
        self.assertEqual(self.store.deliver(Mailer(),NOW+24*3600)['accepted'],1)
    def test_recipient_change_cancels_old_queue_and_realerts_new_recipient(self):
        s=self.failed();self.observe(s);self.store.observe(s,SENDER,'new@example.com')
        self.assertEqual([j['status'] for j in self.jobs()],['cancelled','pending'])
        self.assertEqual(json.loads(self.jobs()[1]['payload'])['to'],['new@example.com'])
    def test_recurrence_cancels_queued_recovery(self):
        self.observe(self.failed());self.store.deliver(Mailer(),NOW)
        h=self.healthy_after();self.observe(h);self.observe(h);s=self.failed();s['checkedAt']=NOW+600
        self.observe(s);self.assertEqual(self.jobs()[1]['status'],'cancelled');self.assertEqual(len(self.jobs()),3)
    def test_mail_contains_only_allowlisted_metadata_and_rehearsal_is_explicit(self):
        s=self.failed();s['rawError']='secret-token-original-text';s['daily']['failureStage']='capacity-preflight'
        self.observe(s,rehearsal=True);mail=json.loads(self.jobs()[0]['payload'])
        self.assertIn('[MaaSDaily] [演练]',mail['subject']);self.assertIn('Asia/Shanghai',mail['text'])
        self.assertIn('capacity-preflight',mail['text']);self.assertNotIn('secret-token',json.dumps(mail))
    def test_provider_requires_valid_acceptance_and_stable_idempotency_key(self):
        class Fake:
            def request(inner,url,**kw):
                self.assertEqual(url,'https://api.resend.com/emails');self.assertEqual(kw['headers']['Idempotency-Key'],'frozen-key')
                self.assertEqual(kw['timeout'],15);return {'id':'provider-id'}
        mailer=alert.ResendMailer({'RESEND_API_KEY':'test-only','MAAS_MAIL_FROM':SENDER,'MAAS_DATA_ALERT_TO':TO},Fake())
        self.assertEqual(mailer.send('frozen-key',{'text':'test'}),'provider-id')
        with patch.object(mailer.transport,'request',return_value={}):
            with self.assertRaises(alert.MailFailure) as error:mailer.send('frozen-key',{})
            self.assertTrue(error.exception.uncertain)
    def test_file_symlinks_and_oversized_metadata_are_refused(self):
        file=self.path/'metadata';file.write_text('{}');link=self.path/'link';link.symlink_to(file)
        with self.assertRaises(OSError):alert.read_json(link)
        with self.assertRaises(ValueError):alert.read_json(file,1)
        with self.assertRaises(ValueError):alert.AlertStore(link)
    @patch.object(alert,'system_snapshot',return_value={'issues':[]})
    def test_collect_checks_exact_runtime_and_publication_cohort(self,_snapshot):
        root=Path(self.tmp.name).resolve();(root/'pipeline-monitor').mkdir();(root/'public-data/v1').mkdir(parents=True)
        job={**sample()['daily'],'schemaVersion':1}
        (root/'pipeline-monitor/current.json').write_text(json.dumps(job));(root/'pipeline-monitor/daily.json').write_text(json.dumps(job))
        (root/'runtime.json').write_text(json.dumps({'port':8788,'code':'code'}))
        pub={'datasetVersion':'ds_test','site':{'inputVersion':'in_test','codeCommit':'code','formatVersion':1}}
        (root/'public-data/v1/publication.json').write_text(json.dumps(pub));identity={**pub['site'],'datasetVersion':'ds_test'}
        values=[{'ready':True,'processCode':'code','publication':identity,'dataThrough':'2026-11-02','freshness':{'freshness':'fresh'}},
                {'dataThrough':'2026-11-02','datasetVersion':'ds_test'},
                {'workflow_runs':[{'id':123,'status':'completed','conclusion':'success','created_at':'2026-11-01T21:00:00Z','updated_at':'2026-11-01T22:00:00Z'}]}]
        class Fake:
            def request(inner,url,**kw):return values.pop(0)
        s=alert.collect(NOW,Fake(),root);self.assertEqual(alert.conditions(s),{});self.assertTrue(s['githubKnown'])
    @patch.object(alert,'system_snapshot',return_value={'issues':[]})
    def test_malformed_inputs_become_monitor_alerts_without_crashing(self,_snapshot):
        class Fake:
            def request(inner,*args,**kw):return []
        s=alert.collect(NOW,Fake(),Path(self.tmp.name).resolve())
        self.assertTrue(s['inputError']);self.assertTrue(s['runtimeError']);self.assertTrue(s['githubError'])
        self.assertIn('publication_late',alert.conditions(s))

if __name__=='__main__':unittest.main()
