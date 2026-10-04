import json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path(__file__).resolve().parent
report={'checks':[],'errors':[]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 for zone in ['Asia/Shanghai','America/Los_Angeles']:
  context=browser.new_context(timezone_id=zone,viewport={'width':390,'height':844})
  page=context.new_page()
  page.on('pageerror',lambda error:report['errors'].append(str(error)))
  for path in ['/','/feedback/','/en/feedback/','/changes/','/en/account/']:
   response=page.goto('https://daily.maas.click'+path,wait_until='networkidle')
   assert response.status==200,(path,response.status)
   page.wait_for_function("(zone) => document.querySelector('[data-browser-timezone]')?.textContent === zone",arg=zone)
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(path,zone,'overflow')
   report['checks'].append({'path':path,'zone':zone,'status':response.status,'overflow':False})
   if path=='/feedback/':page.screenshot(path=str(out/('feedback-'+zone.replace('/','-')+'.png')),full_page=True)
  context.close()
 browser.close()
assert not report['errors'],report['errors']
(out/'browser-online.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
