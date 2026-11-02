import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {AccountStore} from '../account-store.js';
import {ProStore} from '../pro-store.js';
import {ProjectStore} from '../project-store.js';
import {DatasetHolder} from '../dataset.js';
import {ReleaseFixture} from './fixture.js';
import {projectQuotes} from '../project-cost.js';
const now=Date.parse('2026-11-02T02:00:00Z');
function setup(){
 const root=mkdtempSync(path.join(tmpdir(),'projects-')),fx=new ReleaseFixture(root),holder=new DatasetHolder(root);
 const prices=[{factKey:'ai',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'input',amount:'2'},{factKey:'ao',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'output',amount:'8'},{factKey:'bi',providerId:'openai',modelKey:'b',modelId:'openai:b',component:'input',amount:'1'},{factKey:'bo',providerId:'openai',modelKey:'b',modelId:'openai:b',component:'output',amount:'2'}];
 const publish=(n:number,alter:(rows:typeof prices)=>void=()=>{})=>{const rows=structuredClone(prices);alter(rows);fx.writeRelease('ds_'+String(n).repeat(64),{dataThrough:'2026-11-02',changes:[{id:'today',observationDate:'2026-11-02'}],prices:rows,modelIdentities:{models:[{modelId:'openai:a',modelName:'A'},{modelId:'openai:b',modelName:'B'}],families:[]}});assert.equal(holder.reload(),true);return holder.current!;};
 publish(1);let clock=now;const accounts=new AccountStore(':memory:',()=>clock,'projects-test-secret-over-32-characters');const owner=accounts.verify('a@example.com',accounts.issueCode('a@example.com')).user,other=accounts.verify('b@example.com',accounts.issueCode('b@example.com')).user,pro=new ProStore(accounts);pro.grant(owner.id,now-1,now+86400000,'test','test');const store=new ProjectStore(accounts,pro);
 const input=()=>{const q=projectQuotes(holder.current!,clock)[0]!;return {name:'客服助手',usageNote:'10月估算',currency:'CNY' as const,fx:'1',lines:[{label:'主对话',inputPriceId:q.inputPriceId,outputPriceId:q.outputPriceId,inputMillions:'100',outputMillions:'20'}]};};
 const save=(project=input(),key='initial_request_123456')=>store.save(owner.id,null,{project,requestKey:key,datasetVersion:holder.current!.version},holder.current!);
 return {root,fx,holder,accounts,owner,other,pro,store,publish,input,save,setTime:(time:number)=>clock=time,close:()=>{holder.close();accounts.close();rmSync(root,{recursive:true,force:true});}};
}
test('fixed per-line monthly usage, currencies and frozen baselines produce explainable costs',()=>{
 const s=setup();try{
  const p=s.input();p.currency='USD' as any;const created=s.save(p);assert.equal(created.baseline.cost,'360.000000000000');assert.equal(created.latest.baselineDelta,'0.000000000000');
  const ds=s.publish(2,rows=>rows[0]!.amount='1.5');assert.equal(s.store.refresh(created.id,ds),true);const next=s.store.detail(s.owner.id,created.id);assert.equal(next.latest.cost,'310.000000000000');assert.equal(next.latest.baselineDelta,'-50.000000000000');assert.equal(next.latest.previousDelta,'-50.000000000000');assert.equal(next.baseline.cost,'360.000000000000');
  assert.equal(s.store.refresh(created.id,ds),false);assert.equal(s.store.detail(s.owner.id,created.id).events.length,1);
  const updated=s.store.save(s.owner.id,created.id,{project:{...p,lines:p.lines.map(l=>({...l,inputMillions:'200'}))},requestKey:'update_request_123456',revision:1,datasetVersion:ds.version},ds);
  assert.equal(updated.revision,2);assert.equal(updated.baselines.length,2);assert.equal(updated.latest.baselineDelta,'0.000000000000');assert.equal(updated.baselines[1]!.reason,'user_created');
 }finally{s.close();}
});
test('projects sum actual independently entered usage, not repeated comparison workload; FX is frozen',()=>{
 const s=setup();try{
  const q=projectQuotes(s.holder.current!,now),p=s.input();p.fx='7';p.lines.push({...p.lines[0]!,label:'分类器',inputPriceId:q[1]!.inputPriceId,outputPriceId:q[1]!.outputPriceId,inputMillions:'10',outputMillions:'1'});
  assert.equal(s.save(p).baseline.cost,'2604.000000000000');
 }finally{s.close();}
});
test('ownership, Plus entitlement, five projects, ten lines, idempotency and concurrent baseline edits are enforced server-side',()=>{
 const s=setup();try{
  const a=s.save();assert.equal(s.save().id,a.id);assert.throws(()=>s.save({...s.input(),name:'changed'}),/标识/);
  assert.throws(()=>s.store.detail(s.other.id,a.id),/不存在/);assert.throws(()=>s.store.save(s.other.id,null,{project:s.input(),datasetVersion:s.holder.current!.version,requestKey:'free_request_123456'},s.holder.current!),/Plus/);
  assert.throws(()=>s.save({...s.input(),lines:Array(11).fill(s.input().lines[0])},'eleven_request_123456'),/10/);
  assert.throws(()=>s.store.save(s.owner.id,a.id,{project:s.input(),datasetVersion:s.holder.current!.version,requestKey:'stale_request_123456',revision:0},s.holder.current!),/其他页面/);
  for(let n=0;n<4;n++)s.save({...s.input(),name:String(n)},'other_request_12345'+n);assert.throws(()=>s.save(s.input(),'sixth_request_123456'),/5/);
  s.store.action(s.owner.id,a.id,{action:'archive',revision:1},s.holder.current!);s.save(s.input(),'after_archive_123456');assert.throws(()=>s.store.action(s.owner.id,a.id,{action:'resume',revision:1},s.holder.current!),/5/);
 }finally{s.close();}
});
test('missing or stale quotes show partial coverage without a fabricated total or price-drop notification',()=>{
 const s=setup();try{
  const q=projectQuotes(s.holder.current!,now),p=s.input();p.lines.push({...p.lines[0]!,inputPriceId:q[1]!.inputPriceId,outputPriceId:q[1]!.outputPriceId,inputMillions:'10',outputMillions:'1'});const a=s.save(p);
  const ds=s.publish(2,rows=>rows.splice(0,1));s.store.refresh(a.id,ds);const d=s.store.detail(s.owner.id,a.id);assert.equal(d.latest.complete,false);assert.equal(d.latest.baselineDelta,null);assert.equal(d.latest.lines[0]!.state,'unmatched');assert.equal(d.events[0]!.kind,'quote_attention');
  const fresh=s.publish(3);s.store.refresh(a.id,fresh);assert.equal(s.store.detail(s.owner.id,a.id).events[0]!.kind,'quote_recovered');
  s.setTime(now+73*3600000);s.pro.grant(s.owner.id,now-1,now+100*3600000,'test','extend');s.store.refresh(a.id,fresh);assert.equal(s.store.detail(s.owner.id,a.id).latest.complete,false);
 }finally{s.close();}
});
test('pause and expired Plus preserve data, do not recompute; resume reports cumulative difference once',()=>{
 const s=setup();try{
  const a=s.save();s.store.action(s.owner.id,a.id,{action:'pause',revision:1},s.holder.current!);const ds=s.publish(2,rows=>rows[0]!.amount='1');assert.equal(s.store.refresh(a.id,ds),false);
  s.store.action(s.owner.id,a.id,{action:'resume',revision:1},ds);assert.equal(s.store.detail(s.owner.id,a.id).events.length,1);
  s.setTime(now+86400001);const ds3=s.publish(3,rows=>rows[0]!.amount='0.5');assert.equal(s.store.refresh(a.id,ds3),false);const saved=s.store.detail(s.owner.id,a.id);assert.equal(saved.serviceActive,false);assert.equal(saved.baselines.length,1);
 }finally{s.close();}
});

