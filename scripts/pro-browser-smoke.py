import json, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
fixture=json.loads(Path(sys.argv[1]).read_text())
report={'scope':'Real local API, ephemeral fixture accounts, archived sample content, no production or external mail','checks':[],'errors':[]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 for kind in ['guest','free','paid']:
  context=browser.new_context(viewport={'width':1280,'height':900})
  if kind!='guest':context.add_cookies([{'name':'maas_session','value':fixture[kind],'url':fixture['origin']}])
  page=context.new_page();page.on('pageerror',lambda err:report['errors'].append(str(err)))
  page.goto(fixture['origin']+'/pro/')
  page.wait_for_selector('.pro-entry',timeout=15000)
  if kind=='paid':page.wait_for_selector('#pro-settings-panel:not([hidden])')
  elif kind=='free':page.wait_for_selector('#pro-apply:not([hidden])')
  # Everyone sees full sample; private explainer is not in the static page or anonymous response.
  sample=page.locator('.pro-entry').filter(has_text='专业简报样例')
  sample.locator('button').click();page.wait_for_selector('#pro-reader:not([hidden])')
  assert '统计周尚未结束' in page.locator('#pro-content').inner_text()
  page.locator('#pro-close').click()
  private=page.locator('.pro-entry').filter(has_text='Kimi缓存：')
  private.locator('button').click()
  if kind=='paid':
   page.wait_for_selector('#pro-reader:not([hidden])');assert '缓存写入' in page.locator('#pro-content').inner_text()
   page.locator('#pro-close').click()
   page.locator('#pro-settings button[type=submit]').count() # default submit button below
   page.locator('#pro-settings').evaluate('(form)=>form.requestSubmit()')
   page.wait_for_function("document.querySelector('#pro-match').textContent.includes('匹配')")
   page.locator('#pro-token-name').fill('browser acceptance');page.locator('#pro-token-form').evaluate('(form)=>form.requestSubmit()')
   page.wait_for_selector('#pro-secret:not([hidden])');assert len(page.locator('#pro-secret-value').input_value())==43
   page.locator('#pro-secret-clear').click();assert page.locator('#pro-secret-value').input_value()==''
   page.locator('#pro-tokens button').first.click();page.wait_for_function("document.querySelector('#pro-status').textContent.includes('已撤销')")
   page.locator('#pro-token-purpose').select_option('rss');page.locator('#pro-token-name').fill('browser RSS');page.locator('#pro-token-form').evaluate('(form)=>form.requestSubmit()')
   page.wait_for_selector('#pro-secret:not([hidden])');rss=page.locator('#pro-secret-value').input_value()
   response=context.request.get(rss);assert response.status==200
   feed=ET.fromstring(response.text());assert feed.tag=='rss' and len(feed.findall('./channel/item'))>0
   assert '影响判断：请求成功不能证明旧模型仍在服务' not in response.text()
   page.locator('#pro-secret-clear').click()
   page.locator('#pro-reports button').first.click();page.wait_for_selector('#pro-reader:not([hidden])');assert '范围快照' in page.locator('#pro-content').inner_text()
   timings=[]
   for _ in range(10):
    started=time.perf_counter();response=context.request.get(fixture['origin']+'/api/pro/content/kimi-cache-conditions-20261002');assert response.status==200;timings.append((time.perf_counter()-started)*1000)
   report['localProReadP95Ms']=round(sorted(timings)[-1],2)
  else:
   page.wait_for_function("document.querySelector('#pro-status').textContent.includes('请先登录') || document.querySelector('#pro-status').textContent.includes('未生效')")
   assert page.locator('#pro-reader').is_hidden()
  page.screenshot(path=str(root/'docs/product/maas-pro-briefing-v1/acceptance'/f'{kind}-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),kind+' mobile overflow'
  page.screenshot(path=str(root/'docs/product/maas-pro-briefing-v1/acceptance'/f'{kind}-mobile.png'),full_page=True)
  report['checks'].append({'account':kind,'sampleReadable':True,'protectedContentReadable':kind=='paid','mobileOverflow':False})
  context.close()
 browser.close()
assert not report['errors'],report['errors']
(root/'docs/product/maas-pro-briefing-v1/acceptance/browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
