"""T08 real local UI/API/SQLite + explicit simulator; no external payment or mail."""
import json
import sqlite3
import subprocess
import time
from urllib.parse import urlparse, parse_qs

def payments_flow(page, context, base, env, output, report, root):
    def request(path):
        response=context.request.get(base+path)
        assert response.ok, response.text()
        return response.json()
    def cli(*args):
        result=subprocess.run(['node',str(root/'services/agent-api/dist/payment-cli.js'),*args],env=env,check=True,capture_output=True,text=True)
        return json.loads(result.stdout)
    def refund(amount):
        form=page.locator('#payments-refund')
        form.locator('[name=orderId]').fill(order)
        form.locator('[name=amount]').fill(str(amount))
        form.locator('[name=reason]').fill('本机模拟退款验收')
        form.locator('button').click()
        page.wait_for_function("document.querySelector('#payments-status').textContent.includes('退款请求已保存')")
        result=request('/api/admin/payments/orders/'+order)
        rows=[r for r in result['refunds'] if r['state']=='pending']
        assert len(rows)==1
        return rows[0]['id']
    page.goto(base+'/subscription/payments/')
    page.locator('#billing-buy').wait_for(state='visible')
    page.wait_for_function("!document.querySelector('#billing-buy').disabled")
    assert '尚无付费订阅' in page.locator('#billing-subscriptions').inner_text()
    page.locator('#billing-buy').click()
    page.wait_for_url('**/subscription/sandbox/?order=*')
    order=parse_qs(urlparse(page.url).query)['order'][0]
    assert request('/api/pro/billing')['orders'][0]['state']=='processing'
    preview=context.new_page();preview.goto(base+'/subscription/payments/?success=true')
    preview.wait_for_function("document.querySelector('#billing-records').textContent.includes('支付处理中')")
    preview.screenshot(path=str(output/'payment-processing.png'),full_page=True)
    assert request('/api/pro/me')['entitlement']['status']!='active'
    preview.close()
    page.locator('[data-outcome=failed]').click()
    page.wait_for_function("document.querySelector('#sandbox-status').textContent.includes('已在服务端核验')")
    assert request('/api/pro/billing')['orders'][0]['state']=='failed'
    failure=context.new_page();failure.goto(base+'/subscription/payments/')
    failure.wait_for_function("document.querySelector('#billing-records').textContent.includes('失败')")
    failure.screenshot(path=str(output/'payment-failed.png'),full_page=True);failure.close()
    with page.expect_response(lambda r: r.url.endswith('/api/pro/billing/simulator-result')) as response:
        page.locator('[data-outcome=paid]').click()
    assert response.value.ok
    page.wait_for_function("document.querySelector('#sandbox-status').textContent.includes('已在服务端核验')")
    page.goto(base+'/subscription/payments/')
    page.wait_for_function("document.querySelector('#billing-entitlement').textContent.includes('付费')")
    assert request('/api/pro/me')['entitlement']['source']=='paid'
    assert '下次续费' in page.locator('#billing-subscriptions').inner_text()
    page.screenshot(path=str(output/'payment-paid.png'),full_page=True)
    page.locator('#billing-subscriptions button').click()
    page.wait_for_function("document.querySelector('#billing-subscriptions').textContent.includes('已停止续费')")
    assert request('/api/pro/me')['entitlement']['source']=='paid'
    page.screenshot(path=str(output/'payment-cancel-renewal.png'),full_page=True)
    report['states'].extend(['T08-processing-return-does-not-grant','T08-failed-then-verified-paid','T08-cancel-keeps-current-paid-period'])

    page.goto(base+'/admin/payments/')
    page.wait_for_function("document.querySelector('#payments-status').textContent.includes('记录已加载')")
    assert '手续费' in page.locator('#payments-totals').inner_text() and '未知' in page.locator('#payments-totals').inner_text()
    page.locator('#payments-items button').first.click()
    page.wait_for_function("document.querySelector('#payments-detail-title').textContent.includes('order_')")
    assert '供应商对象' in page.locator('#payments-detail-records').inner_text()
    partial=refund(500)
    assert request('/api/admin/payments/refunds/'+partial)['refund']['state']=='pending'
    assert request('/api/pro/me')['entitlement']['source']=='paid'
    page.screenshot(path=str(output/'payment-refund-pending.png'),full_page=True)
    cli('refund-result',partial,'succeeded')
    assert request('/api/pro/me')['entitlement']['source']=='paid'
    remaining=refund(490)
    cli('refund-result',remaining,'succeeded')
    assert request('/api/pro/me')['entitlement']['status']!='active'
    page.locator('#payments-filter button').click()
    page.wait_for_function("document.querySelector('#payments-items').textContent.includes('全额退款')")
    page.locator('#payments-items button').first.click()
    page.wait_for_function("document.querySelector('#payments-detail-records').textContent.includes('退款成功')")
    page.screenshot(path=str(output/'payment-refund-completed.png'),full_page=True)
    report['states'].append('T08-pending-partial-full-refund-separate-from-entitlement')

    detail=request('/api/admin/payments/orders/'+order)
    paid=next(f for f in detail['facts'] if f['kind']=='paid')
    records=[{'kind':'paid','objectId':paid['objectId'],'currency':'USD','amount':980,'occurredAt':paid['occurredAt']}]
    for f in detail['facts']:
        if f['kind']=='refund': records.append({k:f[k] for k in ['kind','objectId','currency','amount','occurredAt']})
    now=int(time.time()*1000)
    records.extend([{'kind':'fee','objectId':'isolated-fee','currency':'USD','amount':30,'occurredAt':now},{'kind':'settlement','objectId':'isolated-settlement','currency':'USD','amount':0,'occurredAt':now}])
    snapshot={'currency':'USD','from':now-86400000,'to':now+1000,'source':'ISOLATED_SIMULATOR_SNAPSHOT_NOT_REAL_SETTLEMENT','records':records}
    fixture=output/'reconciliation-fixture.json';fixture.write_text(json.dumps(snapshot))
    reconciled=cli('reconcile',str(fixture.resolve()))
    assert reconciled['differences']==1
    page.locator('#payments-filter [name=kind]').select_option('reconciliations')
    page.locator('#payments-filter button').click()
    page.wait_for_function("document.querySelector('#payments-items').textContent.includes('ISOLATED_SIMULATOR')")
    page.locator('#payments-items button').first.click()
    page.wait_for_function("document.querySelector('#payments-detail-records').textContent.includes('供应商快照记录')")
    summary=request('/api/admin/payments/totals?reconciliationId='+reconciled['id'])
    assert summary['fees']==30 and summary['settlement']==0 and summary['revenue']==990
    page.screenshot(path=str(output/'payment-reconciliation-snapshot.png'),full_page=True)
    page.locator('#payments-filter [name=kind]').select_option('differences');page.locator('#payments-filter button').click()
    page.wait_for_function("document.querySelector('#payments-items').textContent.includes('金额不符')")
    page.locator('#payments-items button').first.click()
    page.wait_for_function("document.querySelector('#payments-detail-title').textContent.length>0 && !document.querySelector('#payments-detail').hidden")
    form=page.locator('#payments-note');form.locator('[name=note]').fill('隔离模拟：核对供应商支付记录相差10最小单位，保留交易事实。');form.locator('[name=reason]').fill('本机差异验收');form.locator('button').click()
    page.wait_for_function("document.querySelector('#payments-status').textContent.includes('处理记录已追加')")
    page.wait_for_function("document.querySelector('#payments-detail-records').textContent.includes('保留交易事实')")
    page.screenshot(path=str(output/'payment-difference-action.png'),full_page=True)
    report['states'].append('T08-currency-reconciliation-source-unknown-vs-known-and-append-action')
    page.set_viewport_size({'width':390,'height':844});page.goto(base+'/subscription/payments/')
    page.wait_for_function("document.querySelector('#billing-entitlement').textContent.includes('Free')")
    assert page.evaluate("document.querySelector('#billing-records').scrollWidth > document.querySelector('#billing-records').clientWidth")
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    page.screenshot(path=str(output/'payment-user-mobile.png'),full_page=True)
    page.goto(base+'/admin/payments/');page.wait_for_function("document.querySelector('#payments-status').textContent.includes('记录已加载')")
    page.screenshot(path=str(output/'payment-admin-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    assert not page.evaluate("Object.keys(localStorage).some(k=>/payment|billing/.test(k))")
    page.locator('#payments-filter [name=q]').fill(order)
    page.locator('#account-user-menu summary').click();page.locator('#account-sign-out').click()
    page.wait_for_function("document.querySelector('#admin-private').hidden")
    assert page.locator('#payments-filter [name=q]').input_value()==''
    assert page.locator('#payments-items').inner_text()=='' and page.locator('#payments-detail-records').inner_text()==''
    report['states'].append('T08-mobile-and-logout-private-dom-cleared')
