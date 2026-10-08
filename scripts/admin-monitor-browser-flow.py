"""T05 isolated real SQLite/API browser acceptance. No production fetch or publishing."""
import json
import os
import subprocess
import time
from pathlib import Path

def monitor_flow(page,context,base,env,output,report,root):
    inbox=Path(env['MAAS_ACCOUNT_DB']).parent/'monitor-inbox';inbox.mkdir()
    now=int(time.time()*1000)
    sources=[{'id':s,'name':s,'platform':'isolated','kind':'pricing','budgetHours':48} for s in ['sample-success','sample-failed','sample-stale','sample-unknown','sample-unchanged']]
    def run(rid,sid,outcome='success',at=None):
        at=at or now-60000
        return {'id':rid,'kind':'isolated-prices','trigger':'manual','state':'failed' if outcome=='fetch_failed' else 'succeeded','stage':'archive-committed','startedAt':at-1000,'finishedAt':at,'observedAt':at,
                'inputVersion':'inv_isolated_input','outputVersion':'inv_isolated_output','result':'failed' if outcome=='fetch_failed' else 'unchanged' if outcome=='unchanged' else 'success','validation':'unknown','publication':'not_run','errorCode':None,'runLink':None,
                'sources':[{'sourceId':sid,'attemptAt':at-500,'successAt':None if outcome=='fetch_failed' else at-500,'dataThrough':None if outcome=='fetch_failed' else at-500,'outcome':outcome,'coverage':'missing' if outcome=='fetch_failed' else 'full','errorCode':'fetch_failed' if outcome=='fetch_failed' else None}]}
    def ingest(batch,name):
        p=inbox/(name+'.json');p.write_text(json.dumps(batch))
        result=subprocess.run(['node',str(root/'services/agent-api/dist/monitor-cli.js'),'import',p.name],env={**env,'MAAS_MONITOR_INBOX':str(inbox.resolve())},check=True,capture_output=True,text=True)
        return json.loads(result.stdout)
    first={'schemaVersion':1,'batchId':'browser_monitor_1','sources':sources,'runs':[run('sample_success_run','sample-success'),run('sample_failed_run','sample-failed','fetch_failed'),run('sample_stale_run','sample-stale',at=now-3*86400000),run('sample_unchanged_run','sample-unchanged','unchanged')]}
    assert ingest(first,'first')['imported']==4
    assert ingest(first,'first')['duplicate']
    page.goto(base+'/admin/sources/')
    page.wait_for_function("document.querySelector('#monitor-status').textContent.includes('5个信源')")
    rows=page.locator('#monitor-sources').inner_text()
    assert '无变化' in rows and '记录过期' in rows and '未知' in rows and '抓取失败' in rows
    assert 'inv_isolated' not in page.locator('body').inner_text()
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(output/'monitor-sources-desktop.png'),full_page=True)
    anomaly=page.locator('#monitor-anomalies article').filter(has=page.locator('p',has_text='sample-failed')).first
    anomaly.locator('select').select_option('resolved');anomaly.locator('input[aria-label="处理原因"]').fill('隔离验收：必须有后续核验')
    anomaly.locator('button').click()
    anomaly.locator('[role=status]').filter(has_text='解决需关联').wait_for()
    anomaly.locator('select').select_option('ignored');anomaly.locator('input[aria-label="处理原因"]').fill('隔离验收：忽略不改变健康')
    anomaly.locator('button').click();page.wait_for_function("document.querySelector('#monitor-anomalies').textContent.includes('已忽略')")
    assert '抓取失败' in page.locator('#monitor-sources').inner_text()
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(output/'monitor-ignored.png'),full_page=True)
    anomaly.locator('a',has_text='查看关联运行').click()
    page.wait_for_function("document.querySelector('#monitor-status').textContent.includes('任务已加载')")
    assert page.locator('#monitor-runs article').count()==1
    assert 'sample_failed_run' in page.locator('#monitor-runs').inner_text()
    page.evaluate('scrollTo(0,0)');page.screenshot(path=str(output/'monitor-task-detail.png'),full_page=True)
    page.goto(base+'/admin/sources/')
    page.wait_for_function("document.querySelector('#monitor-anomalies').textContent.includes('已忽略')")
    a=context.request.get(base+'/api/admin/monitor/anomalies?sourceId=sample-failed').json()['items'][0]
    audit=context.request.get(base+'/api/admin/audit?targetType=monitor_anomaly&targetId='+a['id']).json()['items']
    assert len(audit)==1 and audit[0]['reason']=='隔离验收：忽略不改变健康'
    good=run('sample_recovery_run','sample-failed',at=now-1000)
    assert ingest({'schemaVersion':1,'batchId':'browser_monitor_2','sources':sources,'runs':[good]},'recovery')['imported']==1
    page.locator('#monitor-filter button').click();page.wait_for_function("!document.querySelector('#monitor-sources').textContent.includes('抓取失败')")
    anomaly=page.locator('#monitor-anomalies article').filter(has=page.locator('p',has_text='sample-failed')).first
    anomaly.locator('select').select_option('resolved');anomaly.locator('input[aria-label="处理原因"]').fill('后续成功抓取已核验');anomaly.locator('input[aria-label="核验运行"]').fill('sample_recovery_run');anomaly.locator('button').click()
    page.wait_for_function("document.querySelector('#monitor-anomalies').textContent.includes('已解决')")
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'monitor-sources-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.goto(base+'/admin/tasks/');page.wait_for_function("document.querySelector('#monitor-status').textContent.includes('任务已加载')")
    text=page.locator('#monitor-runs').inner_text();assert '校验 未知 · 发布 未执行' in text and 'inv_isolated_input' in text and '周报worker' in text
    assert not page.locator('#monitor-runs button').count()
    assert not page.evaluate("Object.keys(localStorage).some(k=>/monitor|admin/i.test(k))")
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(output/'monitor-tasks-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.set_viewport_size({'width':1440,'height':1000});page.evaluate('scrollTo(0,0)');page.screenshot(path=str(output/'monitor-tasks-desktop.png'),full_page=True)
    report['states'].append('T05-real-ingest-duplicate-success-failure-unchanged-stale-unknown-ignore-not-heal-verified-resolution-audit-desktop-mobile')
    # Permission clearing removes all source/anomaly rows as well as task records.
    page.evaluate("document.dispatchEvent(new CustomEvent('maas:admin-cleared'))")
    assert page.locator('#monitor-runs').inner_text()==''
    response=context.request.post(base+'/api/admin/monitor/retry',headers={'Origin':base,'Idempotency-Key':'blocked-retry'},data={});assert response.status==404
    report['states'].append('T05-private-DOM-cleared-no-execution-endpoint-no-persistent-storage')

    response=context.request.get(base+'/api/admin/monitor/runs').json()
    def held(route):
        page.locator('#account-user-menu summary').click()
        page.locator('#account-sign-out').click(no_wait_after=True)
        route.fulfill(status=200,content_type='application/json',body=json.dumps(response))
    page.route('**/api/admin/monitor/runs?*',held,times=1)
    page.locator('#monitor-filter button').click()
    page.wait_for_function("document.querySelector('#admin-status').textContent.includes('请使用')")
    assert page.locator('#admin-private').is_hidden()
    assert page.locator('#monitor-runs').inner_text()==''
    report['states'].append('T05-real-logout-late-task-response-does-not-repopulate-private-DOM')
    import sqlite3,hashlib
    token='T05-isolated-browser-restored-session'
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db:
        user=db.execute('SELECT userId FROM admin_members WHERE enabled=1').fetchone()[0]
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,int(time.time()*1000)+3600000))
    context.add_cookies([{'name':'maas_session','value':token,'url':base}])
