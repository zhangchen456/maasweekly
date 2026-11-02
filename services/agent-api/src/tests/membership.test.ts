import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {AccountStore} from '../account-store.js';
import {ProStore} from '../pro-store.js';
import {Membership,historyCutoff,membershipContext} from '../membership.js';
import {DatasetHolder} from '../dataset.js';
import {ReleaseFixture} from './fixture.js';
import {runListQueryAsync,getItem} from '../query.js';
import {createAccountHandler} from '../account-http.js';
import {deliverDigests} from '../account-digest.js';
import type {ChangeEntity} from '../public-contract/entities.js';
const SECRET='membership-test-secret-more-than-32-characters';
const catalog={models:Array.from({length:5},(_,n)=>({modelId:`openai:m${n}`,modelName:`Model ${n}`})),families:[]};
function setup(){let now=Date.parse('2026-11-02T01:15:00Z');const store=new AccountStore(':memory:',()=>now,SECRET);const user=store.verify('a@example.com',store.issueCode('a@example.com'));const pro=new ProStore(store);const m=new Membership(store,pro,false);return {store,user,pro,m,setTime:(n:number)=>now=n};}
test('Free/Plus quotas follow effective entitlement; revoked, expired and replayed credentials cannot grant Plus',()=>{
 const s=setup();try{
  for(const model of catalog.models.slice(0,3))s.store.watch(s.user.user.id,model.modelId,catalog);
  assert.throws(()=>s.store.watch(s.user.user.id,'openai:m3',catalog),/3/);
  const token=s.m.mint(s.user.user.id,'Agent');const req={headers:{authorization:`Bearer ${token.token}`}} as http.IncomingMessage;
  assert.equal(s.m.access(req).tier,'free');assert.ok(!JSON.stringify(s.m.tokens(s.user.user.id)).includes(token.token));
  s.pro.grant(s.user.user.id,s.store.now()-1,s.store.now()+1000,'test','test');assert.equal(s.m.access(req).tier,'plus');
  s.store.watch(s.user.user.id,'openai:m3',catalog);
  s.setTime(s.store.now()+1001);assert.equal(s.m.access(req).tier,'free');
  s.m.revoke(s.user.user.id,token.id);assert.throws(()=>s.m.access(req));
 }finally{s.store.close();}
});
test('Monthly meter is per-account across tokens, refunds failures, and resets at Shanghai month boundary',()=>{
 const s=setup();try{
  const id=s.user.user.id;for(let n=0;n<100;n++)s.m.reserve(id);assert.throws(()=>s.m.reserve(id),/额度/);
  s.setTime(Date.parse('2026-11-30T16:00:00Z'));assert.equal(s.m.usage(id).month,'2026-12');assert.equal(s.m.usage(id).used,0);
  const refund=s.m.reserve(id);assert.equal(s.m.usage(id).used,1);refund();assert.equal(s.m.usage(id).used,0);
 }finally{s.store.close();}
});
test('History restrictions apply to signed cursors after downgrade and concurrent query contexts stay isolated',async()=>{
 const root=mkdtempSync(path.join(tmpdir(),'membership-query-'));const holder=new DatasetHolder(root);
 try{
  new ReleaseFixture(root).writeRelease('ds_'+'1'.repeat(64),{dataThrough:'2026-11-02',changes:[{id:'recent',observationDate:'2026-11-01'},{id:'old',observationDate:'2026-10-01'}]});await holder.reloadAsync();
  const raw=new URLSearchParams({from:'2026-10-01',to:'2026-11-03',limit:'1'});
  const [plus,free]=await Promise.all([membershipContext.run({tier:'plus'},()=>runListQueryAsync(holder,'changes',raw)),membershipContext.run({tier:'free'},()=>runListQueryAsync(holder,'changes',raw))]);
  assert.equal(plus.result?.page.items.length,1);assert.equal(free.problem?.status,403);
  const cursor=plus.result!.page.nextCursor!;assert.ok(cursor);
  const downgraded=await membershipContext.run({tier:'free'},()=>runListQueryAsync(holder,'changes',new URLSearchParams({cursor})));
  assert.equal(downgraded.problem?.status,403);
  assert.equal(membershipContext.run({tier:'visitor'},()=>getItem(holder.current!,'old')),null);
  assert.equal(membershipContext.run({tier:'plus'},()=>getItem(holder.current!,'old'))?.id,'old');
  assert.equal(historyCutoff('2026-11-02','visitor'),'2026-10-27');assert.equal(historyCutoff('2026-11-02','free'),'2026-10-04');
 }finally{holder.close();rmSync(root,{recursive:true,force:true});}
});
test('Account credential management requires session and same origin; Free cannot persist more than 3 quotes',async()=>{
 const s=setup(),holder={} as DatasetHolder;const handler=createAccountHandler(s.store,null,holder,{origin:'http://localhost',secure:false},s.m);
 const server=http.createServer((q,r)=>void handler(q,r));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${(server.address() as any).port}/api/account/`;
 try{
  assert.equal((await fetch(base+'membership')).status,401);
  const headers={'content-type':'application/json',origin:'http://localhost',cookie:`maas_session=${s.user.session}`};
  const created=await fetch(base+'tokens',{method:'POST',headers,body:JSON.stringify({name:'test'})});assert.equal(created.status,201);
  assert.equal((await fetch(base+'tokens',{method:'POST',headers:{...headers,origin:'https://evil.example'},body:'{}'})).status,403);
  const workspace={provider:'openai',query:'',sort:'name',modelId:null,familyId:null,selected:['a','b','c','d'],variants:[],component:'total',input:1,output:1,fx:null};
  assert.equal((await fetch(base+'state',{method:'POST',headers,body:JSON.stringify({key:'priceWorkspace',value:workspace})})).status,403);
 }finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));s.store.close();}
});
test('Free waits for Monday, Plus still sends daily; queued Free job cannot block a Plus job',async()=>{
 const s=setup();try{
  const b=s.store.verify('b@example.com',s.store.issueCode('b@example.com'));
  s.pro.grant(b.user.id,s.store.now()-1,s.store.now()+30*86400000,'test','daily');
  for(const id of [s.user.user.id,b.user.id]){s.store.watch(id,'openai:m0',catalog);s.store.preferences(id,true);}
  s.setTime(Date.parse('2026-11-03T01:15:00Z'));
  const change={id:'c',modelId:'openai:m0',revision:1,status:'active',observationDate:'2026-11-03',updatedAt:'2026-11-03T00:00:00Z',title:'Changed',summary:null,links:{permalink:'/item/c/'}} as ChangeEntity;
  const mails:any[]=[];const mailer={send:async(mail:any)=>{mails.push(mail);}};
  const result=await deliverDigests(s.store,mailer,[change],'https://daily.maas.click');assert.equal(result.sent,1);assert.equal(mails[0].to,'b@example.com');
  s.setTime(Date.parse('2026-11-09T01:15:00Z'));assert.equal((await deliverDigests(s.store,mailer,[change],'https://daily.maas.click')).sent,1);assert.equal(mails[1].to,'a@example.com');
 }finally{s.store.close();}
});

test('existing excess watches get one 14-day transition; restart cannot reset it, configuration survives and reducing restores service',()=>{
 const s=setup();try{
  s.store.watchLimit=()=>50;
  for(const model of catalog.models)s.store.watch(s.user.user.id,model.modelId,catalog);
  const policy=new Membership(s.store,s.pro,false),id=s.user.user.id;
  const end=policy.transition(id)!.ends;assert.equal(s.store.effectiveWatches(id).length,5);
  s.setTime(end+1);const restarted=new Membership(s.store,s.pro,false);assert.equal(restarted.transition(id)!.ends,end);assert.equal(s.store.effectiveWatches(id).length,0);assert.equal(s.store.watches(id).length,5);
  s.store.unwatch(id,'openai:m3');s.store.unwatch(id,'openai:m4');assert.equal(s.store.effectiveWatches(id).length,3);assert.equal(restarted.transition(id),null);
 }finally{s.store.close();}
});
