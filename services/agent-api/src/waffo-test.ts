import {readFileSync} from 'node:fs';
import {randomUUID,createHash} from 'node:crypto';
import type {IncomingMessage,ServerResponse} from 'node:http';
import {WaffoPancake,verifyWebhook,type WebhookEvent} from '@waffo/pancake-ts';
import {AccountError} from './account-store.js';
import type {AdminStore} from './admin-store.js';
import {authenticateAdmin} from './admin-auth.js';
import {ClientRateLimiter} from './rate-limit.js';

export interface WaffoTestConfig {merchantId:string;storeId:string;productId:string;currency:string;origin:string}
export const WAFFO_TEST_DEFAULTS={merchantId:'MER_6hWcf71KacKLDtI1J5ukzY',storeId:'STO_5XRDhjxtHscwJdETFLbN1w',productId:'PROD_07eKHHXHSf1IAc4Nzh6X94',currency:'USD'};
export function configuredWaffoTest(origin:string) {
 if(process.env.MAAS_WAFFO_TEST_ENABLED!=='1')return null;
 if(process.env.WAFFO_ENVIRONMENT!=='test')throw Error('Waffo test integration requires WAFFO_ENVIRONMENT=test');
 const privateKey=process.env.WAFFO_PRIVATE_KEY_FILE?readFileSync(process.env.WAFFO_PRIVATE_KEY_FILE,'utf8'):process.env.WAFFO_PRIVATE_KEY_BASE64?Buffer.from(process.env.WAFFO_PRIVATE_KEY_BASE64,'base64').toString('utf8'):process.env.WAFFO_PRIVATE_KEY;
 if(!privateKey||privateKey.includes('<paste-'))throw Error('Waffo test private key is not configured');
 const config={...WAFFO_TEST_DEFAULTS,origin};
 const client=new WaffoPancake({merchantId:config.merchantId,privateKey,environment:'test',fetch:(url,init)=>fetch(url,{...init,redirect:'error',signal:AbortSignal.timeout(15000)})});
 return {config,client};
}
const invalid=(message:string)=>new AccountError(400,'waffo_invalid',message);
export class WaffoTestStore {
 readonly db;
 constructor(readonly admin:AdminStore,readonly config:WaffoTestConfig,readonly client:Pick<WaffoPancake,'graphql'|'checkout'|'orders'>,readonly verify:typeof verifyWebhook=verifyWebhook){
  this.db=admin.db;
  admin.accounts.transaction(()=>this.db.exec(`CREATE TABLE IF NOT EXISTS waffo_test_checkouts(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),requestKey TEXT NOT NULL,sessionId TEXT,checkoutUrl TEXT,expiresAt TEXT,created INTEGER NOT NULL,UNIQUE(userId,requestKey));
   CREATE TABLE IF NOT EXISTS waffo_test_events(id TEXT PRIMARY KEY,businessId TEXT NOT NULL,eventType TEXT NOT NULL,checkoutId TEXT,orderId TEXT NOT NULL,payloadHash TEXT NOT NULL,payload TEXT NOT NULL,occurredAt TEXT NOT NULL,received INTEGER NOT NULL);
   CREATE INDEX IF NOT EXISTS waffo_test_events_checkout ON waffo_test_events(checkoutId,occurredAt);`));
 }
 async preflight(){
  const result=await this.client.graphql.query<{merchant:{apiKeys:{id:string;environment:string}[]};subscriptionProducts:{id:string;name:string;status:string;billingPeriod:string;prices:{currency:string;priceInfo:{amount:string}}[]}[] }>({query:'query($merchantId:String!,$storeId:String!){merchant(id:$merchantId){apiKeys{id environment}} subscriptionProducts(storeId:$storeId){id name status billingPeriod prices{currency priceInfo{amount}}}}',variables:{merchantId:this.config.merchantId,storeId:this.config.storeId}});
  // API-key environment is derived by Waffo from the signing key, not the SDK environment option.
  // Fail closed if this merchant gains any production key until exact key-environment binding is supported.
  const keys=result.data?.merchant?.apiKeys;
  if(result.errors?.length||!keys?.length||keys.some(k=>k.environment!=='test'))throw new AccountError(503,'waffo_test_key_unverified','无法确认仅使用测试密钥');
  const product=result.data?.subscriptionProducts.find(p=>p.id===this.config.productId);
  const price=product?.prices.find(p=>p.currency===this.config.currency)?.priceInfo.amount;
  if(!product||product.status!=='active'||product.billingPeriod!=='monthly'||price!=='9.99')throw new AccountError(503,'waffo_product_changed','测试商品或价格已变化，请核对配置');
  return {name:product.name,amount:price,currency:this.config.currency,billingPeriod:product.billingPeriod,environment:'test'};
 }
 async checkout(userId:string,key:string,authorize:()=>void=()=>{}){
  if(!/^[a-zA-Z0-9_-]{8,100}$/.test(key))throw invalid('缺少有效的请求标识');
  const old=this.db.prepare('SELECT * FROM waffo_test_checkouts WHERE userId=? AND requestKey=?').get(userId,key);
  if(old?.sessionId){if(Date.parse(String(old.expiresAt))<=Date.now())throw new AccountError(409,'checkout_expired','测试结账已过期，请创建新请求');return {id:old.id,checkoutUrl:old.checkoutUrl};}
  if(old&&Date.now()-Number(old.created)>23*3600000)throw new AccountError(409,'checkout_unknown','旧请求结果未知，请先核查，不能自动重试');
  await this.preflight();authorize();
  if(!this.admin.member(userId))throw new AccountError(403,'forbidden','管理员权限已撤销');
  const id=old?String(old.id):randomUUID();
  this.db.prepare('INSERT OR IGNORE INTO waffo_test_checkouts VALUES(?,?,?,NULL,NULL,NULL,?)').run(id,userId,key,Date.now());
  const row=this.db.prepare('SELECT id FROM waffo_test_checkouts WHERE userId=? AND requestKey=?').get(userId,key)!;
  const localId=String(row.id);
  const session=await this.client.checkout.createSession({productId:this.config.productId,currency:this.config.currency,orderMerchantExternalId:localId,successUrl:this.config.origin+'/subscription/waffo-test/?checkout='+localId,expiresInSeconds:3600},{idempotencyKey:'waffo_test_checkout_'+localId});
  const url=new URL(session.checkoutUrl);
  if(url.protocol!=='https:'||!(url.hostname==='waffo.ai'||url.hostname.endsWith('.waffo.ai'))||url.username||url.password||!Number.isFinite(Date.parse(session.expiresAt)))throw new AccountError(502,'waffo_response_invalid','供应商结账响应无效');
  this.db.prepare('UPDATE waffo_test_checkouts SET sessionId=?,checkoutUrl=?,expiresAt=? WHERE id=?').run(session.sessionId,session.checkoutUrl,session.expiresAt,localId);
  return {id:localId,checkoutUrl:session.checkoutUrl};
 }
 receive(raw:string,signature:string){
  let event:WebhookEvent;
  try{event=this.verify(raw,signature,{environment:'test'});}catch{throw new AccountError(401,'waffo_signature_invalid','回调签名无效');}
  if(event.mode!=='test'||event.storeId!==this.config.storeId)throw invalid('回调环境或店铺不匹配');
  if(!event.id||event.id.length>200||!event.eventId||!event.data?.orderId||!Number.isFinite(Date.parse(event.timestamp)))throw invalid('回调字段无效');
  const localId=event.data.orderMerchantExternalId;
  const matched=typeof localId==='string'?this.db.prepare('SELECT id FROM waffo_test_checkouts WHERE id=?').get(localId):undefined;
  const digest=createHash('sha256').update(raw).digest('hex');
  return this.admin.accounts.transaction(()=>{
   const old=this.db.prepare('SELECT payloadHash FROM waffo_test_events WHERE id=?').get(event.id);
   if(old){if(old.payloadHash!==digest)throw new AccountError(409,'waffo_event_conflict','重复回调内容冲突');return {received:true,duplicate:true};}
   // Durable receipt before acknowledgement; test ledger deliberately never modifies paid_* or entitlements.
   this.db.prepare('INSERT INTO waffo_test_events VALUES(?,?,?,?,?,?,?,?,?)').run(event.id,event.eventId,event.eventType,matched?String(matched.id):null,event.data.orderId,digest,raw,event.timestamp,Date.now());
   return {received:true,matched:Boolean(matched)};
  });
 }
 status(userId:string,id:string){
  const row=this.db.prepare('SELECT id,sessionId,expiresAt FROM waffo_test_checkouts WHERE id=? AND userId=?').get(id,userId);
  if(!row)throw new AccountError(404,'not_found','测试结账不存在');
  const events=this.db.prepare('SELECT eventType,businessId,orderId,occurredAt FROM waffo_test_events WHERE checkoutId=? GROUP BY eventType,businessId,orderId,occurredAt ORDER BY occurredAt DESC LIMIT 50').all(id);
  return {...row,environment:'test',events,entitlementGranted:false};
 }
 async cancel(userId:string,id:string){
  this.status(userId,id);await this.preflight();
  if(!this.admin.member(userId))throw new AccountError(403,'forbidden','管理员权限已撤销');
  const orders=this.db.prepare('SELECT DISTINCT orderId FROM waffo_test_events WHERE checkoutId=?').all(id);
  if(orders.length!==1)throw new AccountError(409,'order_unconfirmed','尚无唯一已验证供应商订单');
  return this.client.orders.cancelSubscription({orderId:String(orders[0]!.orderId)},{idempotencyKey:'waffo_test_cancel_'+id});
 }
}
export function createWaffoTestHandler(store:WaffoTestStore|null,origin:string){
 const limiter=new ClientRateLimiter({capacity:30,refillPerMinute:30});
 return async(req:IncomingMessage,res:ServerResponse)=>{
  const reply=(status:number,value:unknown)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  try{
   if(!store)throw new AccountError(503,'waffo_test_disabled','Waffo 测试支付未启用');
   const url=new URL(req.url??'/',origin),route=url.pathname.split('/').pop();
   if(!limiter.take(req).allowed)throw new AccountError(429,'rate_limited','请求频繁');
   if(route==='webhook'){
    if(req.method!=='POST')throw new AccountError(405,'method_not_allowed','仅支持POST');
    let raw=Buffer.alloc(0);for await(const chunk of req){raw=Buffer.concat([raw,Buffer.from(chunk)]);if(raw.length>65536)throw new AccountError(413,'too_large','回调过大');}
    reply(200,store.receive(raw.toString('utf8'),String(req.headers['x-waffo-signature']??'')));return;
   }
   const user=authenticateAdmin(req,store.admin,new URL(origin).protocol==='https:');
   if(req.method==='GET'&&route==='status'){reply(200,url.searchParams.has('checkout')?store.status(user.id,url.searchParams.get('checkout')!):await store.preflight());return;}
   if(req.method!=='POST')throw new AccountError(405,'method_not_allowed','仅支持POST');
   if(req.headers.origin!==origin||req.headers['sec-fetch-site']==='cross-site')throw new AccountError(403,'invalid_origin','请从本站操作');
   let raw='';for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>2048)throw new AccountError(413,'too_large','请求过大');}
   const input=JSON.parse(raw);
   if(route==='checkout'){const result=await store.checkout(user.id,String(input.requestKey??''),()=>{authenticateAdmin(req,store.admin,new URL(origin).protocol==='https:');});authenticateAdmin(req,store.admin,new URL(origin).protocol==='https:');reply(200,result);}
   else if(route==='cancel')reply(200,await store.cancel(user.id,String(input.checkout??'')));
   else throw new AccountError(404,'not_found','接口不存在');
  }catch(e){const error=e instanceof AccountError?e:new AccountError(502,'waffo_unavailable','Waffo 暂不可用或请求结果未知，请保留请求标识后查询');reply(error.status,{code:error.code,message:error.message});}
 };
}
