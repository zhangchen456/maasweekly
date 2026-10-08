"""T07 local fixture only: temporary database, deterministic worker, no remote effects."""
import json
import os
import sqlite3
import subprocess

def problems_flow(page,context,base,env,output,report,root):
    page.on('dialog',lambda dialog:dialog.accept())
    def node(source):
        result=subprocess.run(['node','--input-type=module','-e',source],cwd=root,env=env,text=True,capture_output=True,check=True)
        return json.loads(result.stdout) if result.stdout.strip() else None
    fixture=node("""
      import {AccountStore} from './services/agent-api/dist/account-store.js';
      import {AdminStore} from './services/agent-api/dist/admin-store.js';
      import {AdminProblems} from './services/agent-api/dist/admin-problems.js';
      const a=new AccountStore(process.env.MAAS_ACCOUNT_DB),p=new AdminProblems(new AdminStore(a));
      const u=a.db.prepare('SELECT id FROM users LIMIT 1').get().id;
      const one=p.feedback.feedback.submit(u,{title:'Local feedback one',description:'PRIVATE ORIGINAL SHOULD NOT ENTER MODEL'}).id;
      const two=p.feedback.feedback.submit(u,{title:'Local feedback two',description:'Second affected user-visible record'}).id;
      console.log(JSON.stringify({one,two}));a.close();
    """)
    page.goto(base+'/admin/problems/')
    page.wait_for_function("document.querySelector('#problem-status').textContent.includes('列表已加载')")
    create=page.locator('#problem-create');create.locator('[name=title]').fill('T07 隔离问题');create.locator('[name=description]').fill('页面操作失败，需要复现');create.locator('button').click()
    page.wait_for_function("document.querySelector('#problem-status').textContent.includes('详情已加载')")
    def submit(op,values):
        form=page.locator(f'#problem-detail form[data-operation="{op}"]')
        for key,value in values.items():
            locator=form.locator('[name='+key+']')
            if locator.evaluate('(e)=>e.tagName')=='SELECT': locator.select_option(value)
            else: locator.fill(value)
        with page.expect_response(lambda r:r.request.method=='POST' and '/api/admin/problems/' in r.url) as pending:
            form.locator('button').click()
        response=pending.value
        assert response.status==200,(op,response.status,response.text())
        page.wait_for_function("document.querySelector('#problem-status').textContent.includes('详情已加载')")
        return response.json()
    submit('link',{'kind':'feedback','relatedId':fixture['one'],'reason':'人工确认同一问题'})
    submit('link',{'kind':'feedback','relatedId':fixture['two'],'reason':'逐条确认归并'})
    assert page.locator('#problem-detail a[href*="feedback/detail"]').count()==2
    page.screenshot(path=str(output/'problems-linked-desktop.png'),full_page=True)
    report['states'].append('problem-merge-two-feedback-original-history-preserved')
    diag={'description':'Redacted reproducible failure','reproduction':'Open local page','versions':'local-v1','errorSummary':'HTTP 500','budget':'0','reason':'人工选择脱敏材料'}
    first=submit('diagnose',diag);second=submit('diagnose',diag);assert first['runId']==second['runId']
    subprocess.run(['node',str(root/'services/agent-api/dist/diagnostic-worker.js'),'--once'],env={**env,'MAAS_DIAGNOSTIC_ALLOW_PAID':'false'},check=True,capture_output=True)
    page.locator('#problem-refresh').click()
    page.wait_for_function("document.querySelector('#problem-detail').textContent.includes('advisoryOnly')")
    assert 'PRIVATE ORIGINAL SHOULD NOT ENTER MODEL' not in page.locator('#problem-detail').inner_text()
    page.screenshot(path=str(output/'problems-diagnosis.png'),full_page=True)
    report['states'].append('selected-material-deterministic-advice-dedup-no-feedback-state-change')
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db:
        problem=db.execute('SELECT id FROM problems').fetchone()[0]
        payload=db.execute('SELECT payload FROM diagnostic_runs').fetchone()[0]
        assert 'PRIVATE ORIGINAL' not in payload and '@example.test' not in payload
        assert db.execute('SELECT count(*) FROM editorial_issues').fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM feedback WHERE status='open'").fetchone()[0]==2
    submit('references',{'kind':'commit','value':'local-commit-fixture','trust':'verified','source':'人工查询本地隔离提交样例；非真实仓库修复','checkedAt':'2026-01-01T00:00:00Z','reason':'记录独立修复引用'})
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db: fix=db.execute("SELECT id FROM problem_refs WHERE kind='commit'").fetchone()[0]
    submit('references',{'kind':'release','value':'local-release-fixture','trust':'verified','source':'人工查询本地发布样例；非真实上线','checkedAt':'2026-01-01T00:00:00Z','reason':'记录独立发布引用'})
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db: release=db.execute("SELECT id FROM problem_refs WHERE kind='release'").fetchone()[0]
    submit('progress',{'repairStage':'merged','refId':fix,'reason':'已检查隔离合并样例'})
    submit('progress',{'repairStage':'released','refId':fix,'releaseRefId':release,'reason':'已检查隔离发布样例'})
    submit('verify',{'refId':fix,'releaseRefId':release,'result':'failed','note':'发布后仍复现；模拟线上环境标签','reason':'记录验证失败'})
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db: assert db.execute('SELECT repairStage FROM problems').fetchone()[0]=='pending'
    submit('verify',{'refId':fix,'releaseRefId':release,'result':'passed','note':'隔离样例复验通过；需真实线上逐条核验','reason':'隔离复验'})
    submit('progress',{'repairStage':'verified','refId':fix,'releaseRefId':release,'reason':'样例验证通过'})
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db: assert db.execute("SELECT count(*) FROM feedback WHERE status='open'").fetchone()[0]==2
    page.screenshot(path=str(output/'problems-release-verification.png'),full_page=True)
    report['states'].append('merge-release-separate-post-release-failure-reinvestigation-per-feedback-gate')
    page.locator('#problem-detail button').filter(has_text='解除修复引用').first.click()
    page.wait_for_function("document.querySelector('#problem-detail').textContent.includes('已解除')")
    page.locator('#problem-detail button').filter(has_text='解除关联').first.click()
    page.wait_for_function("document.querySelectorAll('#problem-detail a[href*=\"feedback/detail\"]').length===1")
    report['states'].append('unlink-wrong-repair-reset-progress-unlink-feedback')
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'problems-mobile.png'),full_page=True)
    page.screenshot(path=str(output/'problems-mobile-top.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.evaluate('Object.keys(localStorage).every(k=>!k.includes("problem"))')
    report['states'].append('mobile-no-overflow-no-private-storage')
