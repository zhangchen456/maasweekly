import {createHmac,timingSafeEqual} from 'node:crypto';
import type {AdminDelivery} from './admin-delivery.js';
// Verify exact raw bytes before JSON normalization. Svix signing timestamp is distinct from event time.
export function importReceipt(delivery:AdminDelivery,envelope:any,secret:string,local=false){
 if(!envelope||Object.keys(envelope).sort().join(',')!=='headers,raw'||typeof envelope.raw!=='string'||Buffer.byteLength(envelope.raw)>128*1024||!envelope.headers||Object.keys(envelope.headers).sort().join(',')!=='svix-id,svix-signature,svix-timestamp')throw Error('invalid receipt envelope');
 const h=envelope.headers,id=h['svix-id'],ts=h['svix-timestamp'],sig=h['svix-signature'];
 if(typeof id!=='string'||!/^[\w-]{1,128}$/.test(id)||typeof ts!=='string'||!/^\d{10}$/.test(ts)||typeof sig!=='string'||sig.length>2048||Math.abs(delivery.admin.accounts.now()-Number(ts)*1000)>300000||!/^whsec_[A-Za-z0-9+/=]+$/.test(secret))throw Error('invalid receipt authentication');
 const expected=createHmac('sha256',Buffer.from(secret.slice(6),'base64')).update(`${id}.${ts}.${envelope.raw}`).digest();
 if(!sig.split(' ').some((s:string)=>{const [v,b]=s.split(',');if(v!=='v1'||!b)return false;const actual=Buffer.from(b,'base64');return actual.length===expected.length&&timingSafeEqual(actual,expected);} ))throw Error('invalid receipt signature');
 const v=JSON.parse(envelope.raw),map:Record<string,string>={'email.sent':'accepted','email.delivered':'delivered','email.bounced':'failed','email.failed':'failed','email.delivery_delayed':'unknown'};
 const state=map[v.type],messageId=v.data?.email_id,eventAt=Date.parse(v.created_at);if(!state||typeof messageId!=='string'||!/^[\w-]{1,128}$/.test(messageId)||!Number.isSafeInteger(eventAt))throw Error('unsupported receipt');
 const provider=local?'local':'resend';const rows=delivery.db.prepare('SELECT kind,jobId FROM mail_delivery WHERE provider=? AND messageId=?').all(provider,messageId);if(rows.length!==1)throw Error('receipt message not uniquely matched');
 return delivery.evidence({id:provider+':'+id,job:rows[0]!.kind+':'+rows[0]!.jobId,provider,messageId,state,eventAt,timeBasis:'event'});
}
