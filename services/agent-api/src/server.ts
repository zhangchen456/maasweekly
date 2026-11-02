import {ProjectDelivery} from './project-mail.js';
import {ProjectStore} from './project-store.js';
import {Membership,membershipEnabled,membershipContext} from './membership.js';
import {configuredWaffoLive,WaffoLiveStore} from './waffo-live.js';
import {createWaffoLiveWebhook} from './waffo-live-http.js';
import {configuredWaffoTest,WaffoTestStore,createWaffoTestHandler} from './waffo-test.js';
import { PaymentStore } from './payment-store.js';
import { createPaymentWebhook } from './payment-http.js';
import { trackAnalyticsRequest } from './admin-analytics.js';
import { AdminStore } from './admin-store.js';
import { createAdminHandler } from './admin-http.js';
/**
 * server.ts：agent-api 启动入口（Task 03 M5）。
 *
 * 默认绑定 127.0.0.1（生产由反向代理做 TLS）；PORT 环境变量定端口。
 * PUBLIC_DATA_ROOT 指定数据根（测试注入临时目录）；RELOAD_INTERVAL_MS
 * 轮询 manifest 热重载（0=禁用），另支持 SIGHUP。
 */
import http from 'node:http';
import {createRuntimeHealthHandler, runtimeIdentity} from './runtime-health.js';
import { performance, monitorEventLoopDelay } from 'node:perf_hooks';
import { JsonlLogger, instrumentRequest, freshnessSummary } from './observability.js';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { SiteDataStore } from './site-data-store.js';
import { SiteRuntime } from './site-runtime.js';
import { createSiteHandler, type AstroHandler } from './site-http.js';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { DatasetHolder } from './dataset.js';
import { createMcpHandler, DEFAULT_MCP_CONFIG } from './mcp.js';
import { createHandler, type ServerConfig } from './http.js';
import { countryHandler } from './country.js';
import { AccountStore } from './account-store.js';
import { createMailer } from './account-mail.js';
import { ProStore } from './pro-store.js';
import { createProHandler } from './pro-http.js';
import { createAccountHandler } from './account-http.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..', '..');

const PORT = parseInt(process.env.PORT ?? '8787', 10);
const HOST = process.env.HOST ?? '127.0.0.1';
const DATA_ROOT = process.env.PUBLIC_DATA_ROOT
  ?? path.join(repoRoot, 'data', 'public', 'v1');
const SITE_ENTRY=process.env.MAAS_SITE_ENTRY;
const siteStore=SITE_ENTRY ? new SiteDataStore({connectionString:process.env.MAAS_SITE_DATABASE_URL}) : null;
const siteRuntime=siteStore ? new SiteRuntime(siteStore) : null;
const RELOAD_MS = parseInt(process.env.RELOAD_INTERVAL_MS ?? (SITE_ENTRY ? '5000' : process.env.MAAS_RELEASE_DIR ? '0' : '30000'), 10);
if (!Number.isSafeInteger(RELOAD_MS) || RELOAD_MS < 0) throw new Error('invalid RELOAD_INTERVAL_MS');
const TRUST_PROXY = process.env.MAAS_TRUST_LOOPBACK_PROXY === '1';

const config: ServerConfig = {
  rateLimit: {
    trustLoopbackProxy: TRUST_PROXY,
    globalCapacity: parseInt(process.env.RATE_GLOBAL_CAPACITY ?? '6000', 10),
    globalRefillPerMinute: parseInt(process.env.RATE_GLOBAL_REFILL_PER_MIN ?? '3000', 10),
    capacity: parseInt(process.env.RATE_CAPACITY ?? '60', 10),
    refillPerMinute: parseInt(process.env.RATE_REFILL_PER_MIN ?? '30', 10),
  },
};

