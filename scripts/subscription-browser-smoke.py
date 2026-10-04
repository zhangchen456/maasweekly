import json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1];fixture=json.loads(Path(sys.argv[1]).read_text());report={'checks':[],'errors':[]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 for kind in ['guest','free','paid']:
  context=browser.new_context(viewport={'width':1280,'height':1000})
  if kind!='guest':context.add_cookies([{'name':'maas_session','value':fixture[kind],'url':fixture['origin']}])
  context.add_init_script("localStorage.setItem('maas-theme','dark')")
  page=context.new_page();page.on('pageerror',lambda error:report['errors'].append(str(error)))
  page.goto(fixture['origin']+'/subscription/')
  page.wait_for_function("!document.querySelector('#subscription-status').textContent.includes('正在查询')")
  if kind=='paid':
   page.wait_for_selector('[data-current-plus]:not([hidden])');page.wait_for_function("document.querySelector('[data-account-plan]').textContent==='Plus'")
  else:
   page.wait_for_selector('[data-current-free]:not([hidden])')
  page.screenshot(path=str(root/'docs/product/subscription-v1/acceptance'/f'{kind}-desktop.png'),full_page=True)
  if kind=='guest':
   page.locator('#subscription-plus').click();assert page.locator('#account-login-dialog').is_visible();page.locator('#account-login-close').click()
  elif kind=='free':
   page.locator('#subscription-plus').click();page.locator('#subscription-scenario').fill('每周产品竞品与计费条件对比');page.locator('#subscription-form button').click();page.wait_for_function("document.querySelector('#subscription-status').textContent.includes('申请已提交')")
  else:
   page.locator('#subscription-plus').click();page.wait_for_url('**/pro/')
  page.goto(fixture['origin']+'/subscription/');page.set_viewport_size({'width':390,'height':844});page.wait_for_function("!document.querySelector('#subscription-status').textContent.includes('正在查询')");assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(root/'docs/product/subscription-v1/acceptance'/f'{kind}-mobile.png'),full_page=True)
  page.goto(fixture['origin']+'/en/subscription/');assert page.locator('html').get_attribute('lang')=='en';assert page.locator('.plan-card').count()==2
  report['checks'].append({'account':kind,'plan':'Plus' if kind=='paid' else 'Free','mobileOverflow':False,'englishRoute':True});context.close()
 browser.close()
assert not report['errors'],report['errors']
(root/'docs/product/subscription-v1/acceptance/browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
