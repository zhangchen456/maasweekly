import { AdminPayments } from './admin-payments.js';
import { AdminProblems } from './admin-problems.js';
import { AdminDelivery } from './admin-delivery.js';
import { AdminMonitor } from './admin-monitor.js';
import { analyticsRange, analyticsBusiness, migrateAnalytics } from './admin-analytics.js';
import { AdminUmami } from './admin-umami.js';
import { EditorialStore } from './editorial-store.js';
import { EditorialService } from './editorial-service.js';
import { adminEditorial } from './admin-editorial.js';
import { AdminUsers } from './admin-users.js';
import { AdminFeedback } from './admin-feedback.js';
import { randomUUID } from 'node:crypto';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { AccountError } from './account-store.js';
import type { AccountConfig } from './account-http.js';
import type { DatasetHolder } from './dataset.js';
import type { EventSink } from './observability.js';
import { ClientRateLimiter } from './rate-limit.js';
import { authenticateAdmin } from './admin-auth.js';
import { adminText } from './admin-store.js';
import type { AdminCommand, AdminStore } from './admin-store.js';
// Reuse for future write endpoints after authentication, before command().
export async function adminBody(req: IncomingMessage, fields: readonly string[], maxBytes=16384) {
  if(!/^application\/json(?:\s*;|$)/i.test(req.headers['content-type'] ?? '')) throw new AccountError(415,'invalid_content_type','请求需使用JSON');
  let size=0; const chunks:Buffer[]=[];
  for await(const chunk of req) {size+=Buffer.byteLength(chunk); if(size>maxBytes) throw new AccountError(413,'body_too_large','请求过大'); chunks.push(Buffer.from(chunk));}
  let value:Record<string,unknown>;
  try {value=JSON.parse(Buffer.concat(chunks).toString()); if(!value || Array.isArray(value) || typeof value!=='object') throw Error();} catch {throw new AccountError(400,'invalid_json','请求格式错误');}
  if(Object.keys(value).some(k=>!fields.includes(k))) throw new AccountError(400,'unknown_field','请求含未知字段');
  return value;
}
// Future routes must pass the authenticated user, never a body actor.
export async function adminWriteInput(req: IncomingMessage, fields: readonly string[], actorId: string, requestId: string, action: string, targetType: string, targetId: string, currentVersion?: () => number, maxBytes=16384): Promise<AdminCommand> {
  const idempotencyKey=adminText(req.headers['idempotency-key'],'幂等键',128);
  const input=await adminBody(req,[...fields,'reason',...(currentVersion?['expectedVersion']:[])],maxBytes);
  const reason=adminText(input.reason,'原因',1000);
  if(currentVersion && (!Number.isSafeInteger(input.expectedVersion) || Number(input.expectedVersion)<0)) throw new AccountError(400,'invalid_version','expectedVersion需为非负整数');
  return {actor:{type:'user',id:actorId},requestId,action,targetType,targetId,idempotencyKey,input,reason,expectedVersion:currentVersion?Number(input.expectedVersion):undefined,currentVersion};
}
export function createAdminHandler(store:AdminStore|null,holder:DatasetHolder,config:AccountConfig, sink?: EventSink) {
  const editorial=store?new EditorialService(new EditorialStore(store),holder):null;
  const monitor=store?new AdminMonitor(store):null;
  const delivery=store?new AdminDelivery(store):null;
  const payments=store?new AdminPayments(store):null;
  const problems=store?new AdminProblems(store):null;
  const users=store?new AdminUsers(store):null, feedback=store?new AdminFeedback(store):null;
  if(store)migrateAnalytics(store);
  let umami:AdminUmami|null=null;try{if(store)umami=new AdminUmami(store);}catch{if(store)umami=new AdminUmami(store,null);/* invalid configuration unavailable, never expose it */}
  const limiter=new ClientRateLimiter({capacity:120,refillPerMinute:60,globalCapacity:1000,globalRefillPerMinute:300,trustLoopbackProxy:config.trustProxy});
  return async(req:IncomingMessage,res:ServerResponse)=>{
    const requestId=randomUUID();
    const reply=(status:number,value:unknown)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','Vary':'Cookie','X-Content-Type-Options':'nosniff','X-Request-ID':requestId});res.end(JSON.stringify(value));};
    try {
      if(!['GET','POST'].includes(req.method ?? '')) throw new AccountError(405,'method_not_allowed','不支持该请求方式');
      if(req.headers['sec-fetch-site']==='cross-site' || (req.method==='POST' && req.headers.origin!==config.origin)) throw new AccountError(403,'invalid_origin','请从本站操作');
      if(!store) throw new AccountError(503,'admin_unavailable','后台服务未启用');
      const budget=limiter.take(req); if(!budget.allowed){res.setHeader('Retry-After',budget.retryAfterSeconds);throw new AccountError(429,'rate_limited','操作频繁，请稍后再试');}
      const user=authenticateAdmin(req,store,config.secure), url=new URL(req.url ?? '/',config.origin);
      if(url.pathname==='/api/admin/payments/totals'&&req.method==='GET'){reply(200,payments!.totals(url.searchParams));return;}
      const paymentRoute=/^\/api\/admin\/payments\/(orders|subscriptions|refunds|differences|events|reconciliations)(?:\/([^/]+))?(?:\/(refund|annotate|actions))?$/.exec(url.pathname);
      if(paymentRoute){const kind=paymentRoute[1]!,id=paymentRoute[2],op=paymentRoute[3];if(req.method==='GET'&&!id){reply(200,payments!.list(kind,url.searchParams));return;}if(req.method==='GET'&&id&&!op){if(url.search)throw new AccountError(400,'invalid_parameter','详情不接受查询');reply(200,payments!.detail(id,kind));return;}if(req.method==='GET'&&kind==='differences'&&id&&op==='actions'){reply(200,payments!.actions(id,url.searchParams));return;}if(req.method==='POST'&&id&&((kind==='orders'&&op==='refund')||(kind==='differences'&&op==='annotate'))){if(url.search)throw new AccountError(400,'invalid_parameter','写入不接受查询');const c=await adminWriteInput(req,op==='refund'?['amount']:['note'],user.id,requestId,'payments.'+op,'payment_'+kind,id);reply(200,op==='refund'?payments!.refund(c):payments!.annotate(c));return;}}
      if(url.pathname==='/api/admin/analytics'){if(req.method!=='GET')throw new AccountError(405,'method_not_allowed','仅支持GET');const now=store.accounts.now(),range=analyticsRange(url.searchParams,now),business=analyticsBusiness(store,range,now);const website=umami?await umami.query(range):{availability:'unavailable',reason:'invalid_configuration',lastSuccessAt:null,stats:null,pages:null,sources:null};
        authenticateAdmin(req,store,config.secure);reply(200,{range,business,website});return;}
      if(url.pathname==='/api/admin/problems'&&req.method==='GET'){reply(200,problems!.list(url.searchParams));return;}
      const problemRoute=/^\/api\/admin\/problems(?:\/([^/]+))?(?:\/(create|update|link|unlink|references|remove-reference|progress|verify|diagnose|cancel-run|reconcile-run))?$/.exec(url.pathname);
      if(problemRoute){if(url.search)throw new AccountError(400,'invalid_parameter','详情与写入不接受查询');const id=problemRoute[1]?decodeURIComponent(problemRoute[1]):randomUUID(),op=problemRoute[2]??(!problemRoute[1]?'create':undefined);
       if(req.method==='GET'&&problemRoute[1]&&!op){reply(200,problems!.detail(id));return;}
       if(req.method==='POST'&&op){const fields:Record<string,string[]>={create:['title','description','reproduction','versionInfo'],update:['title','description','reproduction','versionInfo'],link:['kind','relatedId','confirmed'],unlink:['kind','relatedId','confirmed'],references:['kind','value','trust','source','checkedAt'],'remove-reference':['refId'],progress:['repairStage','refId','releaseRefId','confirmed'],verify:['refId','releaseRefId','result','environment','note'],diagnose:['material','budget'],'cancel-run':['runId'],'reconcile-run':['runId','outcome','note','actualCost']};const c=await adminWriteInput(req,fields[op]!,user.id,requestId,'problems.'+op,'problem',op==='create'?'create':id,op==='create'?undefined:()=>problems!.version(id),16384);if(op==='create'){c.input={...c.input};c.targetId='problem_'+c.idempotencyKey;}reply(200,problems!.write(c,op));return;}
      }
      if(url.pathname==='/api/admin/health'&&req.method==='GET'){if(url.search)throw new AccountError(400,'invalid_parameter','健康不接受查询参数');reply(200,delivery!.health(holder));return;}
      if(url.pathname==='/api/admin/delivery'&&req.method==='GET'){reply(200,delivery!.list(url.searchParams));return;}
      const mailRoute=/^\/api\/admin\/delivery\/([^/]+)(?:\/(retry|reconcile))?$/.exec(url.pathname);
      if(mailRoute){if(url.search)throw new AccountError(400,'invalid_parameter','操作与详情不接受查询参数');const id=decodeURIComponent(mailRoute[1]!);if(req.method==='GET'&&!mailRoute[2]){reply(200,delivery!.detail(id));return;}if(req.method==='POST'&&mailRoute[2]){const op=mailRoute[2],c=await adminWriteInput(req,[],user.id,requestId,'delivery.'+op,'mail_delivery',id,()=>delivery!.version(id));reply(200,delivery!.write(c,op));return;}}
      if(url.pathname.startsWith('/api/admin/monitor/')){
        const route=url.pathname.slice('/api/admin/monitor/'.length);
        if(req.method==='GET'){
          if(route==='sources'){reply(200,monitor!.sources(url.searchParams));return;}
          if(route==='runs'){reply(200,monitor!.runs(url.searchParams));return;}
          if(route==='anomalies'){reply(200,monitor!.anomalies(url.searchParams));return;}
          const detail=/^runs\/([a-zA-Z0-9:_-]+)$/.exec(route);if(detail){if(url.search)throw new AccountError(400,'invalid_parameter','详情不接受查询参数');reply(200,monitor!.projectRun(monitor!.run(detail[1]!)));return;}
        }
        const update=/^anomalies\/([a-zA-Z0-9:_-]+)$/.exec(route);
        if(req.method==='POST'&&update){if(url.search)throw new AccountError(400,'invalid_parameter','写入不接受查询参数');const c=await adminWriteInput(req,['state','resolutionRunId'],user.id,requestId,'monitor.anomaly.update','monitor_anomaly',update[1]!,()=>monitor!.anomalyVersion(update[1]!));reply(200,monitor!.update(c));return;}
        throw new AccountError(404,'not_found','接口不存在');
      }
      const editorialResult=await adminEditorial(req,url,user.id,requestId,editorial!);
      if(editorialResult){reply(editorialResult.status,editorialResult.value);return;}
      const route=/^\/api\/admin\/(users|feedback)(?:\/([^/]+))?(?:\/(.*))?$/.exec(url.pathname);
      if(route){
        const kind=route[1]!,id=route[2]?decodeURIComponent(route[2]):undefined,sub=route[3];
        if(req.method==='GET'){
          if(!id){reply(200,kind==='users'?users!.list(url.searchParams):feedback!.list(url.searchParams));return;}
          if(!sub){if(url.search)throw new AccountError(400,'invalid_parameter','详情不接受查询参数');reply(200,kind==='users'?users!.detail(id):feedback!.detail(id));return;}
          if(kind==='feedback'&&['notes','verifications'].includes(sub)){reply(200,feedback!.records(id,sub as 'notes'|'verifications',url.searchParams));return;}
          const image=/^images\/([0-2])$/.exec(sub);
          if(kind==='feedback'&&image){if(url.search)throw new AccountError(400,'invalid_parameter','图片不接受查询参数');feedback!.ops(id);const data=feedback!.feedback.screenshot(id,Number(image[1]));if(!data||!['image/png','image/jpeg','image/webp'].includes(data.mime))throw new AccountError(404,'not_found','截图不存在');res.writeHead(200,{'Content-Type':data.mime,'Cache-Control':'no-store','Vary':'Cookie','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox",'X-Request-ID':requestId});res.end(data.bytes);return;}
        }else if(id&&sub){
          if(url.search)throw new AccountError(400,'invalid_parameter','写入不接受查询参数');
          const credential=/^tokens\/([^/]+)\/revoke$/.exec(sub),operation=credential?'credential':sub;
          const fields=kind==='users'?operation==='entitlement'?['operation','starts','ends']:operation==='revoke-sessions'||credential?[]:null:operation==='update'?['stage','priority','publicReply','resolutionType','relatedFeedbackId']:operation==='notes'?['body']:operation==='verify'?['kind','artifactRef','releaseRef','result','note','environment']:null;
          if(fields){const command=await adminWriteInput(req,fields,user.id,requestId,kind+'.'+sub,kind==='users'?'user':'feedback',id,()=>kind==='users'?users!.version(id):feedback!.version(id));reply(200,kind==='users'?users!.write(command,operation,credential?.[1]):feedback!.write(command,operation));return;}
        }
        throw new AccountError(404,'not_found','接口不存在');
      }
      if(req.method==='POST') throw new AccountError(404,'not_found','接口不存在');
      switch(url.pathname) {
        case '/api/admin/me': reply(200,{id:user.id,displayName:store.accounts.profile(user).displayName || user.email,role:'administrator',capabilities:['overview:read','audit:read','users:read','users:write','feedback:read','feedback:write','weekly:read','weekly:write','analytics:read','monitor:read','monitor:write','delivery:read','delivery:write','health:read','problems:read','problems:write']});return;
        case '/api/admin/overview': {
          store.db.prepare('SELECT 1').get(); const asOf=new Date(store.accounts.now()).toISOString();
          const item=(value:unknown,availability='available')=>({value,asOf,availability});
          reply(200,{apiTime:item(asOf),datasetVersion:item(holder.current?.version ?? null,holder.current?'available':'unavailable'),dataThrough:item(holder.current?.dataThrough ?? null,holder.current?'available':'unavailable'),database:item(true),releaseVersion:item(null,'not_provided'),pendingFeedback:item(store.db.prepare("SELECT count(*) AS n FROM feedback f LEFT JOIN feedback_ops o ON o.feedbackId=f.id WHERE coalesce(o.stage,'triage')!='resolved'").get()!.n)});return;
        }
        case '/api/admin/audit':reply(200,store.audit(url.searchParams));return;
        default:throw new AccountError(404,'not_found','接口不存在');
      }
    } catch(error) {const e=error instanceof AccountError?error:new AccountError(503,'admin_unavailable','后台服务暂不可用');try {sink?.({kind:'admin.rejected',code:e.code,requestId});} catch { /* diagnostics never fail responses */ } reply(e.status,{code:e.code,message:e.message,requestId});}
  };
}
