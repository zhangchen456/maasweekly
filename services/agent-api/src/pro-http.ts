import { PaymentSimulator } from './payment-simulator.js';
import { PaymentStore,paymentMonthEnd } from './payment-store.js';
import { AdminStore } from './admin-store.js';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { AccountError, type User } from './account-store.js';
import { ProStore, csv, csvRows, markdown, parseScope, matches, xml } from './pro-store.js';
import type { AccountConfig } from './account-http.js';
import type { DatasetHolder } from './dataset.js';
import { ClientRateLimiter } from './rate-limit.js';

export function proUser(store: ProStore, req: IncomingMessage, config: AccountConfig): User | undefined {
  if (req.headers.authorization) {
    const match = /^Bearer ([A-Za-z0-9_-]{43})$/.exec(req.headers.authorization);
    if (!match) throw new AccountError(401,'invalid_token','访问凭证无效');
    return store.authenticate(match[1]!, 'api');
  }
  const name = config.secure ? '__Host-maas_session' : 'maas_session';
  const session = (req.headers.cookie ?? '').split(';').map(s => s.trim()).find(s => s.startsWith(`${name}=`))?.slice(name.length+1) ?? '';
  return store.accounts.user(session);
}
async function read(req: IncomingMessage) {
  if (!req.headers['content-type']?.startsWith('application/json')) throw new AccountError(415,'invalid_content_type','请求需使用JSON');
  const buffers: Buffer[] = []; let n = 0;
  for await (const chunk of req) { n += Buffer.byteLength(chunk); if (n > 16384) throw new AccountError(413,'body_too_large','请求过大'); buffers.push(Buffer.from(chunk)); }
  try { const v = JSON.parse(Buffer.concat(buffers).toString()); if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error(); return v as Record<string,unknown>; }
  catch { throw new AccountError(400,'invalid_json','请求格式错误'); }
}
export function createProHandler(store: ProStore | null, holder: DatasetHolder, config: AccountConfig, mailAvailable: boolean) {
  const limiter = new ClientRateLimiter({capacity:120,refillPerMinute:60,trustLoopbackProxy:config.trustProxy});
  return async (req: IncomingMessage,res: ServerResponse) => {
    const send = (value: unknown, status=200, type='application/json; charset=utf-8') => { res.writeHead(status,{'Content-Type':type}); res.end(type.startsWith('application/json') ? JSON.stringify(value) : String(value)); };
    res.setHeader('Cache-Control','private, no-store'); res.setHeader('Vary','Cookie, Authorization'); res.setHeader('X-Content-Type-Options','nosniff'); res.setHeader('Referrer-Policy','no-referrer');
    try {
      if (!store) throw new AccountError(503,'pro_unavailable','专业服务尚未启用');
      const allowance = limiter.take(req); if (!allowance.allowed) { res.setHeader('Retry-After',allowance.retryAfterSeconds); throw new AccountError(429,'rate_limited','操作频繁，请稍后重试'); }
      const url = new URL(req.url ?? '/',config.origin); if (url.href.length > 8192) throw new AccountError(413,'url_too_large','请求过大');
      const route = url.pathname.slice('/api/pro/'.length);
      if (!['GET','POST'].includes(req.method ?? '')) throw new AccountError(405,'method_not_allowed','不支持该方法');
      if (req.method === 'POST' && (req.headers.origin !== config.origin || req.headers['sec-fetch-site'] === 'cross-site')) throw new AccountError(403,'invalid_origin','请从本站操作');
      const input = req.method === 'POST' ? await read(req) : {};
      if (route === 'unsubscribe' && req.method === 'POST') { if (typeof input.token !== 'string') throw new AccountError(400,'invalid_token','退订链接无效'); store.unsubscribe(input.token); send({message:'已关闭专业简报邮件，免费提醒不受影响'}); return; }
      if (route === 'feed' && req.method === 'GET') {
        const user = store.authenticate(url.searchParams.get('token') ?? '', 'rss');
        const scope = store.settings(user.id)?.scope;
        const items = scope ? store.feedContents().filter(c => matches(c,scope)).slice(0,30) : [];
        send(`<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>MaaS 专业情报</title><link>${xml(config.origin+'/pro/')}</link><description>按你的范围筛选的审核内容；阅读全文需登录</description>${items.map(c => `<item><title>${xml((c.withdrawn ? '[已撤回] ' : '')+c.title)}</title><link>${xml(config.origin+'/pro/?content='+encodeURIComponent(c.id))}</link><guid isPermaLink="false">${xml(c.id)}</guid><description>${xml((c.withdrawn ? '该内容已撤回，请登录查看最新状态。' : c.preview)+(c.correction ? '\n更正：'+c.correction : ''))}</description></item>`).join('')}</channel></rss>`,200,'application/rss+xml; charset=utf-8'); return;
      }
      const user = proUser(store,req,config);
      if (route === 'catalog' && req.method === 'GET') {
        store.event('catalog_view','',user?.id);
        send({items:store.contents().map(c => ({id:c.id,version:c.version,title:c.title,preview:c.preview,kind:c.kind,providers:c.providers,models:c.models,families:c.families,topics:c.topics,period:c.period,dataThrough:c.dataThrough,coverage:c.coverage,sample:c.sample,correction:c.correction})),entitlement:user ? store.entitlement(user.id) : null}); return;
      }
      if (route.startsWith('content/') && req.method === 'GET') {
        const c = store.get(decodeURIComponent(route.slice(8)),user?.id);
        store.event(['markdown','csv'].includes(url.searchParams.get('format')??'') ? (c.sample?'sample_export':'content_export') : c.sample ? 'sample_read' : 'content_read',c.id,user?.id);
        const format = url.searchParams.get('format');
        if (format === 'markdown' || format === 'csv') { res.setHeader('Content-Disposition',`attachment; filename="maas-pro.${format === 'csv' ? 'csv' : 'md'}"`); send(format === 'csv' ? csv(c) : markdown(c),200,format === 'csv' ? 'text/csv; charset=utf-8' : 'text/markdown; charset=utf-8'); }
        else send(c); return;
      }
      if (!user) throw new AccountError(401,'unauthenticated','请先登录');
      // Bearer tokens are read-only; account management requires the website session.
      if (req.headers.authorization && (req.method === 'POST' || ['tokens','rss-address','billing'].includes(route) || route.startsWith('billing/'))) throw new AccountError(403,'session_required','请在网站账户中管理凭证');
      if (route.startsWith('weekly/') && req.method === 'GET') {
        store.require(user.id);
        const id=route.slice(7); if (!/^\d{4}-\d{2}-\d{2}$/.test(id)) throw new AccountError(404,'not_found','周报不存在');
        const root=process.env.PRIVATE_WEEKLY_ROOT ?? (process.env.MAAS_RELEASE_DIR ? path.join(process.env.MAAS_RELEASE_DIR,'data/private-weekly') : path.resolve(process.env.PUBLIC_DATA_ROOT ?? 'data/public/v1','../../private-weekly'));
        let html:string;try{html=readFileSync(path.join(root,id+'.html'),'utf8');}catch{throw new AccountError(404,'not_found','周报暂不可用');}
        store.event('weekly_read',id,user.id);send(html,200,'text/html; charset=utf-8');return;
      }
      if(route==='billing'&&req.method==='GET'){const payments=new PaymentStore(new AdminStore(store.accounts));send({...payments.user(user.id),entitlement:store.entitlement(user.id),checkoutAvailability:process.env.MAAS_PAYMENT_MODE==='simulator'&&['localhost','127.0.0.1'].includes(new URL(config.origin).hostname)?'simulator':'unavailable',reason:'real_sandbox_provider_not_configured'});return;}
      if(['billing/checkout','billing/simulator-result','billing/cancel'].includes(route)&&req.method==='POST'){
       if(process.env.MAAS_PAYMENT_MODE!=='simulator'||!['localhost','127.0.0.1'].includes(new URL(config.origin).hostname))throw new AccountError(503,'payment_unavailable','支付沙箱渠道尚未配置，未产生扣款');
       const payments=new PaymentStore(new AdminStore(store.accounts)),sim=new PaymentSimulator(payments);
       if(route==='billing/checkout'){if(typeof input.key!=='string')throw new AccountError(400,'invalid_key','缺少订单幂等键');const o=payments.createOrder(user.id,input.key);send({orderId:o.id,url:'/subscription/sandbox/?order='+encodeURIComponent(String(o.id)),mode:'simulator'});return;}
       if(typeof input.orderId!=='string')throw new AccountError(400,'invalid_order','缺少订单');const o=payments.order(input.orderId);if(o.userId!==user.id)throw new AccountError(404,'not_found','订单不存在');
       if(route==='billing/cancel'){sim.action(String(o.id),'cancel');send({cancelRequested:true,mode:'simulator'});return;}
       if(!['paid','failed'].includes(String(input.outcome)))throw new AccountError(400,'invalid_outcome','模拟结果无效');const previous=payments.db.prepare('SELECT id FROM paid_simulator_objects WHERE id=?').get('sim_'+input.orderId+'_'+String(input.outcome));if(previous){sim.deliver(String(previous.id));send({verified:true,mode:'simulator'});return;}const now=store.accounts.now(),end=paymentMonthEnd(now);const f=sim.publish({id:'sim_'+input.orderId+'_'+String(input.outcome),kind:input.outcome,orderId:o.id,subscriptionId:o.subscriptionId,objectId:'sim_payment_'+o.id,currency:o.currency,amount:o.amount,starts:now,ends:end,occurredAt:now});sim.deliver(f.id);send({verified:true,mode:'simulator'});return;
      }
      if (route === 'me' && req.method === 'GET') { const settings = store.settings(user.id); send({betaAvailable:store.betaAvailable,entitlement:store.entitlement(user.id),settings:settings ? {scope:settings.scope,emailEnabled:settings.emailEnabled} : null,reports:store.reports(user.id),applied:Boolean(store.db.prepare('SELECT 1 FROM pro_applications WHERE userId=?').get(user.id)),mailAvailable}); return; }
      if (route === 'beta' && req.method === 'POST') { send({entitlement:store.activateBeta(user.id)}); return; }
      if (route === 'apply' && req.method === 'POST') { if (typeof input.scenario !== 'string') throw new AccountError(400,'invalid_application','请填写使用场景'); store.apply(user.id,input.scenario); send({saved:true}); return; }
      if (route === 'settings' && req.method === 'POST') {
        if (typeof input.emailEnabled !== 'boolean') throw new AccountError(400,'invalid_preference','请选择邮件设置');
        if (input.emailEnabled && !mailAvailable) throw new AccountError(503,'mail_unavailable','邮件服务未配置');
        const scope = parseScope(input.scope), ds = holder.current;
        if (!ds) throw new AccountError(503,'data_unavailable','目录暂不可用');
        const catalog = ds.modelIdentities;
        if (scope.models.some(id => !catalog.models.some(m => m.modelId === id)) || scope.families.some(id => !catalog.families.some(f => f.familyId === id)) || scope.providers.some(id => !ds.status.providers.some(p => p.providerId === id))) throw new AccountError(400,'unknown_scope','请选择目录内的关注对象');
        const result = store.configure(user.id,scope,input.emailEnabled); send({scope:result!.scope,emailEnabled:result!.emailEnabled,matching:store.contents().filter(c => matches(c,scope)).map(c => c.id)}); return;
      }
      if (route === 'tokens' && req.method === 'GET') { send({items:store.tokens(user.id)}); return; }
      if (route === 'token' && req.method === 'POST') { if (typeof input.name !== 'string' || !['api','rss'].includes(String(input.purpose))) throw new AccountError(400,'invalid_token','凭证配置无效'); send(store.mint(user.id,input.name,input.purpose as 'api'|'rss',input.days === undefined ? 30 : Number(input.days))); return; }
      if (route === 'revoke-token' && req.method === 'POST') { if (typeof input.id !== 'string') throw new AccountError(400,'invalid_token','凭证无效'); store.revoke(user.id,input.id); send({revoked:true}); return; }
      if (route === 'rss-address' && req.method === 'GET') { store.require(user.id); const token = store.rssSecret(user.id); send({url:token ? `${config.origin}/api/pro/feed?token=${encodeURIComponent(token)}` : null}); return; }
      if (route.startsWith('report/') && req.method === 'GET') {
        const report = store.report(user.id,route.slice(7));
        store.event(['markdown','csv'].includes(url.searchParams.get('format')??'') ? 'report_export' : 'report_read',report.id,user.id);
        const format = url.searchParams.get('format');
        if (format === 'markdown' || format === 'csv') {
          const metadata = {reportId:report.id,reportPeriod:report.period,scope:JSON.stringify(report.scope),coverage:report.coverage};
          const exportRows: Record<string,string>[] = [];
          for (const c of report.items) {
            if ('withdrawn' in c) { exportRows.push({...metadata,contentId:c.id,version:String(c.version),result:'withdrawn'}); continue; }
            for (const row of c.rows.length ? c.rows : [{}]) exportRows.push({...row,...metadata,contentId:c.id,version:String(c.version),from:c.period.from,to:c.period.to,dataThrough:c.dataThrough,conditions:c.conditions,limitations:c.limitations,evidence:JSON.stringify(c.evidence),sources:c.evidence.map(e=>e.url).join(' ')});
          }
          if (!exportRows.length) exportRows.push({...metadata,result:report.coverage === 'normal' ? 'no_matching_changes' : 'coverage_failure'});
          res.setHeader('Content-Disposition',`attachment; filename="maas-report.${format === 'csv' ? 'csv' : 'md'}"`);
          send(format === 'csv' ? csvRows(exportRows) : `# MaaS 个人简报 ${report.period}\n\n范围：${JSON.stringify(report.scope)}\n覆盖：${report.coverage}\n\n${report.items.length ? report.items.map(c => 'withdrawn' in c ? `内容 ${c.id} 已撤回` : markdown(c)).join('\n\n---\n\n') : report.coverage === 'normal' ? '本期没有匹配的重要变化。' : '本期覆盖异常，无法确认是否有变化。'}`,200,format === 'csv' ? 'text/csv; charset=utf-8' : 'text/markdown; charset=utf-8');
        } else send(report); return;
      }
      throw new AccountError(404,'not_found','接口不存在');
    } catch (error) { const e = error instanceof AccountError ? error : new AccountError(503,'pro_error','专业服务暂不可用'); if (!res.headersSent) send({code:e.code,message:e.message},e.status); else res.end(); }
  };
}
