import functools, http.server, threading, json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[3]
out=Path(__file__).parent
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root/'site/dist')))
threading.Thread(target=server.serve_forever,daemon=True).start()
report={'viewports':[], 'errors':[]}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True)
  for width in [1440,390]:
   page=browser.new_page(viewport={'width':width,'height':1000})
   base=f'http://127.0.0.1:{server.server_port}'
   page.route('**/*', lambda r:r.continue_() if r.request.url.startswith(base) else r.abort())
   page.on('pageerror', lambda e:report['errors'].append(str(e)))
   page.goto(base+'/compare/')
   assert page.locator('.compare-group').count()==3
   assert page.locator('tr[data-platform-id="google-vertex-ai"]').count()>=3
   assert page.get_by_text('等待完整、最新的价格证据',exact=True).count()==0
   metrics=page.evaluate('({width:innerWidth,bodyWidth:document.documentElement.scrollWidth,rows:document.querySelectorAll("tbody tr").length,tableWidth:document.querySelector("table").getBoundingClientRect().width,rowHeight:document.querySelector("tbody tr").getBoundingClientRect().height})')
   assert metrics['bodyWidth']<=width,metrics
   assert metrics['rowHeight']<240,metrics
   page.screenshot(path=str(out/f'compare-{width}.png'),full_page=False)
   page.locator('.group-head a[href^="/model/"]').first.click()
   page.wait_for_url('**/model/**')
   assert '/model/' in page.url
   assert page.get_by_role('link',name='跨平台比较').count() or page.locator('a[href*="/compare/"]').count()
   report['viewports'].append(metrics)
   page.close()
  browser.close()
 assert not report['errors'],report
finally:
 server.shutdown();server.server_close()
 (out/'browser-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
