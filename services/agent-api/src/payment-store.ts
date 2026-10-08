import { randomUUID, createHmac, createHash, timingSafeEqual } from 'node:crypto';
import { z } from 'zod';
import { AccountError } from './account-store.js';
import { AdminStore } from './admin-store.js';

const ident=z.string().min(1).max(200).regex(/^[a-zA-Z0-9:_-]+$/);
const minor=z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
export const paymentFactSchema=z.object({id:ident,kind:z.enum(['paid','failed','cancel','terminate','refund','dispute','dispute_won','dispute_lost']),orderId:ident,subscriptionId:ident,objectId:ident,currency:z.string().regex(/^[A-Z]{3}$/),amount:minor,starts:minor,ends:minor,occurredAt:minor}).strict();
export type PaymentFact=z.infer<typeof paymentFactSchema>;
const bad=(message:string)=>new AccountError(400,'invalid_payment',message);
export function migratePayments(admin:AdminStore) {
 admin.accounts.transaction(()=>{
  if(admin.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=8').get())return;
  admin.db.exec(`
 CREATE TABLE paid_simulator_objects(id TEXT PRIMARY KEY,payload TEXT NOT NULL,createdAt INTEGER NOT NULL);
 CREATE TABLE paid_orders(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),subscriptionId TEXT NOT NULL,provider TEXT NOT NULL,currency TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),createdAt INTEGER NOT NULL,UNIQUE(provider,id));
 CREATE INDEX paid_orders_user ON paid_orders(userId,createdAt,id);
 CREATE TABLE paid_subscriptions(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),provider TEXT NOT NULL,providerId TEXT UNIQUE,createdAt INTEGER NOT NULL);
 CREATE TABLE paid_attempts(id TEXT PRIMARY KEY,orderId TEXT NOT NULL REFERENCES paid_orders(id),providerObjectId TEXT NOT NULL,state TEXT NOT NULL,createdAt INTEGER NOT NULL);
 CREATE TABLE paid_events(id TEXT PRIMARY KEY,provider TEXT NOT NULL,providerEventId TEXT NOT NULL,payloadHash TEXT NOT NULL,payload TEXT NOT NULL,receivedAt INTEGER NOT NULL,UNIQUE(provider,providerEventId));
 CREATE TABLE paid_event_results(id TEXT PRIMARY KEY,eventId TEXT NOT NULL REFERENCES paid_events(id),state TEXT NOT NULL,error TEXT,createdAt INTEGER NOT NULL);
 CREATE TABLE paid_facts(id TEXT PRIMARY KEY,eventId TEXT NOT NULL REFERENCES paid_events(id),kind TEXT NOT NULL,orderId TEXT NOT NULL REFERENCES paid_orders(id),subscriptionId TEXT NOT NULL REFERENCES paid_subscriptions(id),objectId TEXT NOT NULL,currency TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>=0),starts INTEGER NOT NULL,ends INTEGER NOT NULL,occurredAt INTEGER NOT NULL,UNIQUE(kind,objectId));
 CREATE UNIQUE INDEX paid_one_success_per_order ON paid_facts(orderId) WHERE kind='paid';
 CREATE INDEX paid_facts_subscription ON paid_facts(subscriptionId,occurredAt,id);
 CREATE TABLE paid_refunds(id TEXT PRIMARY KEY,orderId TEXT NOT NULL REFERENCES paid_orders(id),amount INTEGER NOT NULL CHECK(amount>0),currency TEXT NOT NULL,providerId TEXT UNIQUE,createdAt INTEGER NOT NULL,requestKey TEXT NOT NULL UNIQUE);
 CREATE TABLE paid_refund_results(id TEXT PRIMARY KEY,refundId TEXT NOT NULL REFERENCES paid_refunds(id),state TEXT NOT NULL,source TEXT NOT NULL,createdAt INTEGER NOT NULL);
 CREATE TABLE paid_reconciliations(id TEXT PRIMARY KEY,currency TEXT NOT NULL,starts INTEGER NOT NULL,ends INTEGER NOT NULL,source TEXT NOT NULL,createdAt INTEGER NOT NULL);
 CREATE TABLE paid_provider_records(id TEXT PRIMARY KEY,reconciliationId TEXT NOT NULL REFERENCES paid_reconciliations(id),kind TEXT NOT NULL,objectId TEXT NOT NULL,amount INTEGER NOT NULL,currency TEXT NOT NULL,occurredAt INTEGER NOT NULL,source TEXT NOT NULL);
 CREATE TABLE paid_differences(id TEXT PRIMARY KEY,reconciliationId TEXT NOT NULL REFERENCES paid_reconciliations(id),objectId TEXT NOT NULL,kind TEXT NOT NULL,expected INTEGER,observed INTEGER,source TEXT NOT NULL);
 CREATE TABLE paid_difference_actions(id TEXT PRIMARY KEY,differenceId TEXT NOT NULL REFERENCES paid_differences(id),actorId TEXT NOT NULL,note TEXT NOT NULL,createdAt INTEGER NOT NULL);
 `);
 for(const table of ['paid_orders','paid_subscriptions','paid_attempts','paid_simulator_objects','paid_events','paid_facts','paid_event_results','paid_refunds','paid_refund_results','paid_reconciliations','paid_provider_records','paid_differences','paid_difference_actions']){admin.db.exec(`CREATE TRIGGER ${table}_immutable_update BEFORE UPDATE ON ${table} BEGIN SELECT RAISE(ABORT,'immutable payment record'); END;CREATE TRIGGER ${table}_immutable_delete BEFORE DELETE ON ${table} BEGIN SELECT RAISE(ABORT,'immutable payment record'); END;`);}
 admin.db.prepare('INSERT INTO admin_schema_migrations VALUES(8,?)').run(admin.accounts.now());
 });
}
export function verifyPaymentSignature(raw:Buffer,header:string,secret:string,now:number) {
 const parts=header.split(','),t=parts.find(p=>p.startsWith('t='))?.slice(2), signatures=parts.filter(p=>p.startsWith('v1=')).map(p=>p.slice(3));
 if(!secret||!t||!/^\d+$/.test(t)||Math.abs(now/1000-Number(t))>300)throw bad('回调签名或时间无效');
 const expected=createHmac('sha256',secret).update(t+'.').update(raw).digest();
 if(!signatures.some(s=>/^[a-f0-9]{64}$/.test(s)&&timingSafeEqual(expected,Buffer.from(s,'hex'))))throw bad('回调签名无效');
}
export class PaymentStore {
 readonly db;
 constructor(readonly admin:AdminStore){this.db=admin.db;migratePayments(admin);}
 order(id:string){const r=this.db.prepare('SELECT * FROM paid_orders WHERE id=?').get(id);if(!r)throw new AccountError(404,'not_found','订单不存在');return r;}
 createOrder(userId:string,key:string,currency='USD',amount=990,subscriptionId?:string) {
  ident.parse(key);if(!/^[A-Z]{3}$/.test(currency)||!Number.isSafeInteger(amount)||amount<=0)throw bad('金额或币种无效');
  return this.admin.accounts.transaction(()=>{
   const previous=this.db.prepare('SELECT * FROM paid_orders WHERE id=?').get('order_'+key);
   if(previous){if(previous.userId!==userId||previous.currency!==currency||previous.amount!==amount)throw new AccountError(409,'idempotency_conflict','订单键冲突');return previous;}
   if(!subscriptionId){
    const subscriptions=this.db.prepare('SELECT id FROM paid_subscriptions WHERE userId=?').all(userId);
    if(subscriptions.some(s=>['active','disputed','pending'].includes(String(this.subscription(String(s.id)).state))))throw new AccountError(409,'subscription_exists','已有付费订阅，请先查询当前订阅');
    const open=this.db.prepare("SELECT o.* FROM paid_orders o WHERE userId=? AND NOT EXISTS(SELECT 1 FROM paid_facts f WHERE f.orderId=o.id AND f.kind='paid') AND NOT EXISTS(SELECT 1 FROM paid_facts f WHERE f.subscriptionId=o.subscriptionId AND f.kind IN ('cancel','terminate')) ORDER BY createdAt DESC,id DESC LIMIT 1").get(userId);
    if(open){if(open.currency!==currency||open.amount!==amount)throw bad('未完成订单套餐不匹配');return open;}
   }
   const sub=subscriptionId??'sub_'+randomUUID();
   if(subscriptionId){const s=this.db.prepare('SELECT * FROM paid_subscriptions WHERE id=?').get(sub);if(!s||s.userId!==userId)throw bad('订阅不匹配');if(this.db.prepare("SELECT 1 FROM paid_facts WHERE subscriptionId=? AND kind IN ('cancel','terminate')").get(sub))throw bad('订阅已停止续费');}
   else this.db.prepare('INSERT INTO paid_subscriptions VALUES(?,?,?,NULL,?)').run(sub,userId,'simulator',this.admin.accounts.now());
   this.db.prepare('INSERT INTO paid_orders VALUES(?,?,?,?,?,?,?)').run('order_'+key,userId,sub,'simulator',currency,amount,this.admin.accounts.now());return this.order('order_'+key);
  });
 }
 receive(provider:string,eventId:string,raw:Buffer){
  ident.parse(eventId);if(provider!=='simulator')throw bad('未配置供应商适配');
  if(raw.length>65536)throw bad('回调过大');const payloadHash=createHash('sha256').update(raw).digest('hex');
  return this.admin.accounts.transaction(()=>{const old=this.db.prepare('SELECT * FROM paid_events WHERE provider=? AND providerEventId=?').get(provider,eventId);
   if(old){if(old.payloadHash!==payloadHash)throw new AccountError(409,'event_conflict','供应商事件内容冲突');return String(old.id);}
   const id=randomUUID();this.db.prepare('INSERT INTO paid_events VALUES(?,?,?,?,?,?)').run(id,provider,eventId,payloadHash,raw.toString(),this.admin.accounts.now());return id;});
 }
 // Input comes only from a trusted adapter's server-side lookup, never a browser return.
 process(eventId:string,verified:PaymentFact){
  try{return this.admin.accounts.transaction(()=>this.processInTransaction(eventId,verified));}
  catch(e){this.db.prepare('INSERT INTO paid_event_results VALUES(?,?,?,?,?)').run(randomUUID(),eventId,'failed',e instanceof AccountError?e.code:'invalid_fact',this.admin.accounts.now());throw e;}
 }
 processInTransaction(eventId:string,verified:PaymentFact){
  const fact=paymentFactSchema.parse(verified);
   const event=this.db.prepare('SELECT * FROM paid_events WHERE id=?').get(eventId);if(!event)throw bad('事件不存在');
   const payload=JSON.parse(String(event.payload));if((payload.kind?payload.id:payload.objectId)!==fact.id)throw bad('供应商核查对象与接收事件不匹配');
   const o=this.order(fact.orderId),subscription=this.db.prepare('SELECT * FROM paid_subscriptions WHERE id=?').get(fact.subscriptionId);if(!subscription||subscription.userId!==o.userId||subscription.provider!==o.provider||event.provider!==o.provider)throw bad('订单用户或供应商不匹配');if(o.subscriptionId!==fact.subscriptionId||o.currency!==fact.currency)throw bad('订单关联或币种不匹配');
   if(fact.kind==='paid'&&(fact.amount!==o.amount||fact.starts>=fact.ends))throw bad('付款金额或周期不匹配');
   const old=this.db.prepare('SELECT * FROM paid_facts WHERE kind=? AND objectId=?').get(fact.kind,fact.objectId);
   if(old){for(const k of ['orderId','subscriptionId','currency','amount','starts','ends','occurredAt'] as const)if(old[k]!==fact[k])throw bad('交易事实冲突');}
   else {
    if(fact.kind==='refund'){
     if(fact.amount<=0)throw bad('退款金额必须为正整数');
     const paid=this.db.prepare("SELECT 1 FROM paid_facts WHERE orderId=? AND kind='paid'").get(fact.orderId);if(!paid)throw bad('未核实原付款');
     const sum=Number(this.db.prepare("SELECT coalesce(sum(amount),0) n FROM paid_facts WHERE orderId=? AND kind='refund'").get(fact.orderId)!.n);if(sum+fact.amount>Number(o.amount))throw bad('超过可退余额');
    }
    if(['paid','failed'].includes(fact.kind))this.db.prepare('INSERT INTO paid_attempts VALUES(?,?,?,?,?)').run(fact.id,fact.orderId,fact.objectId,fact.kind==='paid'?'succeeded':'failed',this.admin.accounts.now());
    this.db.prepare('INSERT INTO paid_facts VALUES(?,?,?,?,?,?,?,?,?,?,?)').run(fact.id,eventId,fact.kind,fact.orderId,fact.subscriptionId,fact.objectId,fact.currency,fact.amount,fact.starts,fact.ends,fact.occurredAt);
   }
   if(fact.kind==='refund'){
    const request=this.db.prepare('SELECT * FROM paid_refunds WHERE id=?').get(fact.objectId);
    if(request){if(request.orderId!==fact.orderId||request.amount!==fact.amount||request.currency!==fact.currency)throw bad('退款请求与供应商结果不匹配');
     const final=this.db.prepare('SELECT state FROM paid_refund_results WHERE refundId=? ORDER BY rowid DESC LIMIT 1').get(fact.objectId);
     if(final?.state==='failed')throw bad('退款终态冲突');
     if(final?.state!=='succeeded')this.db.prepare('INSERT INTO paid_refund_results VALUES(?,?,?,?,?)').run(randomUUID(),fact.objectId,'succeeded','simulator_verified_fact',this.admin.accounts.now());
    }
   }
   this.db.prepare('INSERT INTO paid_event_results VALUES(?,?,?,?,?)').run(randomUUID(),eventId,'processed',null,this.admin.accounts.now());return {processed:true};
 }

 refund(orderId:string,amount:number,key:string){return this.admin.accounts.transaction(()=>this.refundInTransaction(orderId,amount,key));}
 refundInTransaction(orderId:string,amount:number,key:string){
   const o=this.order(orderId);if(!Number.isSafeInteger(amount)||amount<=0)throw bad('退款金额无效');ident.parse(key);
   const old=this.db.prepare('SELECT * FROM paid_refunds WHERE requestKey=?').get(key);if(old){if(old.orderId!==orderId||old.amount!==amount)throw new AccountError(409,'idempotency_conflict','退款键冲突');return old;}
   if(!this.db.prepare("SELECT 1 FROM paid_facts WHERE orderId=? AND kind='paid'").get(orderId))throw bad('无成功支付');
   const reserved=Number(this.db.prepare("SELECT coalesce(sum(r.amount),0) n FROM paid_refunds r WHERE r.orderId=? AND coalesce((SELECT state FROM paid_refund_results x WHERE x.refundId=r.id ORDER BY rowid DESC LIMIT 1),'pending')NOT IN ('failed','succeeded')").get(orderId)!.n);
   const completed=Number(this.db.prepare("SELECT coalesce(sum(amount),0) n FROM paid_facts WHERE orderId=? AND kind='refund'").get(orderId)!.n);
   // Pending/unknown requests reserve balance; completed refunds are counted from facts.
   if(reserved+completed+amount>Number(o.amount))throw bad('超过可退余额');
   const id='refund_'+randomUUID();this.db.prepare('INSERT INTO paid_refunds VALUES(?,?,?,?,NULL,?,?)').run(id,orderId,amount,String(o.currency),this.admin.accounts.now(),key);this.db.prepare('INSERT INTO paid_refund_results VALUES(?,?,?,?,?)').run(randomUUID(),id,'pending','internal_request',this.admin.accounts.now());return this.db.prepare('SELECT * FROM paid_refunds WHERE id=?').get(id)!;
 }
 facts(subscriptionId:string){return this.db.prepare("SELECT * FROM paid_facts WHERE subscriptionId=? ORDER BY occurredAt,CASE kind WHEN 'dispute_won' THEN 1 WHEN 'dispute' THEN 2 WHEN 'dispute_lost' THEN 3 ELSE 0 END,id").all(subscriptionId);}
 subscription(id:string):Record<string,unknown>{const s=this.db.prepare('SELECT * FROM paid_subscriptions WHERE id=?').get(id);if(!s)throw new AccountError(404,'not_found','订阅不存在');return {...s,...projectPaidSubscription(this.facts(id),this.admin.accounts.now())};}
 orderProjection(id:string){const o=this.order(id),facts=this.db.prepare('SELECT * FROM paid_facts WHERE orderId=? ORDER BY occurredAt,id').all(id),paid=facts.find(f=>f.kind==='paid'),refunds=checkedMinorTotal(facts.filter(f=>f.kind==='refund').reduce((n,f)=>checkedMinorTotal(n+Number(f.amount)),0)),pending=checkedMinorTotal(Number(this.db.prepare("SELECT coalesce(sum(r.amount),0) n FROM paid_refunds r WHERE r.orderId=? AND coalesce((SELECT state FROM paid_refund_results x WHERE x.refundId=r.id ORDER BY rowid DESC LIMIT 1),'pending') NOT IN ('failed','succeeded')").get(id)!.n));return {...o,state:paid?'succeeded':facts.some(f=>f.kind==='failed')?'failed':'processing',refundedAmount:refunds,reservedRefundAmount:pending,refundableAmount:paid?Math.max(0,Number(o.amount)-refunds-pending):0,refundState:refunds===Number(o.amount)?'full':refunds>0?'partial':'none'};}
 refundProjection(id:string):Record<string,unknown>{const r=this.db.prepare('SELECT * FROM paid_refunds WHERE id=?').get(id);if(!r)throw new AccountError(404,'not_found','退款不存在');return {...r,state:String(this.db.prepare('SELECT state FROM paid_refund_results WHERE refundId=? ORDER BY rowid DESC LIMIT 1').get(id)?.state??'pending')};}
 user(userId:string){return {subscriptions:this.db.prepare('SELECT id FROM paid_subscriptions WHERE userId=? ORDER BY createdAt DESC,id DESC LIMIT 100').all(userId).map(s=>this.subscription(String(s.id))),orders:this.db.prepare('SELECT id FROM paid_orders WHERE userId=? ORDER BY createdAt DESC,id DESC LIMIT 100').all(userId).map(o=>this.orderProjection(String(o.id))),truncated:this.db.prepare('SELECT count(*) n FROM paid_orders WHERE userId=?').get(userId)!.n as number>100};}

}

// Shared by website/API/MCP/RSS/mail through ProStore.entitlement; no frontend payment decisions.
type FactRow=Record<string,unknown>;
export function projectPaidSubscription(facts:FactRow[],now:number){
 const paid=facts.filter(f=>f.kind==='paid'),termination=facts.some(f=>f.kind==='terminate'),cancelAtPeriodEnd=facts.some(f=>f.kind==='cancel');
 const disputes=new Map<string,boolean>();for(const f of facts){if(f.kind==='dispute')disputes.set(String(f.orderId),true);if(f.kind==='dispute_won'||f.kind==='dispute_lost')disputes.set(String(f.orderId),false);}
 const disputed=[...disputes.values()].some(Boolean);
 const usable=paid.filter(f=>{const refunded=facts.filter(r=>r.kind==='refund'&&r.orderId===f.orderId).reduce((n,r)=>checkedMinorTotal(n+Number(r.amount)),0);return refunded<Number(f.amount)&&!facts.some(r=>r.kind==='dispute_lost'&&r.orderId===f.orderId);});
 const current=usable.filter(f=>Number(f.starts)<=now&&Number(f.ends)>now).sort((a,b)=>Number(b.ends)-Number(a.ends))[0];
 const periodEnd=paid.length?Math.max(...paid.map(f=>Number(f.ends))):null;
 const failed=facts.filter(f=>f.kind==='failed').sort((a,b)=>Number(b.occurredAt)-Number(a.occurredAt))[0],lastSuccess=paid.length?Math.max(...paid.map(f=>Number(f.occurredAt))):null,renewalFailed=!!failed&&(lastSuccess===null||Number(failed.occurredAt)>lastSuccess);
 const state=termination?'terminated':disputed?'disputed':current?'active':paid.length&&usable.length===0?'revoked':usable.some(f=>Number(f.starts)>now)?'pending':paid.length?'expired':'incomplete';
 return {state,periodEnd,cancelAtPeriodEnd,renewalFailed,nextRenewalAt:state==='active'&&!cancelAtPeriodEnd&&!renewalFailed?periodEnd:null,entitlement:state==='active'&&current?{source:'paid',status:'active',starts:Number(current.starts),ends:Number(current.ends)}:null};
}
export function paidEntitlement(db:AdminStore['db'],userId:string,now:number) {
 if(!db.prepare("SELECT 1 FROM sqlite_master WHERE name='paid_facts'").get())return undefined;
 let best:{source:string;status:string;starts:number;ends:number}|undefined;
 for(const s of db.prepare('SELECT id FROM paid_subscriptions WHERE userId=?').all(userId)){
  const facts=db.prepare("SELECT * FROM paid_facts WHERE subscriptionId=? ORDER BY occurredAt,CASE kind WHEN 'dispute_won' THEN 1 WHEN 'dispute' THEN 2 WHEN 'dispute_lost' THEN 3 ELSE 0 END,id").all(String(s.id)),e=projectPaidSubscription(facts,now).entitlement;
  if(e&&(!best||e.ends>best.ends))best=e;
 }
 return best;
}

export function paymentMonthEnd(now:number){const start=new Date(now),day=start.getUTCDate(),end=new Date(now);end.setUTCDate(1);end.setUTCMonth(end.getUTCMonth()+1);const last=new Date(Date.UTC(end.getUTCFullYear(),end.getUTCMonth()+1,0)).getUTCDate();end.setUTCDate(Math.min(day,last));return end.getTime();}
export function checkedMinorTotal(n:number){if(!Number.isSafeInteger(n)||n<0)throw new AccountError(503,'amount_overflow','金额汇总超出安全整数范围');return n;}
