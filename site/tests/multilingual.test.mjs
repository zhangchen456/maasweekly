import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import { JSDOM } from 'jsdom';
import { preferredLanguage, readPreference, savePreference, startLanguage, switchUrl } from '../public/language.js';
import { loadVerifiedRelease } from '../src/lib/release.ts';
import { featuredModels } from '../src/lib/model-pages.ts';
import { englishPriceCells } from '../src/lib/price-display.ts';
import { pageType } from '../public/analytics.js';
const release = loadVerifiedRelease(undefined, { select: ['prices','modelIdentities','changes','evidence'] });
const pages = ['','models/','pricing/','method/','agent/', ...featuredModels().map(p => `model/${p.model.modelId}/`)];
assert.equal(featuredModels().length, 5);
const sitemap = readFileSync('dist/sitemap.xml','utf8');
for (const page of pages) {
  const doc = new JSDOM(readFileSync(`dist/en/${page}index.html`,'utf8')).window.document;
  assert.equal(doc.documentElement.lang,'en');
  assert.equal(doc.querySelector('link[rel=canonical]').href, `https://daily.maas.click/en/${page}`);
  assert.equal(doc.querySelectorAll('link[rel=alternate]').length,2);
  assert(doc.querySelector('h1').textContent.trim());
  assert(doc.querySelector('meta[name=description]').content.trim());
  assert.equal(doc.querySelectorAll('script[data-maas-analytics]').length,1);
  assert(sitemap.includes(`https://daily.maas.click/en/${page}`));
  const zh = new JSDOM(readFileSync(`dist/${page}index.html`,'utf8')).window.document;
  assert.equal(zh.querySelector('link[hreflang=en]').href, `https://daily.maas.click/en/${page}`);
  for (const link of doc.querySelectorAll('a[href^="/en/"]')) assert(existsSync(`dist${new URL(link.href,'https://daily.maas.click').pathname.replace(/\/$/,'')}/index.html`), `Missing English link: ${link.href}`);
}
assert(new JSDOM(readFileSync('dist/index.html','utf8')).window.document.querySelector('meta[name=baidu-site-verification]'));
const pricesDoc = new JSDOM(readFileSync('dist/en/pricing/index.html','utf8')).window.document;
assert.equal(pricesDoc.querySelectorAll('tbody tr').length, release.prices.length);
for (const price of release.prices) {
  const row = pricesDoc.querySelector(`[data-price-id="${price.id}"]`);
  assert.deepEqual([...row.cells].slice(0,11).map(c => c.textContent.trim()), englishPriceCells(price));
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
