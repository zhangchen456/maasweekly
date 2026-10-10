import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import { JSDOM } from 'jsdom';
import { build } from 'esbuild';
import { preferredLanguage, readPreference, savePreference, startLanguage, switchUrl } from '../public/language.js';
import { loadVerifiedRelease } from '../src/lib/release.ts';
import { featuredModels, translatedModels } from '../src/lib/model-pages.ts';
import { pageType } from '../public/analytics.js';
const translationBundle = await build({ entryPoints:['src/lib/ui-translation.ts'], bundle:true, write:false, format:'cjs', platform:'node' });
const translationModule = { exports:{} };
new Function('module','exports',translationBundle.outputFiles[0].text)(translationModule,translationModule.exports);
const { englishHtml, englishHref } = translationModule.exports;
assert.equal(englishHref('/pricing/?modelId=a%3Ab#api-pricing'), '/en/pricing/?modelId=a%3Ab#api-pricing');
assert.equal(englishHref('/api/account/me'), '/api/account/me');
assert.equal(englishHref('mailto:zhangchen3508@gmail.com'), 'mailto:zhangchen3508@gmail.com');
const original = '<script>{"title":"价格"}</script><pre>价格</pre><blockquote>价格</blockquote>';
assert.equal(englishHtml(original), original);
assert.equal(new JSDOM(englishHtml('<p>COST &amp; COMPUTE / 价格观察</p>')).window.document.querySelector('p').textContent, 'COST & COMPUTE / PRICE OBSERVATIONS');
const release = loadVerifiedRelease(undefined, { select: ['prices','modelIdentities','changes','evidence'] });
const pages = ['','models/','pricing/','method/','agent/','changes/','leaderboards/','weekly/','about/', ...translatedModels().map(p => `model/${p.model.modelId}/`)];
assert(featuredModels().length <= 5);
const homeDoc = new JSDOM(readFileSync('dist/en/index.html','utf8')).window.document;
assert.equal(homeDoc.querySelectorAll('.market-table').length,0);
const chineseHome = new JSDOM(readFileSync('dist/index.html','utf8')).window.document;
assert.deepEqual([...homeDoc.querySelectorAll('[data-recent-platform]')].map(el=>el.dataset.recentPlatform),[...chineseHome.querySelectorAll('[data-recent-platform]')].map(el=>el.dataset.recentPlatform));
const sitemap = readFileSync('dist/sitemap.xml','utf8');
const sitemapUrls = new Set([...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1]));
for (const url of sitemapUrls) { const path = new URL(url).pathname; const counterpart = path.startsWith('/en/') ? path.replace(/^\/en(?=\/)/,'') : `/en${path}`; assert(sitemapUrls.has(`https://daily.maas.click${counterpart}`), `Sitemap language parity: ${path}`); }
for (const page of pages) {
  const doc = new JSDOM(readFileSync(`dist/en/${page}index.html`,'utf8')).window.document;
  assert.equal(doc.documentElement.lang,'en');
  assert.equal(doc.querySelector('link[rel=canonical]').href, `https://daily.maas.click/en/${page}`);
  assert.equal(doc.querySelectorAll('link[rel=alternate]').length,2);
  assert(doc.querySelector('h1').textContent.trim());
  assert(doc.querySelector('meta[name=description]').content.trim());
  assert.equal(doc.querySelectorAll('script[data-maas-analytics]').length,1);
  const noindex = doc.querySelector('meta[name=robots]')?.content.includes('noindex') ?? false;
  assert.equal(sitemap.includes(`https://daily.maas.click/en/${page}`), !noindex, 'empty model pages stay reachable but excluded from sitemap');
  const zh = new JSDOM(readFileSync(`dist/${page}index.html`,'utf8')).window.document;
  assert.equal(zh.querySelector('link[hreflang=en]').href, `https://daily.maas.click/en/${page}`);
  for (const link of doc.querySelectorAll('a[href^="/en/"]')) assert(existsSync(`dist${new URL(link.href,'https://daily.maas.click').pathname.replace(/\/$/,'')}/index.html`), `Missing English link: ${link.href}`);
}
assert(new JSDOM(readFileSync('dist/index.html','utf8')).window.document.querySelector('meta[name=baidu-site-verification]'));
const pricesDoc = new JSDOM(readFileSync('dist/en/pricing/index.html','utf8')).window.document;
const zhPricesDoc = new JSDOM(readFileSync('dist/pricing/index.html','utf8')).window.document;
assert.deepEqual(JSON.parse(pricesDoc.querySelector('#goal-data').textContent), JSON.parse(zhPricesDoc.querySelector('#goal-data').textContent));
for (const path of ['', 'pricing/', 'models/', 'changes/', 'leaderboards/', 'sources/', 'weekly/', 'method/', 'agent/', 'about/', 'compare/']) {
  const en = new JSDOM(readFileSync(`dist/en/${path}index.html`,'utf8')).window.document;
  const zh = new JSDOM(readFileSync(`dist/${path}index.html`,'utf8')).window.document;
  const controls = doc => [...doc.querySelectorAll('main input[id], main select[id], main button[id]')].map(el => [el.id,el.tagName,el.getAttribute('type')]);
  assert.deepEqual(controls(en), controls(zh), `Shared controls: ${path}`);
  const nav = doc => [...doc.querySelectorAll('header nav a')].map(a => new URL(a.href,'https://daily.maas.click').pathname.replace(/^\/en(?=\/)/,''));
  assert.deepEqual(nav(en), nav(zh), `Shared navigation: ${path}`);
  for (const doc of [en, zh]) assert(doc.querySelector('footer a[href="mailto:zhangchen3508@gmail.com"]'));
}
for (const model of featuredModels()) {
  const doc = new JSDOM(readFileSync(`dist/en/model/${model.model.modelId}/index.html`,'utf8')).window.document;
  assert.equal(doc.querySelectorAll('[data-price-id]').length, model.prices.length);
  assert.equal(doc.querySelector('.model-detail').dataset.datasetVersion, release.datasetVersion);
}
for (const [country, expected] of [['CN','zh'],['US','en'],['HK','en']]) {
  assert.equal(preferredLanguage({country,browser:'zh-CN'}),expected);
  assert.equal(preferredLanguage({country,saved:'zh'}),'zh');
  assert.equal(preferredLanguage({country,saved:'en'}),'en');
}
assert.equal(preferredLanguage({explicit:'en',saved:'zh',country:'CN'}),'en');
assert.equal(preferredLanguage({browser:'zh-TW'}),'zh');
assert.equal(preferredLanguage({browser:'en-US'}),'en');
assert.equal(preferredLanguage({}),'zh');
const mem = new Map(); const storage = {getItem:k => mem.get(k),setItem:(k,v) => mem.set(k,v)};
savePreference({localStorage:storage}, 'zh'); assert.equal(readPreference({localStorage:storage}), 'zh');
mem.set('maas-language', JSON.stringify({locale:'en',expires:Date.now()-1})); assert.equal(readPreference({localStorage:storage}),null);
const broken = { getItem(){throw Error();},setItem(){throw Error();} };
assert.doesNotThrow(() => savePreference({localStorage:broken},'en')); assert.equal(readPreference({localStorage:broken}),null);
function win(path, country='US', language='en-US', localStorage=storage) {
  const dom = new JSDOM('<p id="language-note" hidden></p>', {url:`https://daily.maas.click${path}`});
  const nav=[]; let calls=0;
  return {document:dom.window.document,localStorage,navigator:{language},AbortSignal,
    location:{href:dom.window.location.href,replace:url=>nav.push(url)},nav,
    fetch:async()=>{calls++;return {ok:true,json:async()=>({country})}}, get calls(){return calls}};
}
mem.clear(); for (const [country, expected] of [['CN','/'],['US','/en/'],['HK','/en/']]) {
  const w=win('/',country); await startLanguage(w); assert.equal(w.nav[0] ? new URL(w.nav[0]).pathname : '/',expected);
}
for (const path of ['/en/','/en/model/deepseek:deepseek-v4-pro/','/model/deepseek:deepseek-v4-pro/']) {const w=win(path);await startLanguage(w);assert.equal(w.calls,0);assert.equal(w.nav.length,0);}
let w=win('/?lang=zh','US','en-US',broken);await startLanguage(w);assert.equal(w.calls,0);assert.equal(w.nav.length,0);
w=win('/?lang=en','CN');await startLanguage(w);assert.equal(new URL(w.nav[0]).pathname,'/en/');
mem.clear();w=win('/','US','zh-CN');w.fetch=async()=>{throw Error('timeout')};await startLanguage(w);assert.equal(w.nav.length,0);
w=win('/','CN','en-US',broken);w.fetch=async()=>{throw Error('offline')};await startLanguage(w);assert.equal(new URL(w.nav[0]).pathname,'/en/');
const u=switchUrl({location:{href:'https://daily.maas.click/pricing/?modelId=a%3Ab#api-pricing'}},{href:'/en/pricing/',dataset:{translated:'true',language:'en'}});assert.equal(new URL(u).searchParams.get('modelId'),'a:b');assert.equal(new URL(u).hash,'#api-pricing');
assert.equal(new URL(switchUrl({location:{href:'https://daily.maas.click/weekly/?q=foo#bar'}},{href:'/en/',dataset:{translated:'false',language:'en'}})).searchParams.get('untranslated'),'1');
assert.equal(pageType('/en/model/alibaba:qwen-plus/'),'model_detail');assert.equal(pageType('/en/'),'home');
// Exercise English refresh against paginated API responses and a changed version.
const page=featuredModels()[0];const html=readFileSync(`dist/en/model/${page.model.modelId}/index.html`,'utf8');
const dom=new JSDOM(html,{runScripts:'outside-only'});dom.window.AbortSignal=AbortSignal;
const code=stripTypeScriptTypes(readFileSync('src/scripts/model-refresh.ts','utf8').replace(/^import .*;\n/gm,''));
const cellsCode=stripTypeScriptTypes(readFileSync('src/lib/price-display.ts','utf8').replace(/^import .*;\n/gm,'').replace(/export /g,''));
dom.window.eval(cellsCode+'\n'+code);
let call=0;dom.window.fetch=async url=>({ok:true,json:async()=>{call++;return {datasetVersion:release.datasetVersion,items:url.includes('/prices')?(call===1?page.prices.slice(0,2):page.prices.slice(2)):[],page:{nextCursor:call===1?'next':null}};}});
dom.window.document.querySelector('#refresh-model').click();
for(let i=0;i<100 && dom.window.document.querySelector('#refresh-model').disabled;i++) await new Promise(r=>setTimeout(r,5));
assert.equal(dom.window.document.querySelectorAll('#current-prices tbody tr').length,page.prices.length);
assert.match(dom.window.document.querySelector('#refresh-status').textContent,/Current dataset records checked/);
const before=dom.window.document.querySelector('#current-prices').innerHTML;dom.window.fetch=async()=>({ok:true,json:async()=>({datasetVersion:'different'})});dom.window.document.querySelector('#refresh-model').click();await new Promise(r=>setTimeout(r,20));
assert.equal(dom.window.document.querySelector('#current-prices').innerHTML,before);assert.match(dom.window.document.querySelector('#refresh-status').textContent,/retained/);
console.log('Multilingual static content, SEO, exact pricing, preference, navigation and English refresh passed');
