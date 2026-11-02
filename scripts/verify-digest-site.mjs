/** Render the actual homepage/archive with bound, legacy, aged and empty data. */
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const require=createRequire(path.join(root,'site/package.json'));
const {JSDOM}=require('jsdom');const {transform}=require('esbuild');
const {capturePage}=await import(pathToFileURL(path.join(root,'services/agent-api/dist/site-http.js')));
const code=(await transform(readFileSync(path.join(root,'site/src/scripts/explore.ts'),'utf8').replace(/^import .*;\n/,''),{loader:'ts',format:'iife'})).code;
const id='obs_'+'a'.repeat(64),oldId='obs_'+'b'.repeat(64),bound='Fixture bound excerpt',legacy='Fixture legacy AI summary';
const source={platform:'OpenAI',source_type:'blog',url:'https://openai.com/blog/',permalink:`/item/${id}/`,kind:'substantive',added_count:1,removed_count:0,added_lines:['Fixture source excerpt'],removed_lines:[],pairs:[]};
const daily={updated_at:'2026-11-02T10:00:00Z',days:[
 {date:'2026-11-02',changed:[source],highlights:[{platform:'OpenAI',logo_summary:'Fixture platform activity',items:[{text:bound,type:'release',evidenceVersion:1,evidence:[{id:'de_'+'c'.repeat(64),url:'https://openai.com/news/',observedDate:'2026-11-02'}]}]}]},
 {date:'2026-10-31',changed:[source],highlights:[{platform:'OpenAI',logo_summary:'Fixture platform activity',items:[{text:legacy,type:'sunset'}]}]},
]};
const currentWeek={week:'2026-W45',start:'2026-11-02',end:'2026-11-08',days:{'2026-11-02':{substantive:1}},highlights:[],totals:{substantive:1}};
const week={week:'2026-W44',start:'2026-10-26',end:'2026-11-01',days:{'2026-10-31':{substantive:1}},highlights:[],totals:{substantive:1}};
const aged={week:'2026-W36',start:'2026-08-31',end:'2026-09-06',days:{'2026-09-02':{substantive:1}},highlights:[{platform:'OpenAI',date:'2026-09-02',text:'Fixture aged summary',type:'release'}],totals:{substantive:1}};
const records=[{id,date:'2026-10-31',platform:'OpenAI',title:'Fixture source',status:'active',permalink:`/item/${id}/`},{id:oldId,date:'2026-09-02',platform:'OpenAI',title:'Fixture old source',status:'active',permalink:`/item/${oldId}/`}];
let empty=false;
const bridge={version:1,membership:()=>({tier:'plus',cutoff:null}),release:()=>({datasetVersion:'ds_'+'1'.repeat(64),dataThrough:'2026-11-02',coverage:{changes:{from:'2026-09-02',to:'2026-11-03',count:2},prices:{facts:0}},weekly:[{id:'2026-10-27',title:'Fixture report',date:'2026-10-27',period:'Fixture period'}],changes:[],prices:[],evidence:[],modelIdentities:{models:[],families:[]}}),
 projection:name=>{
  if(name==='translations-en.json')return {texts:{}};
  if(name==='daily_changes.json')return empty?{days:[]}:daily;
  if(name==='weekly-digest.json')return empty?[]:[currentWeek,week,aged];
  if(name==='record-index.json')return records;
  throw new Error('Unexpected projection '+name);
 },json:()=>null,hasItem:()=>true,record:async()=>null,revisions:async()=>[],facts:async()=>[],evidence:async()=>null,weekly:()=>null,dailyWeek:name=>name===week.week?week:name===aged.week?aged:null};
