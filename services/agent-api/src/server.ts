/**
 * server.ts：agent-api 启动入口（Task 03 M5）。
 *
 * 默认绑定 127.0.0.1（生产由反向代理做 TLS）；PORT 环境变量定端口。
 * PUBLIC_DATA_ROOT 指定数据根（测试注入临时目录）；RELOAD_INTERVAL_MS
 * 轮询 manifest 热重载（0=禁用），另支持 SIGHUP。
 */
import http from 'node:http';
import { performance, monitorEventLoopDelay } from 'node:perf_hooks';
import { JsonlLogger, instrumentRequest, freshnessSummary } from './observability.js';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatasetHolder } from './dataset.js';
import { createMcpHandler, DEFAULT_MCP_CONFIG } from './mcp.js';
import { createHandler, type ServerConfig } from './http.js';
import { countryHandler } from './country.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..', '..');

const PORT = parseInt(process.env.PORT ?? '8787', 10);
const HOST = process.env.HOST ?? '127.0.0.1';
const DATA_ROOT = process.env.PUBLIC_DATA_ROOT
  ?? path.join(repoRoot, 'data', 'public', 'v1');
const RELOAD_MS = parseInt(process.env.RELOAD_INTERVAL_MS ?? (process.env.MAAS_RELEASE_DIR ? '0' : '30000'), 10);
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
  maxRetainedVersions: parseInt(process.env.RETAINED_DATASET_MAX_VERSIONS ?? '2', 10),
  maxRetainedBytes: parseInt(process.env.RETAINED_DATASET_MAX_BYTES ?? String(128 * 1024 * 1024), 10),
});
const logger = process.env.MAAS_DIAGNOSTICS === '0' ? undefined : new JsonlLogger();
const releaseName = path.basename(process.env.MAAS_RELEASE_DIR ?? 'local');
const releaseId = /^rl_[a-f0-9]+_[a-f0-9]+$/.test(releaseName) ? releaseName : 'local';
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
  return result;
};
await reload();

// dispatcher：/api/mcp → MCP；其余 → REST（http.ts 行为不变）
const restHandler = instrumentRequest(createHandler(holder, config), holder, releaseId, logger?.emit);
const mcpHandler = instrumentRequest(createMcpHandler(holder, mcpConfig), holder, releaseId, logger?.emit);
const server = http.createServer((req, res) => {
  const pathname = (req.url ?? '').split('?')[0];
  if (pathname === '/_locale/country') { countryHandler(req, res); return; }
  if (pathname === '/api/mcp') {
    void mcpHandler(req, res);
    return;
  }
  void restHandler(req, res);
});
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
  loop?.disable(); holder.close();
  server.close(() => { void (async () => { await logger?.close(); process.exit(0); })(); });
  setTimeout(() => process.exit(0), 3000).unref();
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