// MCP 独立配置（任务书 §4.1：独立限流，不消耗 REST 匿名桶）
const mcpConfig = {
  originAllowlist: (process.env.MCP_ALLOWED_ORIGINS
    ?? DEFAULT_MCP_CONFIG.originAllowlist.join(',')).split(',').map((s) => s.trim()).filter(Boolean),
  maxBodyBytes: parseInt(process.env.MCP_MAX_BODY_BYTES ?? String(DEFAULT_MCP_CONFIG.maxBodyBytes), 10),
  rateLimit: {
    trustLoopbackProxy: TRUST_PROXY,
    globalCapacity: parseInt(process.env.MCP_RATE_GLOBAL_CAPACITY ?? '3000', 10),
    globalRefillPerMinute: parseInt(process.env.MCP_RATE_GLOBAL_REFILL_PER_MIN ?? '3000', 10),
    capacity: parseInt(process.env.MCP_RATE_CAPACITY ?? '30', 10),
    refillPerMinute: parseInt(process.env.MCP_RATE_REFILL_PER_MIN ?? '30', 10),
  },
};

// cursor MAC 密钥（验收 P1-2）：默认进程内随机（重启后旧 cursor 全失效，
// 可接受——cursor 是短期分页令牌）；多实例部署设 CURSOR_SECRET 共享。
import { setCursorSecret } from './query.js';
setCursorSecret(process.env.CURSOR_SECRET ?? randomUUID());

const holder = new DatasetHolder(DATA_ROOT, {
  ...(siteRuntime ? {prepare:dataset=>siteRuntime.prepare(dataset),publicationFile:'publication.json' as const} : {}),
  maxRetainedVersions: parseInt(process.env.RETAINED_DATASET_MAX_VERSIONS ?? '2', 10),
  maxRetainedBytes: parseInt(process.env.RETAINED_DATASET_MAX_BYTES ?? String(128 * 1024 * 1024), 10),
});
let projects:ProjectStore|undefined;
const logger = process.env.MAAS_DIAGNOSTICS === '0' ? undefined : new JsonlLogger();
const releaseId = runtimeIdentity(process.env.MAAS_RELEASE_DIR);
const reload = async (force = false) => {
  const started = performance.now();
  const result = await holder.reloadAsync({ force });
  logger?.emit({ kind: 'dataset.load', releaseId, datasetVersion: holder.current?.version ?? null,
    result, force, elapsedMs: performance.now() - started,
    errorCode: result === 'failed' ? 'dataset_load_failed' : null,
    dataCounts: result === 'changed' && holder.current ? { changes: holder.current.changes.length,
      prices: holder.current.prices.length, evidence: holder.current.evidenceById.size,
      unresolvedPrices: holder.current.prices.filter(price => !price.modelId).length } : undefined,
    evidenceIntegrity: result === 'changed' ? 'validated' : undefined,
    cache: holder.cacheState, counters: { ...holder.metrics } });
  if(projects&&holder.current&&(result==='changed'||force)){try{if(projects.refreshAll(holder.current).failed)logger?.emit({kind:'projects.refresh_failed'});}catch{logger?.emit({kind:'projects.refresh_failed'});}}
  return result;
};
await reload();

// dispatcher：/api/mcp → MCP；其余 → REST（http.ts 行为不变）
const restHandler = instrumentRequest(createHandler(holder, config), holder, releaseId, logger?.emit);

