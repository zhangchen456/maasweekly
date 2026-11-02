import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {transform} from 'esbuild';
const read=p=>fs.readFileSync(new URL(p,import.meta.url),'utf8');
const settle=()=>new Promise(r=>setTimeout(r,0));
test('project editor previews before saving, opens the new detail, separates email opt-in and clears private data on logout',async()=>{
 const html=read('../src/components/Projects.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
 const d=new JSDOM(html,{url:'https://daily.maas.click/projects/',runScripts:'outside-only'}),w=d.window,doc=w.document;let listener,stored=null;const calls=[];
 const rate={id:'input',amount:'2',currency:'USD',unitQuantity:1000000,observedAt:'2026-11-02T00:00:00Z',sourceUrl:'https://openai.com/'};
 const snapshot={cost:'360.000000000000',complete:true,baselineDelta:'0.000000000000',dataThrough:'2026-11-02',checkedAt:1,lines:[{label:'Primary',modelId:'openai:a',modelName:'A',platform:'openai',state:'ok',cost:'360',input:rate,output:{...rate,id:'output',amount:'8'}}]};
 const quote={key:'q1',modelId:'openai:a',modelName:'A',modelKey:'a',provider:'openai',platform:'openai',currency:'USD',region:'global',billingMode:'realtime',serviceTier:'standard',contextBand:null,timeCondition:null,state:'ok',inputPriceId:'input',outputPriceId:'output'};
 w.currentAccount=()=>({user:{id:'owner'}});w.onAccountChange=f=>listener=f;w.openAccountLogin=()=>{};w.HTMLElement.prototype.scrollIntoView=()=>{};
 w.accountApi=async(route,body)=>{calls.push({route,body});if(route==='projects/catalog')return {items:[quote],datasetVersion:'ds_1'};if(route==='projects/preview')return {baseline:{...body.project,datasetVersion:'ds_1',cost:'360'},snapshot};if(route==='projects'&&body){stored={id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',name:body.project.name,status:'active',revision:1,emailEnabled:false,serviceActive:true,baseline:{...body.project,lines:[{...body.project.lines[0],input:rate,output:{...rate,id:'output'}}],cost:'360'},latest:snapshot,baselines:[],events:[]};return stored;}if(route==='projects')return {items:stored?[stored]:[],plus:true,mailAvailable:true};if(route.includes('/action')){stored.emailEnabled=body.enabled;return stored;}return stored;};
 try{
  const source=read('../src/scripts/projects.ts').replace(/^import[^\n]*\n/gm,'');w.eval((await transform(source,{loader:'ts'})).code);listener({user:{id:'owner'}});await settle();
  doc.getElementById('project-new').click();await settle();doc.getElementById('project-name').value='PRIVATE_PROJECT';doc.querySelector('.project-line select').value='q1';doc.querySelector('.project-line select').dispatchEvent(new w.Event('change',{bubbles:true}));
  doc.getElementById('project-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await settle();assert.equal(calls.filter(c=>c.route==='projects'&&c.body).length,0);assert.equal(doc.getElementById('project-confirm').hidden,false);
  doc.getElementById('project-confirm').click();await settle();await settle();assert.equal(doc.querySelector('#project-detail h2').textContent,'PRIVATE_PROJECT');assert.ok(w.location.search.includes('id='));assert.equal(stored.emailEnabled,false);assert.equal(calls.some(c=>c.route.endsWith('/action')),false);
  [...doc.querySelectorAll('#project-detail button')].find(b=>b.textContent.includes('开启每日')).click();await settle();assert.equal(stored.emailEnabled,true);
  listener(null);assert.equal(doc.getElementById('project-detail').textContent,'');assert.equal(doc.getElementById('project-name').value,'');assert.equal(doc.getElementById('project-list').textContent,'');
 }finally{w.close();}
});
