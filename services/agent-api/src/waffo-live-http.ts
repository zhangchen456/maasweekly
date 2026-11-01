import type {IncomingMessage,ServerResponse} from 'node:http';
import {AccountError} from './account-store.js';
import type {WaffoLiveStore} from './waffo-live.js';
export function createWaffoLiveWebhook(store:WaffoLiveStore|null){return async(req:IncomingMessage,res:ServerResponse)=>{
 const send=(status:number,body:unknown)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
 try{if(!store)throw new AccountError(503,'payment_unavailable','支付未启用');if(req.method!=='POST')throw new AccountError(405,'method_not_allowed','仅支持 POST');let size=0;const chunks:Buffer[]=[];for await(const c of req){size+=Buffer.byteLength(c);if(size>131072)throw new AccountError(413,'body_too_large','通知过大');chunks.push(Buffer.from(c));}send(200,store.receive(Buffer.concat(chunks).toString('utf8'),String(req.headers['x-waffo-signature']??'')));}
 catch(e){const error=e instanceof AccountError?e:new AccountError(503,'payment_receipt_failed','通知暂未保存，请重试');send(error.status,{code:error.code,message:error.message});}
};}
