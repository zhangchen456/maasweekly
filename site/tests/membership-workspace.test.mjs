import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {transform} from 'esbuild';
const read=p=>fs.readFileSync(new URL(p,import.meta.url),'utf8');
const compile=async s=>(await transform(s.replace(/^import[^\n]*\n/gm,'').replace(/export /g,''),{loader:'ts'})).code;
const settle=()=>new Promise(r=>setTimeout(r,0));
test('visitor prompts login and resumes original usage; Free compares 3, Plus 10, logout restores visitor allowance',async()=>{
 let html=read('../src/components/PriceWorkspace.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
 const prices=Array.from({length:11},(_,i)=>'model'+String(i).padStart(2,'0')).flatMap(model=>['input','output'].map(component=>({provider:'openai',model,component,amount:'1',amount_per_1m:'1',currency:'CNY',unit_quantity:1000000,unit_name:'token',region:'global',billing_mode:'realtime',service_tier:'standard',context_band:null,time_condition:null,observed_at:1,field_state:'confirmed'})));
 html+='<script id="goal-data" type="application/json">'+JSON.stringify({prices,meta:{}})+'</script>';
 const d=new JSDOM(html,{url:'https://daily.maas.click/pricing/',runScripts:'outside-only'}),w=d.window;let user=null,limit=3,onChange,login=0;
 try{
  w.eval(await compile(read('../src/lib/workspace-share.ts')));w.currentAccount=()=>user;w.onAccountChange=f=>onChange=f;w.openAccountLogin=()=>login++;w.accountApi=async()=>({limits:{compare:limit}});w.formatTimestamp=()=>'';w.recordWorkspaceResult=()=>{};w.savedState=()=>()=>{};w.fetch=async()=>({json:async()=>({membershipV2:true})});w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.eval(await compile(read('../src/scripts/price-workspace.ts')));await settle();
  const count=()=>w.document.querySelectorAll('#selection button').length;const add=()=>{let b=w.document.querySelector('button.add:not(.selected)');if(!b){w.document.getElementById('next').click();b=w.document.querySelector('button.add:not(.selected)');}return b;};
  assert.equal(count(),1);const input=w.document.getElementById('input-volume');input.value='42';input.dispatchEvent(new w.Event('change',{bubbles:true}));add().click();assert.equal(login,1);assert.equal(count(),1);
  user={user:{id:'free'}};onChange(user);await settle();assert.equal(count(),2);assert.equal(input.value,'42');
  add().click();assert.equal(count(),3);add().click();assert.equal(count(),3);assert.ok(w.document.querySelector('#toast a[href="/subscription/"]'));
  limit=10;onChange(user);await settle();for(let i=0;i<7;i++)add().click();assert.equal(count(),10);add().click();assert.equal(count(),10);
  user=null;onChange(null);await settle();assert.equal(count(),1);
 }finally{w.close();}
});