const accountOrigin = process.env.MAAS_ACCOUNT_ORIGIN ?? 'https://daily.maas.click';
const accountUrl = new URL(accountOrigin);
if (accountOrigin !== accountUrl.origin || (accountUrl.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(accountUrl.hostname))) throw new Error('invalid MAAS_ACCOUNT_ORIGIN');
const accountStore = process.env.MAAS_ACCOUNT_DB ? new AccountStore(path.resolve(process.env.MAAS_ACCOUNT_DB)) : null;
const proStore = accountStore ? new ProStore(accountStore) : null;
if(membershipEnabled()&&(!accountStore||!proStore))throw new Error('membership requires account database');
const membership=membershipEnabled()&&accountStore&&proStore?new Membership(accountStore,proStore,accountUrl.protocol==='https:'):undefined;
projects=accountStore&&proStore?new ProjectStore(accountStore,proStore):undefined;
if(projects){new ProjectDelivery(projects);if(holder.current)if(projects.refreshAll(holder.current).failed)logger?.emit({kind:'projects.refresh_failed'});}
const accountHandler=createAccountHandler(accountStore,createMailer(),holder,{origin:accountOrigin,secure:accountUrl.protocol==='https:',trustProxy:TRUST_PROXY},membership,projects);
const proConfig = { origin: accountOrigin, secure: accountUrl.protocol === 'https:', trustProxy: TRUST_PROXY, membership };
const adminStore = accountStore ? new AdminStore(accountStore) : null;
const adminHandler = createAdminHandler(adminStore, holder, proConfig, logger?.emit);
const paymentWebhook=createPaymentWebhook(adminStore?new PaymentStore(adminStore):null,accountOrigin);
const liveConfig=configuredWaffoLive(accountOrigin);
const livePayments=adminStore&&liveConfig?new WaffoLiveStore(adminStore,liveConfig.config,liveConfig.client):null;
const stopPaymentSync=livePayments?.start();
const liveWebhook=createWaffoLiveWebhook(livePayments);
const waffoConfig=configuredWaffoTest(accountOrigin);
const waffoHandler=createWaffoTestHandler(adminStore&&waffoConfig?new WaffoTestStore(adminStore,waffoConfig.config,waffoConfig.client):null,accountOrigin);
let site:ReturnType<typeof createSiteHandler>|undefined;
if(siteRuntime&&SITE_ENTRY){
  if(!holder.current)throw new Error('versioned site data unavailable');
  siteRuntime.install();
  const module=await siteRuntime.run(holder.current,()=>import(pathToFileURL(path.resolve(SITE_ENTRY)).href)) as {handler:AstroHandler};
  site=createSiteHandler(holder,siteRuntime,module.handler,accountOrigin);
}
const proHandler = createProHandler(proStore, holder, proConfig, Boolean(createMailer()),site?.weekly,livePayments);
const mcpHandler = instrumentRequest(createMcpHandler(holder, mcpConfig,undefined,membership), holder, releaseId, logger?.emit);
const proMcpHandler = proStore ? createMcpHandler(holder, mcpConfig, {store:proStore,config:proConfig}) : proHandler;
const runtimeHealthHandler = createRuntimeHealthHandler(holder, releaseId);
const server = http.createServer((req, res) => {
  if(membership){
    try{
      const pathname=new URL(req.url??'/',accountOrigin).pathname;
      if(pathname.startsWith('/api/payment/')||pathname==='/_runtime/health'){dispatch(req,res);return;}
      const access=membership.access(req);
      const machine=pathname.startsWith('/api/v1/')||pathname==='/api/mcp'||pathname==='/api/pro/mcp';
      const browser=pathname.startsWith('/api/browser/');
      if(machine&&req.method!=='OPTIONS'&&pathname!=='/api/v1/status'&&!access.machine){res.writeHead(401,{'Content-Type':'application/problem+json','Cache-Control':'no-store'});res.end(JSON.stringify({status:401,code:'token_required',detail:'请登录账户创建API/MCP访问凭证',recovery:'/account/'}));return;}
      if(browser&&access.machine){res.writeHead(403,{'Content-Type':'application/problem+json','Cache-Control':'no-store'});res.end(JSON.stringify({code:'session_required',detail:'浏览器数据通道使用网站会话；机器查询请使用/api/v1或/api/mcp'}));return;}
      if(browser)req.url=req.url!.replace('/api/browser/','/api/v1/');
      if((machine||pathname.startsWith('/api/pro/'))&&access.machine&&req.method==='GET'&&pathname!=='/api/v1/status'){
        const refund=membership.reserve(access.userId!);res.once('finish',()=>{if(res.statusCode!==200)refund();});
      }
      membershipContext.run(pathname==='/feed.xml'||pathname==='/feed/weekly.xml'?{tier:'visitor'}:access,()=>dispatch(req,res));return;
    }catch(error){const e=error as {status?:number;code?:string;message?:string};res.writeHead(e.status??503,{'Content-Type':'application/problem+json','Cache-Control':'no-store'});res.end(JSON.stringify({status:e.status??503,code:e.code??'membership_unavailable',detail:e.status?e.message:'权益暂不可用'}));return;}
  }
  if((req.url??'').startsWith('/api/browser/'))req.url=req.url!.replace('/api/browser/','/api/v1/');
  dispatch(req,res);
});
function dispatch(req:http.IncomingMessage,res:http.ServerResponse){
  if ((req.url ?? '').split('?')[0] === '/_runtime/health') { runtimeHealthHandler(req, res); return; }
  if(adminStore)trackAnalyticsRequest(adminStore,req,res);
  const pathname = (req.url ?? '').split('?')[0] ?? '';
  if (pathname === '/api/pro/mcp') { void proMcpHandler(req, res); return; }
  if (pathname==='/api/payment/waffo/live/webhook'){void liveWebhook(req,res);return;}
  if (pathname.startsWith('/api/payment/waffo/')) {void waffoHandler(req,res);return;}
  if (pathname==='/api/payment/webhook') { void paymentWebhook(req,res);return;}
  if (pathname.startsWith('/api/pro/')) { void proHandler(req, res); return; }
  if (pathname.startsWith('/api/admin/')) { void adminHandler(req, res); return; }
  if (pathname.startsWith('/api/account/')) { void accountHandler(req, res); return; }
  if (pathname === '/_locale/country') { countryHandler(req, res); return; }
  if (pathname === '/api/mcp') {
    void mcpHandler(req, res);
    return;
  }
  if(site&&!pathname.startsWith('/api/')){void site.handle(req,res);return;}
  void restHandler(req, res);
}
const loop = logger ? monitorEventLoopDelay({ resolution: 20 }) : undefined;
loop?.enable();
const sample = () => {
  const memory = process.memoryUsage();
  logger?.emit({ kind: 'runtime.sample', releaseId, datasetVersion: holder.current?.version ?? null,
    rssBytes: memory.rss, heapUsedBytes: memory.heapUsed,
    eventLoopP99Ms: loop && loop.count ? loop.percentile(99) / 1e6 : 0,
    health: freshnessSummary(holder), cache: holder.cacheState, logger: logger.state });
  loop?.reset();
};
server.listen(PORT, HOST, () => {
  logger?.emit({ kind: 'runtime.started', releaseId, datasetVersion: holder.current?.version ?? null,
    ready: Boolean(holder.current) });
  sample();
});
const projectTimer=projects?setInterval(()=>{try{if(holder.current)if(projects!.refreshAll(holder.current).failed)logger?.emit({kind:'projects.refresh_failed'});}catch{logger?.emit({kind:'projects.refresh_failed'});}},300000):undefined;
projectTimer?.unref();
const sampleTimer = logger ? setInterval(sample, 60000) : undefined;
sampleTimer?.unref();
const timer = RELOAD_MS > 0 ? setInterval(() => { void reload(); }, RELOAD_MS) : undefined;
timer?.unref();
process.on('SIGHUP', () => { void reload(true); });

let stopping = false;
const shutdown = () => {
  if (stopping) return; stopping = true;
  logger?.emit({ kind: 'runtime.stopping', releaseId });
  if (timer) clearInterval(timer);
  if (sampleTimer) clearInterval(sampleTimer);
  if(projectTimer)clearInterval(projectTimer);
  const paymentDrained=stopPaymentSync?.(); loop?.disable(); holder.close();
  server.close(() => { void (async () => { await paymentDrained;accountStore?.close();siteRuntime?.uninstall();await siteStore?.close(); await logger?.close(); process.exit(0); })(); });
  setTimeout(() => process.exit(0), 3000).unref();
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
