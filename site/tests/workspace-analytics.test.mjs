import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {transform} from 'esbuild';
const read=p=>fs.readFileSync(new URL(p,import.meta.url),'utf8');
const compile=async s=>(await transform(s.replace(/^import[^\n]*\n/gm,'').replace(/export /g,''),{loader:'ts'})).code;
test('costs use the published FX snapshot and preserve explicit user overrides',async()=>{
 const template=read('../src/components/PriceWorkspace.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
 const prices=['input','output'].map((component,i)=>({provider:'openai',model:'a',modelId:'openai:a',component,amount:String([2,8][i]),amount_per_1m:String([2,8][i]),currency:'USD',unit_quantity:1000000,unit_name:'token',region:'global',billing_mode:'realtime',service_tier:'standard',context_band:null,time_condition:null,observed_at:1,field_state:'confirmed'}));
 for(const [fx_snapshot,expected] of [[{base:'USD',rates:{CNY:'7.1',USD:'1'},as_of:'2026-09-07'},7.1],[{base:'CNY',rates:{USD:'.125'}},8],[{base:'USD',rates:{CNY:'0'}},7]]){
  const html='<html lang="en"><body>'+template+'<script id="goal-data" type="application/json">'+JSON.stringify({prices,meta:{},fx_snapshot,modelIdentities:{models:[{modelId:'openai:a',modelName:'A'}],families:[]}})+'</script></body></html>';
  const d=new JSDOM(html,{url:'https://daily.maas.click/en/pricing/?modelId=openai:a',runScripts:'outside-only'}),w=d.window;
  w.eval(await compile(read('../src/lib/workspace-share.ts')));w.onAccountChange=()=>{};w.currentAccount=()=>null;w.formatTimestamp=v=>v;w.savedState=(_key,defaults,apply)=>{apply(defaults);return()=>{}};w.recordWorkspaceResult=()=>{};
  w.eval(await compile(read('../src/scripts/price-workspace.ts')));
  const fx=w.document.getElementById('fx'),label=w.document.getElementById('fx-label');
  assert.equal(Number(fx.value),expected);
  const currency=w.document.getElementById('display-currency');currency.value='CNY';currency.dispatchEvent(new w.Event('change'));
  assert.match(w.document.getElementById('comparison-table').textContent,new RegExp('¥'+String(expected*4).replace('.','\\.')));
  if(fx_snapshot.as_of){assert.match(label.textContent,/Reference estimate · not a live exchange rate · 2026-09-07/);}
  fx.value='9';fx.dispatchEvent(new w.Event('change'));assert.match(w.document.getElementById('comparison-table').textContent,/¥36/);assert.equal(label.textContent,'Manual estimate · not a live exchange rate');
  d.window.close();
 }
});
test('optional result collection excludes amounts and respects opt-out, DNT and anonymous accounts',async()=>{
 const d=new JSDOM('',{url:'https://daily.maas.click/pricing/',runScripts:'outside-only'}),w=d.window,calls=[],events=[];
 w.currentAccount=()=>null;w.accountApi=async(...args)=>calls.push(args);w.document.addEventListener('maas:workspace-result',e=>events.push(e.detail));
 w.eval(await compile(read('../src/scripts/workspace-analytics.ts')));
 w.recordWorkspaceResult('comparison_completed');assert.equal(events.length,1);assert.equal(calls.length,0);
 w.currentAccount=()=>({user:{id:'private'}});w.recordWorkspaceResult('cost_estimate_completed_v2');assert.equal(calls.length,1);assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1])),{event:'cost_estimate_completed_v2'});
 w.localStorage.setItem('umami.disabled','1');w.recordWorkspaceResult('comparison_completed');assert.equal(calls.length,1);
 w.localStorage.clear();Object.defineProperty(w.navigator,'doNotTrack',{value:'1'});w.recordWorkspaceResult('comparison_completed');assert.equal(calls.length,1);d.window.close();
});
test('workspace initial renders do not count; completed user comparisons and committed estimates do',async()=>{
 let html=read('../src/components/PriceWorkspace.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
 const prices=['a','b','c'].flatMap(model=>['input','output'].map(component=>({provider:'openai',model,component,amount:'1',amount_per_1m:'1',currency:'CNY',unit_quantity:1000000,unit_name:'token',region:'global',billing_mode:'realtime',service_tier:'standard',context_band:null,time_condition:null,observed_at:1,field_state:'confirmed'})));
 html+='<script id="goal-data" type="application/json">'+JSON.stringify({prices,meta:{}})+'</script>';
 const d=new JSDOM(html,{url:'https://daily.maas.click/pricing/',runScripts:'outside-only'}),w=d.window,events=[];
 w.eval(await compile(read('../src/lib/workspace-share.ts')));w.onAccountChange=()=>{};w.currentAccount=()=>null;w.formatTimestamp=()=>'';w.savedState=()=>()=>{};w.recordWorkspaceResult=e=>events.push(e);w.HTMLElement.prototype.scrollIntoView=()=>{};
 w.eval(await compile(read('../src/scripts/price-workspace.ts')));assert.equal(events.length,0);
 const clear=w.document.getElementById('clear');clear.click();
 // Select the actual catalog action, excluding selected models.
 const add=()=>w.document.querySelector('button.add:not(.selected)');
 assert.ok(add());add().click();assert.equal(events.length,0);add().click();assert.deepEqual(events,['comparison_completed']);
 const volume=w.document.getElementById('input-volume');volume.value='5';volume.dispatchEvent(new w.Event('input'));assert.equal(events.length,1);volume.dispatchEvent(new w.Event('change'));assert.equal(events.at(-1),'cost_estimate_completed_v2');
 clear.click();volume.dispatchEvent(new w.Event('change'));assert.equal(events.length,2);d.window.close();
});

test('single-model entry and share restore override saved preferences without counting initial renders',async()=>{
 let html=read('../src/components/PriceWorkspace.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
 const prices=['a','b'].flatMap(model=>['input','output'].map(component=>({provider:'openai',model,modelId:'openai:'+model,component,amount:'2',amount_per_1m:'2',currency:'CNY',unit_quantity:1000000,unit_name:'token',region:'global',billing_mode:'realtime',service_tier:'standard',context_band:null,time_condition:null,observed_at:1,field_state:'confirmed'})));
 html+='<script id="goal-data" type="application/json">'+JSON.stringify({prices,meta:{},modelIdentities:{models:[{modelId:'openai:a',modelName:'A'},{modelId:'openai:b',modelName:'B'}],families:[]}})+'</script>';
 const setup=async url=>{const d=new JSDOM(html,{url,runScripts:'outside-only'}),w=d.window;w.eval(await compile(read('../src/lib/workspace-share.ts')));w.formatTimestamp=()=>'';w.recordWorkspaceResult=()=>{};w.currentAccount=()=>null;w.onAccountChange=()=>{};w.savedState=(_key,defaults,apply)=>{apply({...defaults,selected:[],input:1,output:.25});return()=>{}};let clipboard='';Object.defineProperty(w.navigator,'clipboard',{value:{writeText:async x=>{clipboard=x;}}});w.eval(await compile(read('../src/scripts/price-workspace.ts')));return{d,w,clipboard:()=>clipboard};};
 const first=await setup('https://daily.maas.click/pricing/?modelId=openai:a&input=300&output=60#compare');
 assert.equal(first.w.document.querySelectorAll('#selection button').length,1);assert.equal(first.w.document.getElementById('input-volume').value,'300');
 first.w.document.getElementById('share-result').click();await new Promise(r=>setTimeout(r,0));const link=first.clipboard();assert.ok(link.includes('#calc='));
 const second=await setup(link);assert.equal(second.w.document.getElementById('input-volume').value,'300');assert.equal(second.w.document.querySelectorAll('#selection button').length,1);
 second.w.document.getElementById('output-volume').value='-1';second.w.document.getElementById('share-result').click();await new Promise(r=>setTimeout(r,0));assert.equal(second.clipboard(),'');
 first.d.window.close();second.d.window.close();
});