test('daily project email is opt-in, coalesced with watched changes, skips repeated states and respects expiry/opt-out',async()=>{
 const {ProjectDelivery}=await import('../project-mail.js'),{deliverDigests}=await import('../account-digest.js');const s=setup();
 try{
  const delivery=new ProjectDelivery(s.store),p=s.input();p.currency='USD' as any;const a=s.save(p),id=s.owner.id;const sent:any[]=[];const mailer={send:async(m:any)=>{sent.push(m);}};
  s.setTime(now+1);s.store.action(id,a.id,{action:'email',enabled:true,revision:1},s.holder.current!);
  s.accounts.watch(id,'openai:b',s.holder.current!.modelIdentities);s.accounts.preferences(id,true);
  s.setTime(now+2);const ds=s.publish(2,rows=>rows[0]!.amount='1.5');s.store.refreshAll(ds);
  const changes=[{id:'other',modelId:'openai:b',revision:1,status:'active',recordType:'source_observation',title:'OTHER_MODEL_UPDATE',updatedAt:new Date(now+2).toISOString(),links:{permalink:'/item/other/'}}] as any[];
  assert.equal((await deliverDigests(s.accounts,mailer,changes,'https://daily.maas.click',true,delivery)).sent,1);assert.equal(sent.length,1);assert.ok(sent[0].text.includes('客服助手'));assert.ok(sent[0].text.includes('OTHER_MODEL_UPDATE'));assert.ok(sent[0].text.includes('2 → 1.5'));assert.ok(!sent[0].text.includes('100000000'));assert.ok(sent[0].text.includes('/projects/?id='));
  assert.equal((await deliverDigests(s.accounts,mailer,changes,'https://daily.maas.click',true,delivery)).sent,0);
  s.setTime(now+3);s.store.refreshAll(s.publish(3,rows=>rows[0]!.amount='1'));assert.equal(delivery.enqueue(),0,'one project batch per Shanghai day');
  s.setTime(now+86400000);s.pro.grant(id,now-1,now+3*86400000,'test','extend');assert.equal((await deliverDigests(s.accounts,mailer,changes,'https://daily.maas.click',true,delivery)).sent,1);
  s.setTime(now+86400001);s.store.action(id,a.id,{action:'email',enabled:false,revision:1},s.holder.current!);s.store.refreshAll(s.publish(4,rows=>rows[0]!.amount='0.5'));s.setTime(now+2*86400000);assert.equal(delivery.enqueue(),0);
 }finally{s.close();}
});
test('project-only recipients get daily mail without enabling model watch; paused and expired projects cannot receive queued mail',async()=>{
 const {ProjectDelivery}=await import('../project-mail.js'),{deliverDigests}=await import('../account-digest.js');const s=setup();try{
  const delivery=new ProjectDelivery(s.store),a=s.save(),id=s.owner.id;s.setTime(now+1);s.store.action(id,a.id,{action:'email',enabled:true,revision:1},s.holder.current!);s.setTime(now+2);s.store.refreshAll(s.publish(2,rows=>rows[0]!.amount='1'));
  assert.equal(s.accounts.db.prepare('SELECT emailEnabled FROM users WHERE id=?').get(id)!.emailEnabled,0);assert.equal(delivery.enqueue(),1);
  s.store.action(id,a.id,{action:'pause',revision:1},s.holder.current!);const sent:any[]=[];assert.equal((await deliverDigests(s.accounts,{send:async(m:any)=>{sent.push(m);}},[],'https://daily.maas.click',false,delivery)).sent,0);assert.equal(sent.length,0);
  s.store.action(id,a.id,{action:'resume',revision:1},s.holder.current!);s.setTime(now+86400001);assert.equal((await deliverDigests(s.accounts,{send:async(m:any)=>{sent.push(m);}},[],'https://daily.maas.click',false,delivery)).sent,0);
 }finally{s.close();}
});

