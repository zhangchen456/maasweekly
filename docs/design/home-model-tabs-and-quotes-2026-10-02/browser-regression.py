import asyncio,json,sys,threading,http.server,functools
from pathlib import Path
from playwright.async_api import async_playwright
root=Path.cwd();out=root/'docs/design/home-model-tabs-and-quotes-2026-10-02';out.mkdir(exist_ok=True)
mode=sys.argv[1] if len(sys.argv)>1 else 'local'
if mode=='local':
 handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root/'site/dist'))
 class Quiet(handler.func):
  def log_message(self,*a):pass
 server=http.server.ThreadingHTTPServer(('127.0.0.1',8327),functools.partial(Quiet,directory=str(root/'site/dist')))
 threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:8327'
else:base='https://daily.maas.click'
async def main():
 results=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True)
  for width in [1440,390]:
   ctx=await browser.new_context(viewport={'width':width,'height':1000},locale='zh-CN')
   await ctx.route('**/*',lambda route: route.continue_() if route.request.url.startswith(base) or route.request.url.startswith('data:') else route.abort())
   page=await ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(base+'/?lang=zh',wait_until='networkidle');await page.locator('.market-section').scroll_into_view_if_needed()
   assert await page.locator('.market-table').count()==1
   assert await page.locator('[role=tab]').count()==3
   tabs=await page.locator('[role=tab]').evaluate_all('(xs)=>xs.map(x=>x.getBoundingClientRect().top)');assert max(tabs)-min(tabs)<2
   assert await page.locator('[data-home-model]:visible').count()==8
   assert await page.locator('[data-quote-amount]').count()==36
   assert await page.locator('.home-quote-pending').count()==0
   quote_rows=[]
   for group,count in [('flagship',8),('value',8),('coding',2)]:
    tab=page.locator('[data-model-tab="'+group+'"]');await tab.click()
    assert await tab.get_attribute('aria-selected')=='true'
    assert await page.locator('[data-home-model]:visible').count()==count
    assert await page.locator('[role=tabpanel]').get_attribute('aria-labelledby')=='model-tab-'+group
    for row in await page.locator('[data-home-model]:visible').all():
     values=await row.locator('[data-quote-amount]').evaluate_all('(xs)=>xs.map(x=>({amount:x.dataset.quoteAmount,currency:x.dataset.quoteCurrency}))')
     assert len(values)==2 and all(float(v['amount'])>0 for v in values)
     quote_rows.append({'modelId':await row.get_attribute('data-home-model'),'prices':values})
    await page.locator('[data-currency=USD]').click();await page.locator('#home-fx-rate').fill('7.25');await page.locator('#home-fx-rate').dispatch_event('change')
    await page.locator('[data-model-tab=flagship]').click()
    assert await page.locator('[data-currency=USD]').get_attribute('aria-pressed')=='true'
    first=page.locator('[data-home-model="openai:gpt-6-astra"] [data-quote-amount]').first
    assert await first.inner_text()=='10'
    await page.locator('[data-currency=CNY]').click();assert await first.inner_text()=='72.5'
    await page.locator('[data-currency=USD]').click()
   await page.locator('#home-fx-rate').fill('0');await page.locator('#home-fx-rate').dispatch_event('change');assert await page.locator('#home-fx-rate').input_value()=='7.25';assert '0.01' in await page.locator('#home-fx-status').inner_text()
   await page.locator('[data-model-tab=flagship]').focus();await page.keyboard.press('ArrowRight');assert await page.locator('[data-model-tab=value]').get_attribute('aria-selected')=='true'
   await page.keyboard.press('End');assert await page.locator('[data-model-tab=coding]').get_attribute('aria-selected')=='true'
   await page.keyboard.press('Home');assert await page.locator('[data-model-tab=flagship]').get_attribute('aria-selected')=='true'
   await page.locator('[data-model-tab=value]').click()
   flash=page.locator('[data-home-model="google:gemini-3.8-flash"]');await flash.locator('summary').click();assert 'December 31, 2026' in await flash.inner_text()
   ds=page.locator('[data-home-model="deepseek:deepseek-flash"]');await ds.locator('summary').click();assert 'UTC' in await ds.inner_text()
   overflow=await page.evaluate('document.documentElement.scrollWidth>window.innerWidth');assert not overflow
   links=[]
   if width==1440:
    for href in await page.locator('[data-home-model] .quote-link').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))'):
     response=await ctx.request.get(base+href);assert response.status==200;links.append(href)
   await page.locator('[data-model-tab=flagship]').click();await page.locator('#home-fx-rate').fill('7.1');await page.locator('#home-fx-rate').dispatch_event('change');await page.locator('[data-currency=CNY]').click();await page.locator('.market-table-wrap').evaluate('(el)=>el.scrollLeft=0');await page.locator('.market-section').screenshot(path=str(out/f'{mode}-zh-{width}.png'))
   assert not errors,errors
   results.append({'locale':'zh','width':width,'oneTable':True,'groups':[8,8,2],'verifiedQuotes':quote_rows,'currencyAndFxPersist':True,'keyboardNavigation':True,'promotionalAndUtcConditions':True,'overflow':overflow,'modelLinks200':links,'pageErrors':errors})
   await page.goto(base+'/en/?lang=en',wait_until='networkidle')
   assert await page.locator('.market-table').count()==1
   for group,count in [('flagship',8),('value',8),('coding',2)]:
    await page.locator('[data-model-tab="'+group+'"]').click();assert await page.locator('[data-home-model]:visible').count()==count
   assert not await page.evaluate('document.documentElement.scrollWidth>window.innerWidth')
   results.append({'locale':'en','width':width,'oneTable':True,'groups':[8,8,2],'overflow':False})
   await ctx.close()
  ctx=await browser.new_context(java_script_enabled=False,viewport={'width':1440,'height':1000});page=await ctx.new_page();await page.goto(base+'/?lang=zh');assert await page.locator('[data-home-model]:visible').count()==18
  results.append({'javaScriptDisabled':'all 18 models visible in one table'})
  await browser.close()
 (out/f'{mode}-browser.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'mode':mode,'passed':len(results),'models':18,'groups':[8,8,2]}))
asyncio.run(main())
