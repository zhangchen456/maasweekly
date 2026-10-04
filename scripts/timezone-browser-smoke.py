import functools,json,threading
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(root/'site/dist')))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
report={'scope':'Built static site and mocked account metadata; Chromium browser timezone emulation; no external email or real account modifications','pages':['/en/account/','/en/pricing/','/en/leaderboards/','/en/model/anthropic:claude-sonnet-4.5/','/en/compare/','/account/ (Asia/Shanghai)'],'checks':[],'errors':[]}
user={'user':{'id':'timezone-fixture','email':'timezone@example.test','displayName':'Timezone Test','created':1790990100000,'plan':'free'},'preferences':{'emailEnabled':False},'watches':[],'state':{}}
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  for zone,expected in [('Asia/Shanghai','09:15 GMT+8'),('America/Los_Angeles','18:15 GMT-7'),('Europe/London','02:15 GMT+1'),('Pacific/Kiritimati','15:15 GMT+14')]:
   context=browser.new_context(timezone_id=zone,viewport={'width':390,'height':844})
   page=context.new_page();page.on('pageerror',lambda err:report['errors'].append(str(err)))
   def account(route):
    path=route.request.url.split('/api/account/')[-1]
    value=user if path=='me' else {'enabled':True,'mailAvailable':True,'cadence':'daily'} if path=='status' else {'items':[],'dataThrough':'2026-10-03'} if path=='changes' else {'saved':True}
    route.fulfill(status=200,content_type='application/json',body=json.dumps(value))
   page.route('**/api/account/**',account)
   page.route('**/api/v1/models',lambda route:route.fulfill(status=200,content_type='application/json',body='{"models":[]}'))
   page.goto(base+'/en/account/')
   page.wait_for_function("document.querySelector('#profile-created-time')?.textContent.includes('GMT')",timeout=5000)
   created=page.locator('#profile-created-time').inner_text()
   assert expected in created,(zone,created)
   assert page.locator('[data-browser-timezone]').inner_text()==zone
   check=page.locator('[data-digest-next]').get_attribute('datetime')
   assert check.endswith('T01:15:00.000Z'),check
   next_local=page.locator('[data-digest-next]').inner_text()
   assert expected in next_local,(zone,next_local)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),zone
   page.screenshot(path=str(root/'docs/product/browser-timezone/acceptance'/('account-'+zone.replace('/','-')+'.png')),full_page=True)
   page.goto(base+'/en/pricing/')
   page.wait_for_function("document.querySelector('time[datetime]')?.textContent.includes('GMT')")
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),('pricing overflow',zone)
   for path in ['/en/leaderboards/', '/en/model/anthropic:claude-sonnet-4.5/', '/en/compare/']:
    page.goto(base+path)
    page.wait_for_function("[...document.querySelectorAll('time[datetime]')].some(t=>t.textContent.includes('GMT'))")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(path,zone)
   if zone == 'Asia/Shanghai':
    page.goto(base+'/account/')
    page.wait_for_function("document.querySelector('#profile-created-time')?.textContent.includes('GMT')")
    assert 'GMT+8' in page.locator('#profile-created-time').inner_text()
   page.goto(base+'/en/pricing/')
   # Dynamic data date precision remains a calendar date even west of UTC.
   page.evaluate("""() => { const date=document.createElement('time');date.id='timezone-date-fixture';date.dateTime='2026-10-03';date.textContent='2026-10-03';document.body.append(date); }""")
   page.wait_for_timeout(20)
   assert page.locator('#timezone-date-fixture').inner_text()=='2026-10-03'
   report['checks'].append({'zone':zone,'profileCreated':created,'nextDigestCheck':next_local,'mobileOverflow':False,'dateOnly':'2026-10-03'})
   context.close()
  browser.close()
 assert not report['errors'],report['errors']
finally:
 server.shutdown();server.server_close()
 (root/'docs/product/browser-timezone/acceptance/browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