test('enabling project mail excludes older events even when enable and change share the same millisecond',async()=>{
 const {ProjectDelivery}=await import('../project-mail.js');const s=setup();try{
  const delivery=new ProjectDelivery(s.store),a=s.save();s.setTime(now+1);s.store.refreshAll(s.publish(2,rows=>rows[0]!.amount='1.8'));
  s.store.action(s.owner.id,a.id,{action:'email',enabled:true,revision:1},s.holder.current!);assert.equal(delivery.enqueue(),0);
  s.store.refreshAll(s.publish(3,rows=>rows[0]!.amount='1.5'));assert.equal(delivery.enqueue(),1);const job=s.accounts.db.prepare('SELECT jobId FROM cost_mail_batches').get();assert.equal(delivery.events(String(job!.jobId)).length,1);
 }finally{s.close();}
});

test('ordinary reminder opt-out retains separately enabled project mail; global unsubscribe atomically disables both',async()=>{
 const {ProjectDelivery}=await import('../project-mail.js');const s=setup();try{
  const delivery=new ProjectDelivery(s.store),a=s.save(),id=s.owner.id;s.setTime(now+1);s.accounts.preferences(id,true);s.store.action(id,a.id,{action:'email',enabled:true,revision:1},s.holder.current!);s.setTime(now+2);s.store.refreshAll(s.publish(2,rows=>rows[0]!.amount='1.5'));assert.equal(delivery.enqueue(),1);
  const job=String(s.accounts.db.prepare('SELECT jobId FROM cost_mail_batches').get()!.jobId);s.accounts.preferences(id,false);assert.equal(s.accounts.db.prepare('SELECT status FROM mail_jobs WHERE id=?').get(job)!.status,'pending');assert.equal(delivery.events(job).length,1);
  assert.equal(s.accounts.unsubscribe(s.owner.unsubscribeToken),true);assert.equal(delivery.events(job).length,0);assert.equal(s.accounts.db.prepare('SELECT status FROM mail_jobs WHERE id=?').get(job)!.status,'cancelled');assert.equal(s.store.detail(id,a.id).emailEnabled,false);
 }finally{s.close();}
});

