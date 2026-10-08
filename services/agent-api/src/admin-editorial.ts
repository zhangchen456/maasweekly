import { randomUUID } from 'node:crypto';
import type { IncomingMessage } from 'node:http';
import { adminWriteInput } from './admin-http.js';
import { EditorialService } from './editorial-service.js';
import { bad } from './editorial-store.js';
const operations:Record<string,string[]>={prepare:['coverage','coverageNote','monitorAcknowledgedHash'],revisions:['package'],review:['revision','outputHash','decision','checklist','note'],publish:['revision','outputHash'],compose:['queueMail'],runs:['stage']};
export async function adminEditorial(req:IncomingMessage,url:URL,userId:string,requestId:string,service:EditorialService){
 const issue=/^\/api\/admin\/weekly(?:\/([^/]+))?(?:\/(inputs|prepare|revisions|review|publish|compose|runs))?$/.exec(url.pathname);
 const run=/^\/api\/admin\/runs\/([^/]+)(?:\/(cancel|reconcile))?$/.exec(url.pathname);
 if(!issue&&!run)return null;
 const id=decodeURIComponent((issue?.[1]??run?.[1])||''),op=issue?.[2]??run?.[2];
 if(req.method==='GET'){
  if(run&&!op){if(url.search)throw bad('详情不接受查询参数');return {status:200,value:service.run(id)};}
  if(issue&&!id)return {status:200,value:service.list(url.searchParams)};
  if(issue&&op==='inputs')return {status:200,value:service.inputs(id,url.searchParams)};
  if(issue&&!op){if(url.search)throw bad('详情不接受查询参数');return {status:200,value:service.detail(id)};}
 }else{
  if(url.search)throw bad('写入不接受查询参数');
  if(issue&&!id){const target=randomUUID(),c=await adminWriteInput(req,['periodEnd','selection','budget'],userId,requestId,'weekly.create','editorial_issue',target); // Stable target is derived from period for idempotency across retries.
   const period=String(c.input.periodEnd);c.targetId='weekly-'+period;return {status:200,value:service.write(c,'create')};}
  if(issue&&op&&operations[op]){const c=await adminWriteInput(req,operations[op]!,userId,requestId,'weekly.'+op,'editorial_issue',id,()=>service.store.issue(id).version,op==='revisions'?1048576:16384);return {status:op==='runs'?202:200,value:service.write(c,op)};}
  if(run&&(op==='cancel'||op==='reconcile')){const c=await adminWriteInput(req,op==='reconcile'?['outcome','note','actualCost']:[],userId,requestId,'runs.'+op,'editorial_run',id,()=>Number(service.store.run(id).version));return {status:200,value:op==='cancel'?service.cancel(c):service.reconcile(c)};}
 }
 throw bad('接口不存在','not_found',404);
}
