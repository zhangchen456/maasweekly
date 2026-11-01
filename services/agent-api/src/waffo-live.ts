import {createHash,randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {WaffoPancake,verifyWebhook} from '@waffo/pancake-ts';
import {AccountError} from './account-store.js';
import {AdminStore} from './admin-store.js';
import {PaymentStore,type PaymentFact} from './payment-store.js';
type Row=Record<string,any>;
export interface WaffoConfig {merchantId:string;storeId:string;productId:string;origin:string;environment:'prod'|'test';amount:number}
export const LIVE_PRODUCT='PROD_4at9FbSOvaC5bLYEVGe0Ln',WAFFO_STORE='STO_5XRDhjxtHscwJdETFLbN1w';
export function configuredWaffoLive(origin:string){
 if(process.env.MAAS_PAYMENT_MODE!=='waffo')return null;
 if(process.env.WAFFO_LIVE_ENVIRONMENT!=='prod')throw Error('production payment environment required');
 const file=process.env.WAFFO_LIVE_PRIVATE_KEY_FILE,expected=process.env.WAFFO_LIVE_KEY_SHA256;
 if(!file||!expected)throw Error('verified production payment key required');
 const privateKey=readFileSync(file,'utf8');if(createHash('sha256').update(privateKey).digest('hex')!==expected)throw Error('payment key binding mismatch');
 const config:WaffoConfig={merchantId:'MER_6hWcf71KacKLDtI1J5ukzY',storeId:WAFFO_STORE,productId:LIVE_PRODUCT,origin,environment:'prod',amount:999};
 const client=new WaffoPancake({merchantId:config.merchantId,privateKey,environment:'prod',fetch:(url,init)=>fetch(url,{...init,redirect:'error',signal:AbortSignal.timeout(15000)})});return {config,client};
}
const invalid=(message:string)=>new AccountError(409,'payment_verification_required',message);
export function usdMinor(v:unknown){if(typeof v!=='string'||!/^\d+(\.\d{1,2})?$/.test(v))throw invalid('供应商金额格式无效');const[a,b='']=v.split('.');const n=Number(a)*100+Number(b.padEnd(2,'0'));if(!Number.isSafeInteger(n))throw invalid('供应商金额超限');return n;}
function stamp(v:unknown){const n=typeof v==='string'?Date.parse(v):NaN;if(!Number.isSafeInteger(n)||n<0)throw invalid('供应商时间无效');return n;}
export function hostedUrl(v:string){const u=new URL(v);if(u.protocol!=='https:'||u.hostname!=='pancake.waffo.ai'||u.username||u.password)throw invalid('支付地址无效');return u;}
const digest=(x:unknown)=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
export const ORDER_FIELDS=`id storeId status testMode currency billingPeriod isInTrial willRenew merchantProvidedBuyerIdentity orderMerchantExternalId currentPeriodStart currentPeriodEnd currentPeriodNumber updatedAt createdAt subscriptionProduct{id} priceSnapshot{currency regularPhase{subtotal taxAmount total} specialPhaseDays} payments{id orderId status testMode periodNumber createdAt amount{amount currency} pspAmountDetails{amount currency} snapshotAmountDetails{currency subtotal taxAmount total discountAmount} refunds{id paymentId status testMode createdAt pspAmountDetails{amount currency}} chargebacks{id status testMode createdAt updatedAt}}`;
export class WaffoLiveStore {
 readonly payments:PaymentStore;readonly db;
 constructor(readonly admin:AdminStore,readonly config:WaffoConfig,readonly client:Pick<WaffoPancake,'graphql'|'checkout'|'orders'|'auth'>,readonly verify=verifyWebhook){
  this.payments=new PaymentStore(admin);this.db=admin.db;
  admin.accounts.transaction(()=>this.db.exec(`
   CREATE TABLE IF NOT EXISTS waffo_checkouts(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),requestKey TEXT NOT NULL,environment TEXT NOT NULL,productId TEXT NOT NULL,created INTEGER NOT NULL,sessionId TEXT,checkoutUrl TEXT,expires INTEGER,providerOrderId TEXT UNIQUE,state TEXT NOT NULL DEFAULT 'pending',checked INTEGER NOT NULL DEFAULT 0,availableAt INTEGER NOT NULL DEFAULT 0,lease INTEGER NOT NULL DEFAULT 0,fence INTEGER NOT NULL DEFAULT 0,error TEXT,UNIQUE(userId,requestKey));
   CREATE INDEX IF NOT EXISTS waffo_checkouts_ready ON waffo_checkouts(availableAt,lease);
   CREATE TABLE IF NOT EXISTS waffo_receipts(id TEXT PRIMARY KEY,environment TEXT NOT NULL,eventType TEXT NOT NULL,orderId TEXT NOT NULL,payloadHash TEXT NOT NULL,payload TEXT NOT NULL,received INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS waffo_observations(id TEXT PRIMARY KEY,checkoutId TEXT NOT NULL REFERENCES waffo_checkouts(id),payload TEXT NOT NULL,observed INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS waffo_periods(orderId TEXT NOT NULL,number INTEGER NOT NULL,starts INTEGER NOT NULL,ends INTEGER NOT NULL,PRIMARY KEY(orderId,number));
   CREATE TABLE IF NOT EXISTS waffo_sync_state(checkoutId TEXT PRIMARY KEY REFERENCES waffo_checkouts(id),status TEXT NOT NULL,willRenew INTEGER NOT NULL,periodEnd INTEGER,updated INTEGER NOT NULL,checked INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS waffo_cancellations(requestId TEXT PRIMARY KEY,subscriptionId TEXT NOT NULL,userId TEXT NOT NULL,created INTEGER NOT NULL);
  `));
  // Provider evidence and accepted financial periods are append-only.
  admin.accounts.transaction(()=>{for(const table of ['waffo_receipts','waffo_observations','waffo_periods','waffo_cancellations']){
   this.db.exec(`CREATE TRIGGER IF NOT EXISTS ${table}_immutable_update BEFORE UPDATE ON ${table} BEGIN SELECT RAISE(ABORT,'immutable payment evidence'); END; CREATE TRIGGER IF NOT EXISTS ${table}_immutable_delete BEFORE DELETE ON ${table} BEGIN SELECT RAISE(ABORT,'immutable payment evidence'); END;`);
  }});
 }
 get now(){return this.admin.accounts.now();}
 async preflight(){
  const r=await this.client.graphql.query<Row>({query:'query($store:String!,$product:String!){store(id:$store){id status prodEnabled payinEnable} subscriptionProduct(id:$product){id storeId status billingPeriod prices{currency priceInfo{amount}}}}',variables:{store:this.config.storeId,product:this.config.productId}});
  const p=r.data?.subscriptionProduct,s=r.data?.store;
  if(r.errors?.length||!p||p.storeId!==this.config.storeId||p.status!=='active'||p.billingPeriod!=='monthly'||!p.prices.some((v:Row)=>v.currency==='USD'&&usdMinor(v.priceInfo.amount)===this.config.amount)||s?.status!=='active'||(this.config.environment==='prod'&&(!s.prodEnabled||!s.payinEnable)))throw new AccountError(503,'payment_not_ready','支付配置尚未通过核验');
  return {amount:this.config.amount,currency:'USD',billingPeriod:'monthly',environment:this.config.environment};
 }
 async checkout(userId:string,key:string,authorize:()=>void=()=>{}){
  if(process.env.MAAS_WAFFO_CHECKOUT_ENABLED==='false')throw new AccountError(503,'checkout_paused','新订阅购买暂时暂停，已有订阅仍可管理');
  if(!/^[a-zA-Z0-9_-]{8,100}$/.test(key))throw invalid('无效的结账请求标识');await this.preflight();authorize();
  const row=this.admin.accounts.transaction(()=>{
   const prior=this.db.prepare('SELECT * FROM waffo_checkouts WHERE userId=? AND requestKey=?').get(userId,key);if(prior)return prior;
   const open=this.db.prepare("SELECT * FROM waffo_checkouts WHERE userId=? AND state NOT IN ('canceled','expired','closed') ORDER BY created DESC LIMIT 1").get(userId);if(open)return open;
   const id='wc_'+randomUUID();this.db.prepare('INSERT INTO waffo_checkouts(id,userId,requestKey,environment,productId,created) VALUES(?,?,?,?,?,?)').run(id,userId,key,this.config.environment,this.config.productId,this.now);return this.db.prepare('SELECT * FROM waffo_checkouts WHERE id=?').get(id)!;
  });
  if(row.environment!==this.config.environment||row.productId!==this.config.productId)throw invalid('已有请求需人工核查');
  if(row.state!=='pending')throw new AccountError(409,'subscription_exists','请先查看现有订阅，避免重复购买');
  if(this.now-Number(row.created)>23*3600000)throw invalid('旧结账结果待核查，请联系支持');
  let url=String(row.checkoutUrl??'');
  if(!row.sessionId){
   const s=await this.client.checkout.createSession({productId:this.config.productId,currency:'USD',orderMerchantExternalId:String(row.id),withTrial:false,allowPromotionCodes:false,successUrl:this.config.origin+'/subscription/payments/?checkout='+row.id,expiresInSeconds:3600},{idempotencyKey:'maas_checkout_'+row.id});
   const target=hostedUrl(s.checkoutUrl);target.hash='';url=target.href;this.db.prepare('UPDATE waffo_checkouts SET sessionId=?,checkoutUrl=?,expires=? WHERE id=?').run(s.sessionId,url,stamp(s.expiresAt),String(row.id));
  }else if(Number(row.expires)<=this.now)throw new AccountError(409,'checkout_expired','结账已过期，请刷新记录后重试');
  const token=await this.client.auth.issueSessionToken({storeId:this.config.storeId,buyerIdentity:userId});authorize();const target=hostedUrl(url);target.hash='token='+token.token;return {mode:'waffo',orderId:row.id,url:target.href};
 }
 receive(raw:string,signature:string){
  let e;try{e=this.verify(raw,signature,{environment:this.config.environment});}catch{throw new AccountError(401,'payment_signature_invalid','支付通知签名无效');}
  if(e.mode!==this.config.environment||e.storeId!==this.config.storeId||!e.id||e.id.length>200||!e.data?.orderId||!Number.isFinite(Date.parse(e.timestamp)))throw invalid('支付通知环境或店铺不匹配');
  const hash=createHash('sha256').update(raw).digest('hex');return this.admin.accounts.transaction(()=>{
   const old=this.db.prepare('SELECT payloadHash FROM waffo_receipts WHERE id=?').get(e.id);if(old){if(old.payloadHash!==hash)throw invalid('支付通知内容冲突');return {received:true,duplicate:true};}
   this.db.prepare('INSERT INTO waffo_receipts VALUES(?,?,?,?,?,?,?)').run(e.id,e.mode,e.eventType,String(e.data.orderId),hash,raw,this.now);
   this.db.prepare('UPDATE waffo_checkouts SET availableAt=0 WHERE providerOrderId=? OR id=?').run(String(e.data.orderId),String(e.data.orderMerchantExternalId??''));return {received:true};
  });
 }
 async lookup(row:Row){const r=await this.client.graphql.query<Row>({query:`query($store:String!,$ref:String!){subscriptionOrders(storeId:$store,filter:{orderMerchantExternalId:{eq:$ref}},limit:2){${ORDER_FIELDS}}}`,variables:{store:this.config.storeId,ref:row.id}});if(r.errors?.length||!Array.isArray(r.data?.subscriptionOrders))throw invalid('支付查询暂不可用');if(r.data.subscriptionOrders.length>1)throw invalid('同一结账出现多个订单，请人工核查');return r.data.subscriptionOrders[0] as Row|undefined;}
 apply(row:Row,o:Row){
  const isTest=this.config.environment==='test';
  if(o.testMode!==isTest||o.storeId!==this.config.storeId||o.orderMerchantExternalId!==row.id||o.merchantProvidedBuyerIdentity!==row.userId||o.subscriptionProduct?.id!==this.config.productId||o.currency!=='USD'||o.billingPeriod!=='monthly'||o.isInTrial||o.priceSnapshot?.currency!=='USD'||usdMinor(o.priceSnapshot.regularPhase.subtotal)!==this.config.amount||o.priceSnapshot.specialPhaseDays)throw invalid('订单用户、套餐或环境核验失败');
  if(row.providerOrderId&&row.providerOrderId!==o.id)throw invalid('订单绑定冲突');const updated=stamp(o.updatedAt),previous=this.db.prepare('SELECT updated FROM waffo_sync_state WHERE checkoutId=?').get(row.id);if(previous&&Number(previous.updated)>updated)return;
  const sub='ws_'+String(row.id),now=this.now;this.db.prepare('INSERT OR IGNORE INTO paid_subscriptions VALUES(?,?,?,?,?)').run(sub,row.userId,'waffo',o.id,stamp(o.createdAt));
  if(o.currentPeriodNumber&&o.currentPeriodStart&&o.currentPeriodEnd){const starts=stamp(o.currentPeriodStart),ends=stamp(o.currentPeriodEnd);if(starts>=ends)throw invalid('订阅周期无效');const old=this.db.prepare('SELECT starts,ends FROM waffo_periods WHERE orderId=? AND number=?').get(o.id,o.currentPeriodNumber);if(old&&(old.starts!==starts||old.ends!==ends))throw invalid('订阅周期发生冲突');this.db.prepare('INSERT OR IGNORE INTO waffo_periods VALUES(?,?,?,?)').run(o.id,o.currentPeriodNumber,starts,ends);}
  let review=false;
  for(const p of o.payments){
   if(p.testMode!==isTest||p.orderId!==o.id)throw invalid('付款环境或订单不符');if(!['succeeded','failed'].includes(p.status))continue;
   const a=p.snapshotAmountDetails,actual=p.pspAmountDetails;
   if(actual?.currency!=='USD'||a?.currency!=='USD'||usdMinor(a.subtotal)!==this.config.amount||usdMinor(a.discountAmount??'0')!==0||usdMinor(actual.amount)!==usdMinor(a.total)||usdMinor(a.total)!==this.config.amount+usdMinor(a.taxAmount))throw invalid('实际收款金额或计费条件不符');
   const amount=usdMinor(actual.amount),order='wp_'+p.id;let period=this.db.prepare('SELECT starts,ends FROM waffo_periods WHERE orderId=? AND number=?').get(o.id,p.periodNumber??-1);
   if(!period&&p.periodNumber==null&&o.currentPeriodStart&&o.currentPeriodEnd&&stamp(p.createdAt)>=stamp(o.currentPeriodStart)&&stamp(p.createdAt)<stamp(o.currentPeriodEnd))period={starts:stamp(o.currentPeriodStart),ends:stamp(o.currentPeriodEnd)};
   if(p.status==='failed'){
    this.db.prepare('INSERT OR IGNORE INTO paid_orders VALUES(?,?,?,?,?,?,?)').run(order,row.userId,sub,'waffo','USD',amount,stamp(p.createdAt));
    this.fact({id:'wfail_'+p.id,kind:'failed',orderId:order,subscriptionId:sub,objectId:p.id,currency:'USD',amount,starts:0,ends:0,occurredAt:stamp(p.createdAt)});continue;
   }
   if(!period){review=true;continue;}
   this.db.prepare('INSERT OR IGNORE INTO paid_orders VALUES(?,?,?,?,?,?,?)').run(order,row.userId,sub,'waffo','USD',amount,stamp(p.createdAt));
   this.fact({id:'wf_'+p.id,kind:'paid',orderId:order,subscriptionId:sub,objectId:p.id,currency:'USD',amount,starts:Number(period.starts),ends:Number(period.ends),occurredAt:stamp(p.createdAt)});
   for(const r of p.refunds){if(r.status!=='succeeded')continue;if(r.testMode!==isTest||r.paymentId!==p.id||r.pspAmountDetails?.currency!=='USD')throw invalid('退款关联核验失败');this.fact({id:'wf_'+r.id,kind:'refund',orderId:order,subscriptionId:sub,objectId:r.id,currency:'USD',amount:usdMinor(r.pspAmountDetails.amount),starts:Number(period.starts),ends:Number(period.ends),occurredAt:stamp(r.createdAt)});}
   for(const d of p.chargebacks){if(d.testMode!==isTest)throw invalid('争议环境不符');const kind=d.status==='won'?'dispute_won':d.status==='lost'?'dispute_lost':'dispute';this.fact({id:'wf_'+digest([d.id,d.status,d.updatedAt]),kind,orderId:order,subscriptionId:sub,objectId:d.id+'_'+stamp(d.updatedAt),currency:'USD',amount,starts:Number(period.starts),ends:Number(period.ends),occurredAt:stamp(d.updatedAt)});}
  }
  const paid=this.db.prepare("SELECT * FROM paid_facts WHERE subscriptionId=? AND kind='paid' ORDER BY ends DESC LIMIT 1").get(sub);
  if(paid&&['active','canceling','canceled','past_due','expired','closed'].includes(o.status)){const kind=['canceled','expired','closed'].includes(o.status)?'terminate':o.willRenew?'resume':'cancel',factId='wf_'+digest([o.id,kind,o.updatedAt]);if(!this.db.prepare('SELECT 1 FROM paid_facts WHERE id=?').get(factId))this.fact({id:factId,kind,orderId:String(paid.orderId),subscriptionId:sub,objectId:o.id+'_'+kind+'_'+updated,currency:'USD',amount:0,starts:Number(paid.starts),ends:Number(paid.ends),occurredAt:updated});}
  this.db.prepare('INSERT OR IGNORE INTO waffo_observations VALUES(?,?,?,?)').run(digest(o),row.id,JSON.stringify(o),now);
  this.db.prepare('INSERT INTO waffo_sync_state VALUES(?,?,?,?,?,?) ON CONFLICT(checkoutId) DO UPDATE SET status=excluded.status,willRenew=excluded.willRenew,periodEnd=excluded.periodEnd,updated=excluded.updated,checked=excluded.checked').run(row.id,o.status,Number(o.willRenew),o.currentPeriodEnd?stamp(o.currentPeriodEnd):null,updated,now);
  this.db.prepare('UPDATE waffo_checkouts SET providerOrderId=?,state=?,checked=?,error=? WHERE id=?').run(o.id,o.status,now,review?'historical_period_requires_review':null,row.id);
 }
 fact(f:PaymentFact){const old=this.db.prepare('SELECT * FROM paid_facts WHERE kind=? AND objectId=?').get(f.kind,f.objectId);if(old){for(const k of ['orderId','subscriptionId','currency','amount','starts','ends','occurredAt'] as const)if(old[k]!==f[k])throw invalid('交易事实冲突');return;}const id=this.payments.receiveInTransaction('waffo',f.id,Buffer.from(JSON.stringify({objectId:f.id})));this.payments.processInTransaction(id,f);}
 async sync(id?:string):Promise<{claimed:boolean;stale?:boolean;verified?:boolean;error?:string}>{
  const row:Row|null=this.admin.accounts.transaction(()=>{const r=this.db.prepare(`SELECT * FROM waffo_checkouts WHERE environment=? AND lease<=? ${id?'AND id=?':'AND availableAt<=?'} ORDER BY availableAt,created LIMIT 1`).get(this.config.environment,this.now,id??this.now);if(!r)return null;this.db.prepare('UPDATE waffo_checkouts SET lease=?,fence=fence+1 WHERE id=?').run(this.now+45000,String(r.id));return {...r,fence:Number(r.fence)+1};});if(!row)return {claimed:false};
  try{const o=await this.lookup(row);return this.admin.accounts.transaction(()=>{const current=this.db.prepare('SELECT * FROM waffo_checkouts WHERE id=?').get(row.id);if(!current||current.fence!==row.fence||Number(current.lease)<=this.now)return {claimed:true,stale:true};if(o)this.apply(current,o);else{if(current.providerOrderId)throw invalid('已有订单暂时查不到');this.db.prepare('UPDATE waffo_checkouts SET checked=?,error=NULL,state=? WHERE id=?').run(this.now,Number(current.expires)>0&&this.now>Number(current.expires)+300000?'expired':'pending',row.id);}this.db.prepare('UPDATE waffo_checkouts SET lease=0,availableAt=? WHERE id=?').run(this.now+(['canceled','expired','closed'].includes(o?.status)?3600000:!o&&Number(current.expires)>0&&this.now>Number(current.expires)+300000?86400000:60000),row.id);return {claimed:true,verified:!!o};});}
  catch(e){this.db.prepare('UPDATE waffo_checkouts SET lease=0,availableAt=?,error=? WHERE id=? AND fence=?').run(this.now+60000,e instanceof AccountError?e.code:'provider_unavailable',row.id,row.fence);return {claimed:true,error:'verification_pending'};}
 }
 async cancel(userId:string,subscriptionId:string,authorize:()=>void=()=>{}){
  const sub=this.db.prepare("SELECT * FROM paid_subscriptions WHERE id=? AND userId=? AND provider='waffo'").get(subscriptionId,userId);if(!sub)throw new AccountError(404,'not_found','订阅不存在');const row=this.db.prepare('SELECT * FROM waffo_checkouts WHERE providerOrderId=? AND userId=?').get(String(sub.providerId),userId)!;
  authorize();await this.sync(String(row.id));authorize();
  const state=this.db.prepare('SELECT * FROM waffo_sync_state WHERE checkoutId=?').get(String(row.id));
  if(state&&!state.willRenew&&['canceling','canceled'].includes(String(state.status)))return {cancelRequested:true};
  const requestId='maas_cancel_'+sub.id+'_'+String(state?.updated??'initial');
  this.db.prepare('INSERT OR IGNORE INTO waffo_cancellations VALUES(?,?,?,?)').run(requestId,String(sub.id),userId,this.now);
  await this.client.orders.cancelSubscription({orderId:String(sub.providerId)},{idempotencyKey:requestId});this.db.prepare('UPDATE waffo_checkouts SET availableAt=0 WHERE id=?').run(String(row.id));await this.sync(String(row.id));return {cancelRequested:true};
 }
 async portal(userId:string,authorize:()=>void=()=>{}){authorize();const r=await this.client.auth.createCustomerPortalLink({storeId:this.config.storeId,buyerIdentity:userId});authorize();hostedUrl(r.portalUrl);return {url:r.portalUrl};}
 user(userId:string){const result=this.payments.user(userId);for(const s of result.subscriptions){if(s.provider!=='waffo')continue;const state=this.db.prepare('SELECT s.* FROM waffo_sync_state s JOIN waffo_checkouts c ON c.id=s.checkoutId WHERE c.providerOrderId=? AND c.userId=?').get(String(s.providerId),userId);if(state){s.renewalFailed=state.status==='past_due';s.cancelAtPeriodEnd=state.status==='canceling';s.providerStatus=state.status;s.nextRenewalAt=state.willRenew&&s.state==='active'?state.periodEnd:null;}}return {...result,pendingCheckouts:this.db.prepare('SELECT id,state,created,checked,error FROM waffo_checkouts WHERE userId=? ORDER BY created DESC LIMIT 20').all(userId),checkoutAvailability:'waffo',checkoutEnabled:process.env.MAAS_WAFFO_CHECKOUT_ENABLED!=='false',price:{amount:this.config.amount,currency:'USD',billingPeriod:'monthly'}};}
 start(){let pending:Promise<unknown>|undefined;const timer=setInterval(()=>{if(pending)return;pending=this.sync().catch(()=>undefined).finally(()=>pending=undefined);},5000);timer.unref();return async()=>{clearInterval(timer);await pending;};}
}
