import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
import { transform } from 'esbuild';
test('feedback uploads screenshots, preserves failed drafts and same-account refresh, then clears on logout',async()=>{
 const markup=fs.readFileSync(new URL('../src/components/Feedback.astro',import.meta.url),'utf8').split('---')[2].split('<script>')[0];
 const dom=new JSDOM(markup,{url:'http://localhost/feedback/?from=%2Fpro%2F',runScripts:'outside-only'}),win=dom.window,doc=win.document;
 let callback,account={user:{id:'a'}},fail=true,submitted;
 const revoked=[];win.URL.createObjectURL=()=> 'blob:screenshot';win.URL.revokeObjectURL=url=>revoked.push(url);
 win.currentAccount=()=>account;win.onAccountChange=fn=>{callback=fn;};win.openAccountLogin=()=>{};
 win.accountApi=async(route,payload)=>{if(payload){submitted=payload;if(fail)throw new win.Error('暂时无法提交');return{id:'feedback-123'};}return{items:[]};};
 const source=fs.readFileSync(new URL('../src/scripts/feedback.ts',import.meta.url),'utf8').replace(/^import .*;\n/,'');win.eval((await transform(source,{loader:'ts'})).code);
 const el=id=>doc.getElementById(id),settle=()=>new Promise(resolve=>setTimeout(resolve,20));
 try{
  callback(account);await settle();assert.equal(el('feedback-page').value,'/pro/');
  el('feedback-title').value='无法选择多个厂商';el('feedback-description').value='点击两个厂商后，前一个厂商会被取消，无法同时选择。';
  callback(account);assert.equal(el('feedback-title').value,'无法选择多个厂商');
  const file=new win.File([new Uint8Array([1,2,3])],'screenshot.png',{type:'image/png'});
  Object.defineProperty(el('feedback-files'),'files',{configurable:true,value:[file]});el('feedback-files').dispatchEvent(new win.Event('change'));
  assert.equal(el('feedback-previews').querySelectorAll('img').length,1);
  el('feedback-form').dispatchEvent(new win.Event('submit',{cancelable:true}));await settle();
  assert.equal(submitted.images[0].mime,'image/png');assert.equal(submitted.images[0].data,'AQID');
  assert.equal(el('feedback-title').value,'无法选择多个厂商');assert.match(el('feedback-status').textContent,/暂时无法提交/);
  fail=false;el('feedback-form').dispatchEvent(new win.Event('submit',{cancelable:true}));await settle();
  assert.match(el('feedback-status').textContent,/feedback-123/);assert.equal(el('feedback-title').value,'');assert.ok(revoked.length>0);
  el('feedback-title').value='新问题记录';account=null;callback(null);assert.equal(el('feedback-title').value,'');assert.equal(el('feedback-workspace').hidden,true);
 }finally{win.close();}
});
