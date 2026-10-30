import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign} from 'node:crypto';
import {verifyWebhook} from '@waffo/pancake-ts';
import {AccountStore} from '../account-store.js';
import {AdminStore} from '../admin-store.js';
import {WaffoTestStore,WAFFO_TEST_DEFAULTS,createWaffoTestHandler} from '../waffo-test.js';
import {createServer} from 'node:http';
const keys=generateKeyPairSync('rsa',{modulusLength:2048});
function fixture(){
 const accounts=new AccountStore(':memory:',Date.now,'waffo-test-fixture-secret-long-enough'),admin=new AdminStore(accounts);
 const login=accounts.verify('test@example.test',accounts.issueCode('test@example.test'));
 accounts.db.prepare('INSERT INTO admin_members VALUES(?,?,1,?,?)').run(login.user.id,'administrator',Date.now(),Date.now());
 let calls=0,prod=false;
 const client:any={graphql:{query:async()=>({data:{merchant:{apiKeys:[{id:'key',environment:prod?'prod':'test'}]},subscriptionProducts:[{id:WAFFO_TEST_DEFAULTS.productId,name:'test',status:'active',billingPeriod:'monthly',prices:[{currency:'USD',priceInfo:{amount:'9.99'}}]}]}})},checkout:{createSession:async(p:any,o:any)=>{calls++;assert.equal(p.currency,'USD');assert.equal(p.priceSnapshot,undefined);assert.equal(p.buyerEmail,undefined);assert.equal(o.idempotencyKey,'waffo_test_checkout_'+p.orderMerchantExternalId);return {sessionId:'cs_test',checkoutUrl:'https://pancake.waffo.ai/test',expiresAt:new Date(Date.now()+3600000).toISOString()};}},orders:{cancelSubscription:async()=>({status:'canceling'})}};
 const verifier:typeof verifyWebhook=(raw,header,options)=>verifyWebhook(raw,header,{...options,publicKey:keys.publicKey.export({type:'spki',format:'pem'}).toString()});
 const store=new WaffoTestStore(admin,{...WAFFO_TEST_DEFAULTS,origin:'http://localhost'},client,verifier);
 return {accounts,admin,login,store,calls:()=>calls,prod:()=>{prod=true;}};
}
function signed(checkout:string,overrides:Record<string,unknown>={}){
 const raw=JSON.stringify({id:'delivery-1',timestamp:new Date().toISOString(),eventId:'payment-1',eventType:'subscription.activated',storeId:WAFFO_TEST_DEFAULTS.storeId,mode:'test',data:{orderId:'ORD_test',orderMerchantExternalId:checkout},...overrides});
 const t=Date.now();return {raw,signature:`t=${t},v1=${sign('RSA-SHA256',Buffer.from(`${t}.${raw}`),keys.privateKey).toString('base64')}`};
}
test('SDK checkout uses stable idempotency, server-owned product and rejects production keys',async()=>{
 const f=fixture();try{const a=await f.store.checkout(f.login.user.id,'request_123');const b=await f.store.checkout(f.login.user.id,'request_123');assert.deepEqual(a,b);assert.equal(f.calls(),1);f.prod();await assert.rejects(f.store.checkout(f.login.user.id,'request_456'));assert.equal(f.calls(),1);}finally{f.accounts.close();}
});
test('SDK signatures, environment/store binding, durable dedup and no paid grants',async()=>{
 const f=fixture();try{const c=await f.store.checkout(f.login.user.id,'request_123');const s=signed(String(c.id));assert.deepEqual(f.store.receive(s.raw,s.signature),{received:true,matched:true});assert.deepEqual(f.store.receive(s.raw,s.signature),{received:true,duplicate:true});assert.throws(()=>f.store.receive(s.raw+' ',s.signature));
 for(const overrides of [{mode:'prod'},{storeId:'STO_wrong'}]){const bad=signed(String(c.id),overrides);assert.throws(()=>f.store.receive(bad.raw,bad.signature));}
 const conflict=signed(String(c.id),{eventType:'subscription.canceled'});assert.throws(()=>f.store.receive(conflict.raw,conflict.signature));
 assert.equal(f.store.status(f.login.user.id,String(c.id)).entitlementGranted,false);assert.throws(()=>f.store.status('other',String(c.id)));
 assert.equal(f.accounts.db.prepare("SELECT 1 FROM sqlite_master WHERE name='paid_facts'").get(),undefined);
 const unknown=signed('unknown',{id:'delivery-2'});assert.deepEqual(f.store.receive(unknown.raw,unknown.signature),{received:true,matched:false});
 }finally{f.accounts.close();}
});
test('webhook acknowledges only persisted events and administrator checkout enforces origin',async()=>{
 const f=fixture();const server=createServer(createWaffoTestHandler(f.store,'http://localhost'));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const address=server.address() as {port:number};const base=`http://127.0.0.1:${address.port}/api/payment/waffo/`;
 try{assert.equal((await fetch(base+'status')).status,401);assert.equal((await fetch(base+'checkout',{method:'POST',headers:{cookie:'maas_session='+f.login.session,origin:'https://evil.test'},body:'{}'})).status,403);
 const c=await f.store.checkout(f.login.user.id,'request_123'),s=signed(String(c.id));const result=await fetch(base+'webhook',{method:'POST',headers:{'x-waffo-signature':s.signature},body:s.raw});assert.equal(result.status,200);assert.equal(f.accounts.db.prepare('SELECT count(*) n FROM waffo_test_events').get()!.n,1);
 assert.equal((await fetch(base+'webhook',{method:'POST',body:s.raw})).status,401);
 }finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));f.accounts.close();}
});