test('confirmed rejection retries the exact frozen project set after another project opted out before composition',async()=>{
 const {ProjectDelivery}=await import('../project-mail.js'),{deliverDigests}=await import('../account-digest.js'),{MailSendError}=await import('../mail-ledger.js');const s=setup();try{
  const delivery=new ProjectDelivery(s.store),a=s.save(),b=s.save({...s.input(),name:'EXCLUDED_PROJECT'},'second_project_123456'),id=s.owner.id;s.setTime(now+1);
  for(const p of [a,b])s.store.action(id,p.id,{action:'email',enabled:true,revision:1},s.holder.current!);s.setTime(now+2);s.store.refreshAll(s.publish(2,rows=>rows[0]!.amount='1.5'));delivery.enqueue();s.store.action(id,b.id,{action:'email',enabled:false,revision:1},s.holder.current!);
  const sent:any[]=[];const failed=await deliverDigests(s.accounts,{send:async(m:any)=>{sent.push(m);throw new MailSendError('provider_rejected',true);}},[],'https://daily.maas.click',false,delivery);assert.equal(failed.failed,1);assert.ok(!sent[0].text.includes('EXCLUDED_PROJECT'));
  const job=String(s.accounts.db.prepare('SELECT jobId FROM cost_mail_batches').get()!.jobId);s.accounts.db.prepare("UPDATE mail_jobs SET status='pending',lease=0 WHERE id=?").run(job);
  const retry=await deliverDigests(s.accounts,{send:async(m:any)=>{sent.push(m);}},[],'https://daily.maas.click',false,delivery);assert.equal(retry.sent,1);assert.deepEqual(sent[0],sent[1]);
 }finally{s.close();}
});
