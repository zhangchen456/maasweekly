import {randomUUID} from 'node:crypto';
import type {AdminDelivery} from './admin-delivery.js';
// Operator-only authenticated fixed-origin status lookup; no send, reset, or arbitrary URL.
export async function queryMail(delivery:AdminDelivery,job:string,key:string,request:typeof fetch=fetch){
 const r=delivery.detail(job);if(r.provider!=='resend'||!r.messageId||!key)throw Error('saved Resend message ID and operator API key required');
 const response=await request('https://api.resend.com/emails/'+encodeURIComponent(String(r.messageId)),{redirect:'error',signal:AbortSignal.timeout(5000),headers:{Authorization:'Bearer '+key}});
 if(!response.ok)throw Error('provider query unavailable; 404 does not prove not sent');
 if(Number(response.headers.get('content-length')??0)>131072)throw Error('provider response too large');const reader=response.body?.getReader();if(!reader)throw Error('empty provider response');const parts:Uint8Array[]=[];let size=0;try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>131072)throw Error('provider response too large');parts.push(value);}}finally{await reader.cancel();}
 const v=JSON.parse(Buffer.concat(parts).toString()),map:Record<string,string>={sent:'accepted',delivered:'delivered',bounced:'failed',failed:'failed',delivery_delayed:'unknown'};
 const state=map[v.last_event];if(v.id!==r.messageId||!state)throw Error('provider status unsupported');
 // Retrieve API supplies last_event but not its timestamp. Keep query observation distinct from event time.
 return delivery.evidence({id:'resend:query_'+randomUUID(),job,provider:'resend',messageId:r.messageId,state,eventAt:delivery.admin.accounts.now(),timeBasis:'query'});
}