const original=JSON.stringify({daily,week,aged,records});
const outputIndex=process.argv.indexOf('--output');const output=outputIndex>=0?process.argv[outputIndex+1]:null;
const key=Symbol.for('maas.site-data.v1');globalThis[key]=bridge;let rendered=0;
try {
 const {handler}=await import(pathToFileURL(path.join(root,'site/dist/server/entry.mjs')));
 for(const route of ['/','/en/','/daily/2026-W44/','/en/daily/2026-W44/','/daily/2026-W36/','/en/daily/2026-W36/']) {
  const result=await capturePage(handler,route,'http://localhost');assert.equal(result.status,200,route);rendered++;
  const html=result.body.toString();const dom=new JSDOM(html,{url:'https://daily.maas.click'+route,runScripts:'outside-only'});const {window}=dom;const doc=window.document;
  assert(!html.includes('未逐条核验')&&!html.includes('not individually verified'),route);
  assert.equal(doc.querySelectorAll('.digest-note').length,1,route+' one shared explanation');
  assert.equal(doc.querySelector('.digest-note').hasAttribute('open'),false);
  const folders=[...doc.querySelectorAll('.digest-sources')];assert.equal(folders.length,1,route+' contextual source access');
  assert.equal(folders[0].hasAttribute('open'),false);assert(folders[0].querySelector('a'));
  const sourceHrefs=[...folders[0].querySelectorAll('a')].map(a=>a.getAttribute('href'));assert.equal(new Set(sourceHrefs).size,sourceHrefs.length,'each source or record appears once');
  assert.equal(doc.querySelector('p details'),null,'disclosures are valid block markup');
  if(route==='/') {
   const row=doc.querySelector('.vendor-change-item[data-date="2026-10-31"]');assert.equal(row.dataset.type,'other');assert.equal(row.querySelector('p').textContent,legacy);
   assert.equal(row.querySelectorAll('a.digest-evidence').length,0,'context is never marked bound');
   assert(folders[0].querySelector('a[href="https://openai.com/blog/"]'));assert(folders[0].querySelector(`a[href="/item/${id}/"]`));
   assert(doc.querySelector('a.digest-evidence[href="https://openai.com/news/"]'),'actual bound proof retained');
  }
  if(route.includes('W36'))assert(folders[0].querySelector(`a[href="${route.startsWith('/en/')?'/en':''}/item/${oldId}/"]`),'aged index-only record remains accessible');
  if(route==='/') {
   window.savedState=()=>()=>{};window.currentAccount=()=>null;let copied='';Object.defineProperty(window.navigator,'clipboard',{value:{writeText:async text=>{copied=text;}}});
   window.eval(code);doc.querySelector('[data-range="today"]').click();assert.equal(rowHidden(doc,'2026-10-31'),true);
   doc.querySelector('[data-range="week"]').click();assert.equal(rowHidden(doc,'2026-10-31'),false);
   doc.querySelector('[data-filter="sunset"]').click();assert(doc.querySelector('.vendor-change-row').hidden,'legacy inference cannot become sunset filter result');
   doc.querySelector('[data-filter="all"]').click();doc.querySelector('#copy-brief').click();await Promise.resolve();
   assert(copied.includes(legacy)&&copied.includes(bound));assert(!copied.includes('openai.com'),'folded source controls do not pollute copied summaries');
   folders[0].open=true;assert(folders[0].querySelector('a').href.startsWith('https://openai.com/'));
  }
  if(output){const dir=path.join(output,route);mkdirSync(dir,{recursive:true});writeFileSync(path.join(dir,'index.html'),html);}
  dom.window.close();
 }
 empty=true;
 for(const route of ['/','/en/']){const result=await capturePage(handler,route,'http://localhost');assert.equal(result.status,200);assert(!result.body.toString().includes('undefined 的变化'));rendered++;}
 assert.equal(JSON.stringify({daily,week,aged,records}),original,'display does not rewrite source or editorial data');
 console.log(JSON.stringify({status:'passed',rendered,sourceBinding:'date/platform only',boundEvidencePreserved:true,legacyCategoriesDowngraded:true,sourceDisclosures:'native/closed',homeFiltersAndCopy:'passed',locales:['zh','en'],sourceMutation:false}));
} finally {delete globalThis[key];}
function rowHidden(doc,date){return doc.querySelector(`.vendor-change-item[data-date="${date}"]`).hidden;}
