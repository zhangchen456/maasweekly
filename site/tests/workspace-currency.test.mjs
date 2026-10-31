import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {JSDOM} from 'jsdom';
import {transform} from 'esbuild';
const read=p=>fs.readFileSync(new URL(p,import.meta.url),'utf8');
const compile=async s=>(await transform(s.replace(/^import[^\n]*\n/gm,'').replace(/export /g,''),{loader:'ts'})).code;
const template=read('../src/components/PriceWorkspace.astro').replace(/^---[\s\S]*?---/,'').replace(/<script[\s\S]*?<\/script>/g,'');
const prices=['a','b'].flatMap(model=>['input','output'].map((component,i)=>({provider:'openai',model,modelId:'openai:'+model,component,amount:String((model==='a'?[2,8]:[14.2,56.8])[i]),amount_per_1m:String((model==='a'?[2,8]:[14.2,56.8])[i]),currency:model==='a'?'USD':'CNY',unit_quantity:1000000,unit_name:'token',region:'global',billing_mode:'realtime',service_tier:'standard',context_band:null,time_condition:null,observed_at:1,field_state:'confirmed'})));
const data={prices,meta:{published_at:1},fx_snapshot:{base:'USD',rates:{CNY:'7.1'}},modelIdentities:{models:['a','b'].map(k=>({modelId:'openai:'+k,modelName:k})),families:[]}};
async function setup({lang='en',url='https://daily.maas.click/en/pricing/?modelId=openai:a',saved={}}={}){
 const d=new JSDOM('<html lang="'+lang+'"><body>'+template+'<script id="goal-data" type="application/json">'+JSON.stringify(data)+'</script></body></html>',{url,runScripts:'outside-only'}),w=d.window;
 let clipboard='',stored,restore;
 w.eval(await compile(read('../src/lib/workspace-share.ts')));w.formatTimestamp=v=>String(v);w.recordWorkspaceResult=()=>{};w.currentAccount=()=>null;w.onAccountChange=()=>{};w.savedState=(_key,defaults,apply)=>{restore=value=>apply({...defaults,...value});restore(saved);return value=>{stored=value;}};
 Object.defineProperty(w.navigator,'clipboard',{value:{writeText:async value=>{clipboard=value;}}});w.eval(await compile(read('../src/scripts/price-workspace.ts')));
 return {w,close:()=>d.window.close(),get clipboard(){return clipboard;},get stored(){return stored;},restore,
 change(id,value){const e=w.document.getElementById(id);e.value=value;e.dispatchEvent(new w.Event('change',{bubbles:true}));},
 async copy(id){w.document.getElementById(id).click();await new Promise(r=>setTimeout(r,0));return clipboard;}};
}
test('English defaults to USD; native USD amounts ignore FX and CNY amounts convert with the stated rate',async()=>{
 const a=await setup();try{
  assert.equal(a.w.document.getElementById('display-currency').value,'USD');assert.match(a.w.document.getElementById('plot').textContent,/US\$4/);
  a.change('fx','9');assert.match(a.w.document.getElementById('plot').textContent,/US\$4/);
  a.change('display-currency','CNY');assert.match(a.w.document.getElementById('plot').textContent,/¥36/);assert.equal(a.stored.currency,'CNY');
  const summary=await a.copy('copy-result');assert.match(summary,/currency CNY/);assert.match(summary,/¥36/);assert.match(summary,/1 USD = 9 CNY/);
  a.change('display-currency','USD');assert.match(await a.copy('copy-result'),/US\$4/);
 }finally{a.close();}
 const b=await setup({url:'https://daily.maas.click/en/pricing/?modelId=openai:b'});try{assert.match(b.w.document.getElementById('plot').textContent,/US\$4/);b.change('display-currency','CNY');assert.match(b.w.document.getElementById('plot').textContent,/¥28\.4/);}finally{b.close();}
});
test('explicit currency survives save/login restoration and shares across languages; legacy shares stay CNY',async()=>{
 const a=await setup({saved:{currency:'CNY'}});try{
  assert.equal(a.w.document.getElementById('display-currency').value,'CNY');a.change('display-currency','USD');
  a.restore({currency:'CNY'});assert.equal(a.w.document.getElementById('display-currency').value,'USD');
  const link=await a.copy('share-result'),payload=JSON.parse(decodeURIComponent(new URL(link).hash.slice(6)));assert.equal(payload.v,2);assert.equal(payload.currency,'USD');
  const b=await setup({lang:'zh',url:link,saved:{currency:'CNY'}});try{assert.equal(b.w.document.getElementById('display-currency').value,'USD');assert.match(b.w.document.getElementById('plot').textContent,/US\$4/);}finally{b.close();}
  payload.v=1;delete payload.currency;const legacy=new URL(link);legacy.hash='calc='+encodeURIComponent(JSON.stringify(payload));
  const c=await setup({url:legacy.href,saved:{currency:'USD'}});try{assert.equal(c.w.document.getElementById('display-currency').value,'CNY');assert.match(c.w.document.getElementById('plot').textContent,/¥28\.4/);}finally{c.close();}
 }finally{a.close();}
 const zh=await setup({lang:'zh',url:'https://daily.maas.click/pricing/?modelId=openai:a'});try{assert.equal(zh.w.document.getElementById('display-currency').value,'CNY');}finally{zh.close();}
});
