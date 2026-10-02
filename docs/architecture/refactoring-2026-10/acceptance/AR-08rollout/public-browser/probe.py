import json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('docs/architecture/refactoring-2026-10/acceptance/AR-08rollout/public-browser');out.mkdir(exist_ok=True)
r={'scope':'Live Chromium; analytics/third-party requests blocked','errors':[],'pages':{}}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);c=b.new_context(locale='zh-CN');page=c.new_page()
 page.route('**/*',lambda rt:rt.continue_() if rt.request.url.startswith('https://daily.maas.click/') else rt.abort())
 page.on('pageerror',lambda e:r['errors'].append(str(e)))
 for w in (1440,390):
  page.set_viewport_size({'width':w,'height':1000})
  for route in ('/','/pricing/','/model/deepseek:deepseek-v4-pro/'):
   response=page.goto('https://daily.maas.click'+route,wait_until='networkidle');assert response.status==200
   width=page.evaluate('document.documentElement.scrollWidth');assert width<=w
   state={'status':response.status,'viewportWidth':w,'documentWidth':width}
   if route=='/pricing/':
    page.wait_for_selector('#models tr');state['rows']=page.locator('#models tr').count();assert state['rows']>0
    page.locator('#search').fill('this-model-does-not-exist');assert page.locator('#models tr').count()==0 and page.locator('#catalog-empty').is_visible()
    page.locator('#search').fill('');page.locator('.details-btn').first.click();assert page.locator('#detail').evaluate('(d)=>d.open');page.keyboard.press('Escape');state['searchAndDetailPassed']=True
    if w==390:page.screenshot(path=str(out/'pricing-mobile.png'),full_page=True)
   if route.startswith('/model/'):
    state['datasetVersion']=page.locator('.model-detail').get_attribute('data-dataset-version');assert state['datasetVersion']=='ds_0da7f0c0f2bcd5df62281a262539b65a1742e3fbd710a14724359b58675c1b13'
   r['pages'][f'{w}{route}']=state
 b.close()
assert not r['errors'];(out/'browser.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
