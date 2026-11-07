import copy
from datetime import datetime
import json
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import daily_data_alert as alert
import daily_inspection as inspection
import operations_checks as checks
from test_daily_data_alert import sample, epoch, Mailer, SENDER, TO


class InspectionTests(unittest.TestCase):
    def test_fresh_inspection_replaces_old_delivery_failure_and_catches_new_failure(self):
        for delivery,site,failed in [
            ({'status':'passed'},[{'status':'ok'}],False),
            ({'status':'failed'},[{'status':'ok'}],True),
            ({'status':'passed'},[{'status':'http_error','httpStatus':503}],True),
            ({'status':'passed'},[],True),
        ]:
            with self.subTest(delivery=delivery,site=site):
                value=sample();value['operations']={'issues':['delivery_unverified','inspection_stale','disk_pressure']}
                result=inspection.inspect(sample=value,links={'site':site},delivery=delivery)
                self.assertEqual('delivery_unverified' in result['operations']['issues'],failed)
                self.assertNotIn('inspection_stale',result['operations']['issues'])
                self.assertIn('disk_pressure',result['operations']['issues'])

    def test_known_evidence_regression_is_checked_when_entrypoints_have_no_evidence_links(self):
        record='/item/obs_'+'a'*64+'/'
        evidence=checks.EVIDENCE_REGRESSION_PATH
        calls=[]
        class Probe:
            def check(self,url,include_body=False):
                calls.append(url)
                result={'url':url,'status':'http_error' if url.endswith(evidence) else 'ok','httpStatus':503 if url.endswith(evidence) else 200}
                if include_body:
                    result['body']='<a href="'+record+'">link</a><a href="/_internal/private/">private</a>'
                return result
        result=checks.inspect_links(None,probe=Probe(),registry={'sources':[]})
        details=[r for r in result['site'] if r.get('detailSample')]
        self.assertEqual([r['httpStatus'] for r in details],[200,503])
        self.assertEqual(len(calls),len(checks.PUBLIC_PATHS)+2)
        self.assertEqual(result['detailSamplesMissing'],[])
        self.assertTrue(all('body' not in row for row in result['site']))
        self.assertFalse(any('_internal' in url for url in calls))

    def test_detail_sampling_detects_database_page_failure_without_crawling_or_private_urls(self):
        record='/item/obs_'+'a'*64+'/'
        evidence='/evidence/ev_'+'b'*64+'/'
        calls=[]
        class Probe:
            def check(self,url,include_body=False):
                calls.append(url)
                result={'url':url,'status':'http_error' if url.endswith(evidence) else 'ok','httpStatus':503 if url.endswith(evidence) else 200}
                if include_body:result['body']=''.join('<a href="'+p+'">link</a>' for p in [record,evidence,'/_internal/weekly-body/2026-11-03/',evidence+'?token=secret','//127.0.0.1/admin','/evidence/ev_'+'c'*64+'/'])
                return result
        result=checks.inspect_links(None,probe=Probe(),registry={'sources':[]})
        details=[r for r in result['site'] if r.get('detailSample')]
        self.assertEqual(len(details),2)
        self.assertEqual([r['httpStatus'] for r in details],[200,503])
        self.assertEqual(len(calls),len(checks.PUBLIC_PATHS)+2)
        self.assertEqual(result['detailSamplesMissing'],[])
        self.assertFalse(any('token' in u or '_internal' in u or '127.0.0.1' in u for u in calls))

    def test_delayed_github_start_is_tolerated_but_real_failures_are_not(self):
        value=sample(epoch('2026-11-03T12:59:59'));value['dataThrough']='2026-11-02'
        self.assertNotIn('publication_late',alert.conditions(value))
        value['github'].update(conclusion='failure',updatedAt=value['checkedAt'])
        self.assertIn('workflow_failed',alert.conditions(value))
        value['checkedAt']=epoch('2026-11-03T13:00:00')
        self.assertIn('publication_late',alert.conditions(value))

    def test_resource_incident_blocks_false_recovery_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=alert.AlertStore(Path(tmp).resolve()/'state');self.addCleanup(store.close)
            value=sample();value['operations']={'issues':['disk_pressure']}
            self.assertEqual(store.observe(value,SENDER,TO)['queued'],0)
            self.assertEqual(store.observe(value,SENDER,TO)['queued'],1)
            store.deliver(Mailer(),value['checkedAt'])
            for _ in range(3):self.assertTrue(store.observe(value,SENDER,TO)['episodeOpen'])
            value['operations']['issues']=[]
            self.assertTrue(store.observe(value,SENDER,TO)['episodeOpen'])
            self.assertFalse(store.observe(value,SENDER,TO)['episodeOpen'])
            jobs=list(store.db.execute('SELECT payload FROM jobs'))
            self.assertEqual(len(jobs),2)
            self.assertIn('运行状态已恢复',json.loads(jobs[-1][0])['subject'])

    def test_daily_mail_survives_restart_and_retries_with_frozen_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'state';store=alert.AlertStore(path);value=sample()
            self.assertEqual(store.queue_report(value,SENDER,TO,'original facts'),1)
            mailer=Mailer(alert.MailFailure('timeout',True));store.deliver(mailer,value['checkedAt']);store.close()
            store=alert.AlertStore(path);self.addCleanup(store.close)
            self.assertEqual(store.queue_report(value,SENDER,TO,'changed facts'),0)
            retry=Mailer();store.deliver(retry,value['checkedAt']+300)
            self.assertEqual(mailer.calls,retry.calls)
            self.assertEqual(store.queue_report(sample(value['checkedAt']+86400),SENDER,TO,'tomorrow'),1)

    def test_private_addresses_and_redirect_to_metadata_never_connect(self):
        probe=checks.PublicProbe()
        with patch.object(checks.socket,'getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('169.254.169.254',443))]),patch.object(checks.socket,'create_connection') as connect:
            self.assertEqual(probe.check('https://example.com/x')['status'],'uncheckable')
            connect.assert_not_called()
        original=probe.exchange;calls=[]
        def exchange(url,*args):
            calls.append(url)
            if len(calls)==1:return 302,'https://127.0.0.1/admin',b'',None
            return original(url,*args)
        with patch.object(probe,'exchange',side_effect=exchange),patch.object(checks,'public_addresses',side_effect=ValueError('private')),patch.object(checks.socket,'create_connection') as connect:
            self.assertEqual(probe.check('https://example.com')['status'],'uncheckable');connect.assert_not_called()
        for url in ['http://example.com','https://user:secret@example.com','https://example.com:8080','https://[broken']:
            self.assertEqual(probe.check(url)['status'],'uncheckable')

    def test_link_failures_are_classified_and_response_bodies_are_not_kept(self):
        probe=checks.PublicProbe()
        for status,expected in [(200,'ok'),(403,'restricted'),(429,'restricted'),(404,'http_error'),(503,'http_error')]:
            with patch.object(probe,'exchange',return_value=(status,None,b'private response text',None)):
                result=probe.check('https://example.com/path?token=do-not-email#fragment')
                self.assertEqual(result['status'],expected)
                self.assertNotIn('private response',json.dumps(result));self.assertNotIn('do-not-email',json.dumps(result))
        with patch.object(probe,'exchange',side_effect=TimeoutError()):self.assertEqual(probe.check('https://example.com')['reason'],'timeout')

    def test_discovery_reports_incomplete_coverage_and_no_body_leaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'pipeline/config';config.mkdir(parents=True)
            (config/'source_registry.json').write_text(json.dumps({'sources':[{'primary_url':'https://official.example/'}]}))
            class Probe:
                def check(self,url,include_body=False):
                    result={'url':url,'status':'ok','httpStatus':200}
                    if include_body:result['body']='<a href="https://other.example/">body not retained</a>'
                    return result
            result=checks.inspect_links(config/'source_registry.json',probe=Probe(),limit=1)
            self.assertEqual(result['discovered'],2);self.assertEqual(result['omitted'],1)
            self.assertEqual(result['external'][0]['url'],'https://official.example/')
            self.assertNotIn('body not retained',json.dumps(result))

    def host_fixture(self,root):
        (root/'state/accounts/backups').mkdir(parents=True)
        (root/'state/accounts/backups/accounts-test.sqlite').write_text('metadata only')
        db=sqlite3.connect(root/'state/accounts/accounts.sqlite')
        db.execute('CREATE TABLE mail_jobs(status TEXT,created INTEGER)');db.commit();db.close()
        proc=root/'proc';proc.mkdir();(proc/'meminfo').write_text('MemTotal: 2000000 kB\nMemAvailable: 1000000 kB\nSwapTotal: 1000000 kB\nSwapFree: 900000 kB\n')
        def run(args):
            if args[0]=='psql':return '123456'
            blocks=[]
            for unit in args[2:-1]:
                state='inactive' if unit in checks.PAUSED or unit in [x+'.service' for x in checks.ONESHOTS] else 'active'
                blocks.append('Id='+unit+'\nLoadState=loaded\nActiveState='+state+'\nSubState=dead\nResult=success\nUnitFileState='+('disabled' if unit in checks.PAUSED else 'enabled'))
            return '\n\n'.join(blocks)
        return proc,run

    def test_host_reports_actual_resources_paused_jobs_and_queue_without_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proc,run=self.host_fixture(root)
            healthy=SimpleNamespace(f_blocks=40*1024**2,f_frsize=1024,f_bfree=12*1024**2,f_bavail=12*1024**2,f_files=1000000,f_ffree=500000)
            with patch.object(checks.os,'statvfs',return_value=healthy),patch.object(checks.os,'getloadavg',return_value=(.1,.2,.3)),patch.object(checks.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
                result=checks.system_snapshot(root,{'slot':'blue'},run=run,proc=proc)
                self.assertEqual(result['issues'],[])
                self.assertEqual(result['resources']['disk']['usedPercent'],70)
                self.assertTrue(all(s['status']=='expected_paused' for s in result['services'] if s['unit'] in checks.PAUSED))
                self.assertEqual(result['mail']['counts'],{})
                healthy.f_bavail=2*1024**2
                self.assertIn('disk_pressure',checks.system_snapshot(root,{'slot':'blue'},run=run,proc=proc)['issues'])
                self.assertIn('service_unhealthy',checks.system_snapshot(root,{'slot':'blue'},run=lambda _: '',proc=proc)['issues'])

    def test_report_explains_restriction_and_coverage_without_fabricating_health(self):
        value=sample();value['operations']={'issues':[],'services':[]}
        value['links']={'site':[],'external':[{'url':'https://example.com','status':'restricted','httpStatus':403}], 'discovered':2,'checked':1,'omitted':1,'pageBodyTruncated':False}
        text=inspection.report_text(value)
        self.assertIn('访问受限，需复核',text);self.assertIn('覆盖不完整',text);self.assertIn('13:00',text)

    def test_database_retention_failure_staleness_and_soft_budget_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proc,run=self.host_fixture(root)
            directory=root/'backup-retention';directory.mkdir()
            for status,age,budget,expected in [
                ('completed',0,False,set()),
                ('failed',0,False,{'database_backup_retention_unhealthy'}),
                ('completed',26*3600+1,False,{'database_backup_retention_unhealthy'}),
                ('completed',0,True,{'database_backup_budget'}),
            ]:
                (directory/'current.json').write_text(json.dumps(dict(status=status,checkedAt=1000000-age,overBudget=budget)))
                with patch.object(checks.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
                    result=checks.system_snapshot(root,{'slot':'blue'},now=1000000,run=run,proc=proc)
                self.assertEqual({i for i in result['issues'] if i.startswith('database_backup_')},expected)
                for issue in expected:self.assertIn(issue,alert.LABELS)


if __name__=='__main__':unittest.main()
