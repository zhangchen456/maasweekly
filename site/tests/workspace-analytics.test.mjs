import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {transform} from 'esbuild';
const read=p=>fs.readFileSync(new URL(p,import.meta.url),'utf8');
const compile=async s=>(await transform(s.replace(/^import[^\n]*\n/gm,'').replace(/export /g,''),{loader:'ts'})).code;
test('optional result collection excludes amounts and respects opt-out, DNT and anonymous accounts',async()=>{
 const d=new JSDOM('',{url:'https://daily.maas.click/pricing/',runScripts:'outside-only'}),w=d.window,calls=[],events=[];
 w.currentAccount=()=>null;w.accountApi=async(...args)=>calls.push(args);w.document.addEventListener('maas:workspace-result',e=>events.push(e.detail));
 w.eval(await compile(read('../src/scripts/workspace-analytics.ts')));
 w.recordWorkspaceResult('comparison_completed');assert.equal(events.length,1);assert.equal(calls.length,0);
 w.currentAccount=()=>({user:{id:'private'}});w.recordWorkspaceResult('cost_estimate_completed');assert.equal(calls.length,1);assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1])),{event:'cost_estimate_completed'});
 w.localStorage.setItem('umami.disabled','1');w.recordWorkspaceResult('comparison_completed');assert.equal(calls.length,1);
 w.localStorage.clear();Object.defineProperty(w.navigator,'doNotTrack',{value:'1'});w.recordWorkspaceResult('comparison_completed');assert.equal(calls.length,1);d.window.close();
});
test('workspace initial renders do not count; completed user comparisons and committed estimates do',async()=>{
 let html=read('../src/components/PriceWorkspace.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
 const prices=['a','b','c'].flatMap(model=>['input','output'].map(component=>({provider:'openai',model,component,amount:'1',amount_per_1m:'1',currency:'CNY',unit_quantity:1000000,unit_name:'token',region:'global',billing_mode:'realtime',service_tier:'standard',context_band:null,time_condition:null,observed_at:1,field_state:'confirmed'})));
 html+='<script id="goal-data" type="application/json">'+JSON.stringify({prices,meta:{}})+'</script>';
 const d=new JSDOM(html,{url:'https://daily.maas.click/pricing/',runScripts:'outside-only'}),w=d.window,events=[];
 w.formatTimestamp=()=>'';w.savedState=()=>()=>{};w.recordWorkspaceResult=e=>events.push(e);w.HTMLElement.prototype.scrollIntoView=()=>{};
 w.eval(await compile(read('../src/scripts/price-workspace.ts')));assert.equal(events.length,0);
 const clear=w.document.getElementById('clear');clear.click();
 // Select the actual catalog action, excluding selected models.
 const add=()=>w.document.querySelector('button.add:not(.selected)');
 assert.ok(add());add().click();assert.equal(events.length,0);add().click();assert.deepEqual(events,['comparison_completed']);
 const volume=w.document.getElementById('input-volume');volume.value='5';volume.dispatchEvent(new w.Event('input'));assert.equal(events.length,1);volume.dispatchEvent(new w.Event('change'));assert.equal(events.at(-1),'cost_estimate_completed');
 clear.click();volume.dispatchEvent(new w.Event('change'));assert.equal(events.length,2);d.window.close();
});
