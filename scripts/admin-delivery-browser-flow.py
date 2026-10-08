"""T06 local real SQLite/admin API/CLI + simulated signed receipt. No external mail."""
import json
import time
import sqlite3
import subprocess
import hashlib
import hmac
import base64
from pathlib import Path

def delivery_flow(page, context, base, env, output, report, root):
    now=int(time.time()*1000)
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db:
        uid=db.execute("SELECT id FROM users WHERE email='admin-preview@example.test'").fetchone()[0]
        db.execute('UPDATE users SET emailEnabled=1 WHERE id=?',(uid,))
        for jid,status in [('t06-failed','review'),('t06-unknown','review'),('t06-accepted','sent')]:
            db.execute("INSERT INTO mail_jobs(id,userId,payload,created,status,mail) VALUES(?,?,'[]',?,?,'PRIVATE_MAIL_WITH_UNSUBSCRIBE')",(jid,uid,now,status))
        for jid,state,provider,mid in [('t06-failed','failed',None,None),('t06-unknown','unknown',None,None),('t06-accepted','accepted','local','browser-message')]:
            db.execute('INSERT INTO mail_delivery(kind,jobId,state,provider,messageId,eventAt) VALUES(?,?,?,?,?,?)',('digest',jid,state,provider,mid,now))
        db.execute("INSERT INTO mail_attempts VALUES('t06-attempt','digest','t06-failed',?,?,0,'failed','provider_rejected',NULL,NULL)",(now,now))
    page.goto(base+'/admin/delivery/')
    page.wait_for_function("document.querySelector('#delivery-status').textContent.includes('投递记录已加载')")
    assert '供应商接受' in page.locator('#delivery-items').inner_text()
    unknown=page.locator('#delivery-items article').filter(has_text='t06-unknown')
    unknown.locator('button').click()
    page.locator('#delivery-detail h2').filter(has_text='未知').wait_for()
    assert page.locator('#delivery-detail button',has_text='确认重试').is_disabled()
    assert 'PRIVATE_MAIL_WITH_UNSUBSCRIBE' not in page.locator('body').inner_text()
    page.screenshot(path=str(output/'delivery-unknown.png'),full_page=True)
    failed=page.locator('#delivery-items article').filter(has_text='t06-failed')
    failed.locator('button').click()
    page.locator('#delivery-detail h2').filter(has_text='失败').wait_for()
    form=page.locator('#delivery-detail form').filter(has=page.locator('button',has_text='确认重试'))
    form.locator('input').fill('隔离验收：明确拒绝可重试')
    form.locator('button').click()
    page.locator('#delivery-detail h2').filter(has_text='入队').wait_for()
    audit=context.request.get(base+'/api/admin/audit?targetType=mail_delivery&targetId=digest%3At06-failed').json()['items']
    assert len(audit)==1 and audit[0]['action']=='delivery.retry'
    page.screenshot(path=str(output/'delivery-retry.png'),full_page=True)
    inbox=Path(env['MAAS_ACCOUNT_DB']).parent/'delivery-inbox';inbox.mkdir()
    def cli(action,name):
        r=subprocess.run(['node',str(root/'services/agent-api/dist/delivery-cli.js'),action,name],env={**env,'MAAS_DELIVERY_INBOX':str(inbox.resolve()),'MAAS_MAIL_RECEIPT_SECRET':signing},capture_output=True,text=True,check=True)
        return json.loads(r.stdout)
    signing='whsec_'+base64.b64encode(b'local-signing-secret-32-characters').decode()
    raw=json.dumps({'type':'email.delivered','created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'data':{'email_id':'browser-message','text':'PRIVATE_PROVIDER_BODY'}})
    stamp=str(int(time.time()));event='browser_event'
    sig=base64.b64encode(hmac.new(base64.b64decode(signing[6:]),(event+'.'+stamp+'.'+raw).encode(),hashlib.sha256).digest()).decode()
    packet={'raw':raw,'headers':{'svix-id':event,'svix-timestamp':stamp,'svix-signature':'v1,'+sig}}
    (inbox/'receipt.json').write_text(json.dumps(packet))
    assert not cli('local-receipt','receipt.json')['duplicate']
    assert cli('local-receipt','receipt.json')['duplicate']
    page.locator('#delivery-items article').filter(has_text='t06-accepted').locator('button').click()
    page.locator('#delivery-detail h2').filter(has_text='供应商接受').wait_for()
    form=page.locator('#delivery-detail form').filter(has=page.locator('button',has_text='核对已保存'))
    form.locator('input').fill('隔离验收：验证送达回执')
    form.locator('button').click()
    page.locator('#delivery-detail h2').filter(has_text='确认送达').wait_for()
    assert 'PRIVATE_PROVIDER_BODY' not in page.locator('body').inner_text()
    page.screenshot(path=str(output/'delivery-delivered.png'),full_page=True)
    record={'id':'browser_backup','kind':'backup','status':'normal','checkedAt':int(time.time()*1000),'budgetSeconds':93600,'source':'account-maintenance.backup','value':None}
    (inbox/'backup.json').write_text(json.dumps(record));cli('health','backup.json')
    old={**record,'id':'browser_mail_stale','kind':'mail','source':'mail.adapter','checkedAt':now-120000,'budgetSeconds':60}
    (inbox/'stale.json').write_text(json.dumps(old));cli('health','stale.json')
    page.goto(base+'/admin/health/')
    page.wait_for_function("document.querySelector('#delivery-status').textContent.includes('检查于')")
    body=page.locator('#health-items').inner_text()
    assert '备份 · 正常' in body and '恢复验证 · 未知' in body and '记录过期' in body
    page.screenshot(path=str(output/'health-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});page.goto(base+'/admin/delivery/')
    page.wait_for_function("document.querySelector('#delivery-status').textContent.includes('投递记录已加载')")
    page.locator('input[name=user]').fill('no-match@example.test');page.locator('#delivery-filter button').click()
    page.wait_for_function("document.querySelector('#delivery-status').textContent.includes('没有符合条件')")
    page.screenshot(path=str(output/'delivery-mobile-empty.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    assert not page.evaluate("Object.keys(localStorage).some(k=>k.includes('delivery'))")
    report['states'].extend(['T06-unknown-disabled-and-safe-detail','T06-confirmed-retry-audited','T06-signed-duplicate-receipt-delivered','T06-backup-separate-from-restore-and-stale','T06-mobile-empty-filter'])
