/** Render actual built Astro pages under a small trusted membership/data bridge. */
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
const {capturePage}=await import(pathToFileURL(path.join(root,'services/agent-api/dist/site-http.js')));
let tier='visitor';
const id='obs_'+'a'.repeat(64),secret='HISTORICAL_DIFF_MUST_NOT_LEAK';
const record={id,date:'2026-10-01',platform:'OpenAI',sourceType:'blog',kind:'substantive',status:'active',title:'Public change fact',summary:'Public factual summary',summaryOrigin:'rule',revision:1,permalink:`/item/${id}/`,sourceUrl:'https://openai.com/',diff:{pairs:[{before:secret,after:'after'}],added_lines:[],removed_lines:[]},diffCompleteness:'complete'};
const bridge={version:1,membership:()=>({tier,cutoff:tier==='plus'?null:tier==='free'?'2026-10-04':'2026-10-27'}),release:()=>({datasetVersion:'ds_'+'1'.repeat(64),dataThrough:'2026-11-02',coverage:{changes:{from:'2026-10-01',to:'2026-11-03',count:2},prices:{facts:0}},weekly:[],changes:[],prices:[],evidence:[],modelIdentities:{models:[],families:[]}}),
 projection:()=>({texts:{}}),json:()=>null,hasItem:()=>true,record:async()=>record,revisions:async()=>[],facts:async()=>[],evidence:async()=>null,weekly:()=>null,dailyWeek:()=>null};
const key=Symbol.for('maas.site-data.v1');globalThis[key]=bridge;
try{
 const {handler}=await import(pathToFileURL(path.join(root,'site/dist/server/entry.mjs')));
 for(tier of ['visitor','free','plus']){
  for(const route of ['/subscription/','/en/subscription/','/account/','/en/account/','/changes/','/en/changes/','/agent/','/en/agent/']){
   const result=await capturePage(handler,route,'http://localhost');assert.equal(result.status,200,`${tier} ${route}`);
   const html=result.body.toString();assert.ok(!html.includes('>undefined<'),route+' renders undefined');
   if(route.includes('subscription')){assert.ok(html.includes('3,000'));assert.ok(html.includes('100'));assert.ok(!html.includes('P1'));}
   if(route.includes('account')){assert.ok(html.includes('membership-tools'));assert.match(html,/noindex/);assert.ok(html.indexOf('membership-tools')<html.indexOf('</body>'));}
  }
  for(const route of [`/item/${id}/`,`/en/item/${id}/`]){
   const result=await capturePage(handler,route,'http://localhost');assert.equal(result.status,200);const html=result.body.toString();assert.ok(html.includes('openai.com'));assert.equal(html.includes(secret),tier==='plus',tier+' history access');
  }
 }
 console.log(JSON.stringify({status:'passed',rendered:30,tiers:['visitor','free','plus'],historicalDiffProtected:true,fixture:true}));
}finally{delete globalThis[key];}
