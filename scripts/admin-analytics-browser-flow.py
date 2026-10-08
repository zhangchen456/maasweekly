"""T04 deterministic local UI acceptance; no real Umami or production writes."""
import datetime
import json
import sqlite3

def analytics_flow(page,context,base,env,output,report,root,umami):
    today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db:
        user=db.execute("SELECT id FROM users WHERE email='admin-preview@example.test'").fetchone()[0]
        content=db.execute("SELECT id FROM pro_content WHERE json_extract(payload,'$.kind')='briefing' LIMIT 1").fetchone()[0]
        for days in [1,1,2]:
            stamp=int(datetime.datetime.combine(today-datetime.timedelta(days=days),datetime.time(),datetime.timezone(datetime.timedelta(hours=8))).timestamp()*1000)
            db.execute('INSERT INTO pro_events VALUES(?,?,?,?)',('content_read',content,user,stamp))
    page.goto(base+'/admin/analytics/')
    page.wait_for_function("document.querySelector('#analytics-status').textContent.includes('北京时间')")
    assert '12' in page.locator('#analytics-website').inner_text()
    assert '浏览量' in page.locator('#analytics-website-state').inner_text()
    assert content in page.locator('#analytics-weekly').inner_text()
    assert '1' in page.locator('#analytics-weekly').inner_text()
    assert '分母为0' in page.locator('#analytics-cohorts').inner_text()
    assert 'PRIVATE_UMAMI_BROWSER_TOKEN' not in page.locator('body').inner_text()
    assert not page.evaluate("Object.keys(localStorage).some(k=>/analytics|umami|admin/i.test(k))")
    page.screenshot(path=str(output/'analytics-desktop.png'),full_page=True)
    page.locator('#analytics-filter [name=preset]').select_option('28')
    page.locator('#analytics-filter button').click()
    first=(today-datetime.timedelta(days=27)).isoformat()
    page.wait_for_function("value=>document.querySelector('#analytics-status').textContent.includes(value)",arg=first)
    page.locator('#analytics-filter [name=preset]').select_option('custom')
    page.locator('#analytics-filter [name=from]').fill((today-datetime.timedelta(days=2)).isoformat())
    page.locator('#analytics-filter [name=to]').fill((today-datetime.timedelta(days=1)).isoformat())
    page.locator('#analytics-filter button').click()
    page.wait_for_function("value=>document.querySelector('#analytics-status').textContent.includes(value)",arg=(today-datetime.timedelta(days=2)).isoformat())
    assert len(page.locator('#analytics-weekly tbody tr').all())==1
    assert page.locator('#analytics-weekly tbody tr td').nth(2).inner_text()=='3'
    assert page.locator('#analytics-weekly tbody tr td').nth(3).inner_text()=='1'
    assert page.locator('#analytics-weekly tbody tr td').nth(4).inner_text()=='1'
    report['states'].append('T04-7day-28day-custom-real-SQL-deduplicated-cross-day-readers')
    umami['fail']=True
    page.locator('#analytics-filter [name=from]').fill((today-datetime.timedelta(days=3)).isoformat())
    page.locator('#analytics-filter button').click()
    page.wait_for_function("document.querySelector('#analytics-website-state').textContent.includes('不可用')")
    assert '尚无成功记录' not in page.locator('#analytics-website-state').inner_text()
    assert page.locator('#analytics-website').inner_text()==''
    assert page.locator('#analytics-pages').inner_text()==''
    assert '资料建立' in page.locator('#analytics-business').inner_text()
    page.screenshot(path=str(output/'analytics-unavailable.png'),full_page=True)
    report['states'].append('T04-Umami-failure-null-values-last-success-local-metrics-still-visible')
    umami['fail']=False
    page.locator('#analytics-filter [name=from]').fill((today-datetime.timedelta(days=4)).isoformat())
    page.locator('#analytics-filter button').click()
    page.wait_for_function("document.querySelector('#analytics-website-state').textContent.includes('查询成功')")
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.screenshot(path=str(output/'analytics-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    report['states'].append('T04-desktop-mobile-no-overflow-and-Umami-recovery')
    # A held reply arriving after logout must not reintroduce private metrics.
    response=context.request.get(base+'/api/admin/analytics').json()
    def held(route):
        page.locator('#account-user-menu summary').click()
        page.locator('#account-sign-out').click(no_wait_after=True)
        route.fulfill(status=200,content_type='application/json',body=json.dumps(response))
    page.route('**/api/admin/analytics?*',held,times=1)
    page.locator('#analytics-filter [name=preset]').select_option('7')
    page.locator('#analytics-filter button').click()
    page.wait_for_function("document.querySelector('#admin-status').textContent.includes('请使用')")
    assert page.locator('#admin-private').is_hidden()
    assert page.locator('#analytics-business').inner_text()==''
    assert page.locator('#analytics-weekly').inner_text()==''
    report['states'].append('T04-logout-late-response-clears-private-metrics')
    # Restore the existing admin session for subsequent T02 acceptance.
    with sqlite3.connect(env['MAAS_ACCOUNT_DB']) as db:
        import hashlib
        token='T04-local-browser-session-restored-only'
        db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,int(datetime.datetime.now().timestamp()*1000)+3600000))
    context.add_cookies([{'name':'maas_session','value':token,'url':base}])
