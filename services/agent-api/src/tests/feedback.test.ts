import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { AccountStore, AccountError } from '../account-store.js';
import { FeedbackStore, IMAGE_LIMIT } from '../feedback-store.js';
import { createAccountHandler } from '../account-http.js';
import type { DatasetHolder } from '../dataset.js';
const secret='feedback-test-secret-at-least-32-characters';
const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf0QAAAAASUVORK5CYII=';
const payload={title:'无法选择多个厂商',description:'打开专业服务页面，点击两个厂商，前一个厂商被取消。',page:'/pro/',images:[{mime:'image/png',data:png}]};
function user(store:AccountStore,email:string){return store.verify(email,store.issueCode(email));}
test('feedback validates inputs, isolates users, stores screenshots privately and tracks reply',()=>{
 const account=new AccountStore(':memory:',Date.now,secret),store=new FeedbackStore(account);
 try {
  const a=user(account,'a@example.test'),b=user(account,'b@example.test');
  const result=store.submit(a.user.id,payload);
  assert.equal(store.list(a.user.id).length,1);assert.equal(store.list(b.user.id).length,0);
  assert.equal(store.screenshot(result.id,0,b.user.id),undefined);
  assert.deepEqual(Buffer.from(store.screenshot(result.id,0,a.user.id)!.bytes),Buffer.from(png,'base64'));
  assert.ok(!JSON.stringify(store.list(a.user.id)).includes('data'));assert.ok(!JSON.stringify(store.list(a.user.id)).includes('email'));
  store.update(result.id,'investigating','已复现，正在修复');assert.equal(store.list(a.user.id)[0]!.status,'investigating');
  store.update(result.id,'resolved','已修复');assert.equal(store.list(a.user.id)[0]!.reply,'已修复');
  assert.throws(()=>store.update(result.id,'deleted',''),Error);
  for(const invalid of [{...payload,title:'短'},{...payload,description:'太短'},{...payload,page:'https://evil.test/'},{...payload,page:'/pro/?token=secret'},{...payload,images:Array(4).fill(payload.images[0])},{...payload,images:[{mime:'image/svg+xml',data:Buffer.from('<svg/>').toString('base64')}]},{...payload,images:[{mime:'image/jpeg',data:png}]},{...payload,images:[{mime:'image/png',data:'%%%'}]},{...payload,images:[{mime:'image/png',data:Buffer.alloc(IMAGE_LIMIT+1).toString('base64')}]}])assert.throws(()=>store.submit(a.user.id,invalid),AccountError);
  assert.equal(store.list(a.user.id).length,1);
  for(let i=0;i<9;i++)store.submit(a.user.id,{...payload,images:[]});
  assert.throws(()=>store.submit(a.user.id,payload),(e:unknown)=>e instanceof AccountError&&e.status===429);
 }finally{account.close();}
});
test('HTTP feedback requires login and same origin; screenshots are private and no-store',async()=>{
 const account=new AccountStore(':memory:',Date.now,secret),a=user(account,'a@example.test'),b=user(account,'b@example.test');
 const origin='http://localhost:4323',server=http.createServer(createAccountHandler(account,null,{} as DatasetHolder,{origin,secure:false}));
 await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
 const base=`http://127.0.0.1:${(server.address() as {port:number}).port}/api/account/`;
 const cookie=(session:string)=>`maas_session=${session}`;
 const post=(data:unknown,session='',from=origin)=>fetch(base+'feedback',{method:'POST',headers:{Origin:from,'Content-Type':'application/json',Cookie:cookie(session)},body:JSON.stringify(data)});
 try {
  assert.equal((await post(payload)).status,401);assert.equal((await post(payload,a.session,'http://evil.test')).status,403);
  const submitted=await post({...payload,padding:'x'.repeat(9000)},a.session);assert.equal(submitted.status,201);const {id}=await submitted.json() as {id:string};
  const image=await fetch(base+`feedback/${id}/image/0`,{headers:{Cookie:cookie(a.session)}});assert.equal(image.status,200);assert.equal(image.headers.get('content-type'),'image/png');assert.equal(image.headers.get('cache-control'),'no-store');assert.equal(image.headers.get('x-content-type-options'),'nosniff');assert.deepEqual(Buffer.from(await image.arrayBuffer()),Buffer.from(png,'base64'));
  assert.equal((await fetch(base+`feedback/${id}/image/0`,{headers:{Cookie:cookie(b.session)}})).status,404);
  assert.equal((await fetch(base+`feedback/${id}/image/0`)).status,401);
  const listed=await(await fetch(base+'feedback',{headers:{Cookie:cookie(b.session)}})).json() as {items:unknown[]};assert.equal(listed.items.length,0);
 }finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));account.close();}
});
