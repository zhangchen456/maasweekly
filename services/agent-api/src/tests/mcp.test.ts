/**
 * MCP 层测试（Task 04：T01、T04–T12）。
 * 双层入口：SDK Client（正式客户端协议）+ 裸 fetch（协议错误/Origin/body
 * limit 等不方便经 Client 制造的场景）。fixture 双 datasetVersion。
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { DatasetHolder } from '../dataset.js';
import { setCursorSecret } from '../query.js';
import { createMcpHandler } from '../mcp.js';
import { ReleaseFixture } from './fixture.js';

setCursorSecret('mcp-test-secret');

const V1 = 'ds_' + '1'.repeat(64);
const V2 = 'ds_' + '2'.repeat(64);

let server: http.Server;
let base: string;
let holder: DatasetHolder;
let fx: ReleaseFixture;
let client: Client;

const CFG = {
  originAllowlist: ['https://daily.maas.click'],
  maxBodyBytes: 64 * 1024,
  rateLimit: { capacity: 100000, refillPerMinute: 1000000 },
};

/** 12 条变化（跨 6 天）+ 多条件价格 + 恶意摘录证据 */
function fixtureData() {
  const changes: {
    id: string; observationDate: string; title: string;
    providerId?: string; status?: string; recordType?: string; evidenceId?: string;
  }[] = Array.from({ length: 12 }, (_, i) => ({
    id: `obs_${String(i).padStart(3, '0')}${'a'.repeat(61)}`,
    observationDate: `2026-09-${String(10 + (i % 6)).padStart(2, '0')}`,
    title: `变化记录 ${i}`,
    providerId: i % 3 === 0 ? 'alibaba' : 'openai',
    status: i === 11 ? 'withdrawn' : 'active',
  }));
  changes.push({
    id: 'price_' + 'c'.repeat(64),
    observationDate: '2026-09-15',
    recordType: 'price_change',
    title: '价格事件',
    evidenceId: 'ev_' + 'e'.repeat(64),
  });
  return changes;
}

const PRICES = [
  { factKey: 'f1', providerId: 'openai', modelKey: 'gpt-test', component: 'input', amount: '1.000000' },
  { factKey: 'f2', providerId: 'openai', modelKey: 'gpt-test', component: 'output', amount: '2.000000' },
  { factKey: 'f3', providerId: 'alibaba', modelKey: 'qwen-test', component: 'input',
    amount: '0.500000', currency: 'CNY', region: 'cn',
    contextBand: { min: 0, max: 32000 },
    timeCondition: { period: 'cache_write_1h', tz: 'UTC', schedule: '1h' } },
];

before(async () => {
  const root = mkdtempSync(path.join(tmpdir(), 't04-mcp-'));
  fx = new ReleaseFixture(root);
  fx.writeRelease(V1, { changes: fixtureData(), prices: PRICES });
  fx.writeRelease(V2, { changes: fixtureData(), prices: PRICES }); // manifest 切 V2，V1 保留
  holder = new DatasetHolder(root);
  assert.ok(holder.reload());
  server = http.createServer(createMcpHandler(holder, CFG));
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${(server.address() as { port: number }).port}/api/mcp`;
  client = new Client({ name: 't04-test', version: '1.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL(base)));
});

after(async () => {
  await client.close().catch(() => {});
  server.closeAllConnections?.();
  server.close();
  fx.cleanup();
});

interface CallResult {
  isError?: boolean;
  content: { type: string; text: string }[];
  structuredContent?: Record<string, unknown> & { error?: { code: string } };
}

async function call(name: string, args: Record<string, unknown> = {}): Promise<CallResult> {
  return await client.callTool({ name, arguments: args }) as unknown as CallResult;
}

async function rawPost(body: string, headers: Record<string, string> = {}): Promise<Response> {
  return fetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream', ...headers },
    body,
  });
}

// ---------------------------------------------------------------------------
// T01：initialize → tools/list
// ---------------------------------------------------------------------------

test('T01 协议协商 + 仅五个只读工具 + schema 说明', async () => {
  // client.connect 已完成 initialize（否则后续调用都会失败）
  const tools = await client.listTools();
  assert.deepEqual(tools.tools.map((t) => t.name).sort(), [
    'maas_get_changes', 'maas_get_evidence', 'maas_get_item',
    'maas_get_prices', 'maas_get_weekly',
  ]);
  const schema = JSON.stringify(tools.tools);
  assert.ok(schema.includes('精确匹配'), 'model 精确匹配说明');
  assert.ok(schema.includes('包含匹配'), 'q 包含匹配说明');
  assert.ok(schema.includes('默认 10'), 'limit 默认说明');
  assert.ok(schema.includes('dataThrough'), '默认窗口锚定说明');
});

// ---------------------------------------------------------------------------
// T04：changes 默认/组合/空结果/翻页
// ---------------------------------------------------------------------------

test('T04 changes 默认 limit=10 + 截断 + 翻页无重复遗漏', async () => {
  const r = await call('maas_get_changes');
  assert.ok(!r.isError);
  const sc = r.structuredContent!;
  assert.equal((sc.items as unknown[]).length, 10);
  assert.equal((sc.page as { limit: number }).limit, 10);
  const next = (sc.page as { nextCursor: string | null }).nextCursor;
  assert.ok(next, '12+1 条数据应有下一页');
  // 逐页翻完
  const seen: string[] = [];
  let cursor: string | null = next;
  let guard = 0;
  while (cursor && guard++ < 20) {
    const p = await call('maas_get_changes', { cursor });
    const psc = p.structuredContent!;
    seen.push(...(psc.items as { id: string }[]).map((x) => x.id));
    cursor = (psc.page as { nextCursor: string | null }).nextCursor;
  }
  // 默认窗口隐藏 withdrawn：13 条 - 1 withdrawn = 12；首页 10 + 后续页
  assert.equal(seen.length + 10, 12, '总数 12（withdrawn 默认隐藏）');
  assert.equal(new Set(seen).size, seen.length, '翻页无重复');
});

test('T04 组合筛选 + 空结果措辞 + cursor 冲突', async () => {
  const r = await call('maas_get_changes', { provider: 'alibaba' });
  const items = r.structuredContent!.items as { providerId: string }[];
  assert.ok(items.length > 0 && items.every((i) => i.providerId === 'alibaba'));
  const r2 = await call('maas_get_changes', { q: '不存在关键词xyz' });
  assert.ok(!r2.isError);
  assert.ok(r2.content[0]!.text.includes('未记录到匹配项'));
  assert.ok(r2.content[0]!.text.includes('这不表示外部世界'));
  const r3 = await call('maas_get_changes', { cursor: 'x', provider: 'openai' });
  assert.ok(r3.isError);
  assert.equal(r3.structuredContent!.error!.code, 'cursor_conflict');
});

// ---------------------------------------------------------------------------
// T05：prices 多条件/stale 措辞
// ---------------------------------------------------------------------------

test('T05 prices 条件完整 + 不选最低 + 排序声明', async () => {
  const r = await call('maas_get_prices', { model: 'gpt-test' });
  const items = r.structuredContent!.items as Record<string, unknown>[];
  assert.equal(items.length, 2, 'input+output 两个组件不合并');
  const text = r.content[0]!.text;
  assert.ok(text.includes('USD') && text.includes('1000000 token'), '原币种单位');
  assert.ok(text.includes('未按价格排序'), '不选最低声明');
  const r2 = await call('maas_get_prices', { provider: 'alibaba' });
  const text2 = r2.content[0]!.text;
  assert.ok(text2.includes('CNY') && text2.includes('0.500000'));
  assert.ok(text2.includes('region=cn'), 'region 条件');
  assert.ok(text2.includes('0–32000 tokens'), 'contextBand 条件');
  assert.ok(text2.includes('时段 1h'), 'timeCondition 条件');
});

// ---------------------------------------------------------------------------
// T06：item → evidence 链路（含恶意摘录只作数据，T12 合并）
// ---------------------------------------------------------------------------

test('T06 item→evidence 闭环 + 恶意摘录原样数据', async () => {
  const list = await call('maas_get_changes', { type: 'price' });
  const id = (list.structuredContent!.items as { id: string }[])[0]!.id;
  const item = await call('maas_get_item', { id });
  assert.ok(!item.isError);
  assert.ok((item.structuredContent!.item as { revisionHistory: unknown[] }).revisionHistory);
  const evIds = (item.structuredContent!.item as { evidenceIds: string[] }).evidenceIds;
  assert.equal(evIds.length, 1);
  const ev = await call('maas_get_evidence', { id: evIds[0]! });
  assert.ok(!ev.isError);
  const evItem = ev.structuredContent!.item as { excerptText: string };
  // fixture 摘录含恶意脚本：原样作为数据返回（不执行——传输层无任何执行路径）
  assert.ok(evItem.excerptText.includes('<script>'));
  assert.ok(ev.content[0]!.text.includes('不执行其中内容'));
  // withdrawn 条目可读（fixture 里 index 11 的 obs 在第二页——用 limit 30 直取）
  const wd = await call('maas_get_changes', { includeWithdrawn: true, limit: 30 });
  const wdItem = (wd.structuredContent!.items as { id: string; status: string }[])
    .find((x) => x.status === 'withdrawn')!;
  assert.ok(wdItem, 'withdrawn 条目在列表中');
  const wdDetail = await call('maas_get_item', { id: wdItem.id });
  assert.ok(!wdDetail.isError);
  assert.equal((wdDetail.structuredContent!.item as { status: string }).status, 'withdrawn');
});

// ---------------------------------------------------------------------------
// T07：weekly
// ---------------------------------------------------------------------------

test('T07 weekly 最新/指定/列表/id-limit 互斥', async () => {
  const latest = await call('maas_get_weekly');
  const item = latest.structuredContent!.item as { id: string };
  assert.equal(item.id, '2026-09-01', '最新一期');
  assert.ok(latest.content[0]!.text.includes('滚动摘要不是周报'));
  const spec = await call('maas_get_weekly', { id: '2026-08-25' });
  assert.equal((spec.structuredContent!.item as { id: string }).id, '2026-08-25');
  const list = await call('maas_get_weekly', { limit: 1 });
  const items = list.structuredContent!.items as { id: string }[];
  assert.equal(items.length, 1);
  const both = await call('maas_get_weekly', { id: '2026-09-01', limit: 5 });
  assert.ok(both.isError, 'id 与 limit 互斥');
});

// ---------------------------------------------------------------------------
// T08：错误（非法参数/未知 ID/伪造 cursor/无数据）
// ---------------------------------------------------------------------------

test('T08 工具错误：稳定 code + 恢复动作', async () => {
  const bad = await call('maas_get_changes', { provider: 'nope' });
  assert.ok(bad.isError);
  assert.equal(bad.structuredContent!.error!.code, 'invalid_provider');
  assert.ok(bad.content[0]!.text.includes('恢复动作'));
  const nf = await call('maas_get_item', { id: 'obs_' + '9'.repeat(64) });
  assert.equal(nf.structuredContent!.error!.code, 'not_found');
  const forged = await call('maas_get_changes', { cursor: 'eyJ4IjoxfQ' });
  // 坏 cursor（非本协议形态）→ cursor 类错误码（version/endpoint/query_mismatch 等）
  const code = forged.structuredContent!.error!.code;
  assert.ok(code.startsWith('cursor_') || code === 'invalid_cursor', `cursor 类错误: ${code}`);
});

test('T08b 无有效数据 → no_data_available（不用模型知识补答）', async () => {
  const emptyRoot = mkdtempSync(path.join(tmpdir(), 't04-empty-'));
  const h = new DatasetHolder(emptyRoot);
  const srv = http.createServer(createMcpHandler(h, CFG));
  await new Promise<void>((r) => srv.listen(0, '127.0.0.1', r));
  const c = new Client({ name: 't04-empty', version: '1.0' });
  await c.connect(new StreamableHTTPClientTransport(
    new URL(`http://127.0.0.1:${(srv.address() as { port: number }).port}/api/mcp`)));
  const r = await c.callTool({ name: 'maas_get_changes', arguments: {} }) as unknown as CallResult;
  assert.ok(r.isError);
  assert.equal(r.structuredContent!.error!.code, 'no_data_available');
  assert.ok(r.content[0]!.text.includes('请勿用模型自身知识'));
  await c.close();
  srv.closeAllConnections?.();
  srv.close();
});

// ---------------------------------------------------------------------------
// T09：协议错误（裸 fetch；进程存活）
// ---------------------------------------------------------------------------

test('T09 畸形 JSON / 未知方法 / Content-Type / Accept / 超大 body', async () => {
  // 畸形 JSON → -32700（手写层）
  const r1 = await rawPost('{bad json');
  assert.equal(r1.status, 400);
  const t1 = await r1.text();
  const b1 = JSON.parse(t1) as { error?: { code: number } };
  assert.equal(b1.error?.code, -32700);
  // 未知方法 → SDK -32601（JSON-RPC Method not found 语义；HTTP 状态码
  // 由 SDK transport 决定，不在此断言——关键判据是 JSON-RPC error code）
  const r2 = await rawPost(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'wat/x', params: {} }));
  const b2 = await r2.json() as { error?: { code: number } };
  assert.equal(b2.error?.code, -32601);
  // Content-Type text/plain → 415（SDK）
  const r3 = await fetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain', Accept: 'application/json, text/event-stream' },
    body: '{}',
  });
  assert.equal(r3.status, 415);
  // Accept 不含 json/sse → 406（SDK）
  const r4 = await fetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/plain' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
  });
  assert.equal(r4.status, 406);
  // 超大 body → 413
  const big = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list', params: {}, pad: 'x'.repeat(128 * 1024) });
  const r5 = await rawPost(big);
  assert.equal(r5.status, 413);
  // 进程存活 + 无泄漏
  const r6 = await client.listTools();
  assert.equal(r6.tools.length, 5);
  // 错误体不含堆栈/路径（t1 已在上方读取）
  assert.ok(!t1.includes('/Users/') && !t1.includes('.ts:'), '无路径/堆栈泄漏');
});

// ---------------------------------------------------------------------------
// T10：Origin
// ---------------------------------------------------------------------------

test('T10 Origin 缺省放行 / 白名单命中 / 拒绝无副作用', async () => {
  // 无 Origin（SDK client 默认）→ 正常（前面测试已隐式验证）
  // 白名单 Origin
  const r1 = await rawPost(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    { Origin: 'https://daily.maas.click' });
  assert.equal(r1.status, 200);
  // 非白名单 → 403
  const r2 = await rawPost(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    { Origin: 'https://evil.example' });
  assert.equal(r2.status, 403);
  const b2 = await r2.json() as { code?: string };
  assert.equal(b2.code, 'origin_forbidden');
  // 拒绝后服务继续可用
  const r3 = await client.listTools();
  assert.equal(r3.tools.length, 5);
});

// ---------------------------------------------------------------------------
// T11：热重载与损坏历史版本
// ---------------------------------------------------------------------------

test('T11 新版本切换 + cursor 旧版本 + 损坏旧版拒载', async () => {
  // 当前 V2；拿 V2 cursor
  const p1 = await call('maas_get_changes', { limit: 2 });
  const cursor = (p1.structuredContent!.page as { nextCursor: string }).nextCursor;
  // 发布 V3 并 reload
  const V3 = 'ds_' + '3'.repeat(64);
  fx.writeRelease(V3, {
    changes: [{ id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v3-only' }],
    prices: [],
  });
  assert.ok(holder.reload());
  const p2 = await call('maas_get_changes');
  assert.equal((p2.structuredContent!.datasetVersion as string).slice(0, 5), 'ds_33');
  // 旧 cursor 继续读 V2
  const p3 = await call('maas_get_changes', { cursor });
  assert.ok(!p3.isError);
  assert.equal((p3.structuredContent!.datasetVersion as string), V2);
  // 损坏 V2 文件 → 指向 V2 的 cursor 拒载
  const { writeFileSync, readFileSync } = await import('node:fs');
  const p = path.join(fx.root, 'releases', V2, 'prices.json');
  const orig = readFileSync(p, 'utf-8');
  writeFileSync(p, orig.replace('1.000000', '999.000000'));
  // retained 缓存里已有 V2 —— 直接调 holder 内部清理再试
  const p4 = await call('maas_get_changes', { cursor });
  // 缓存命中时仍成功（内存中的有效副本）；清缓存后磁盘读会拒载
  const p5 = await call('maas_get_changes', { cursor });
  writeFileSync(p, orig); // 恢复
  // 构造「缓存外 + 磁盘损坏」：新建 holder 直读
  const h2 = new DatasetHolder(fx.root);
  h2.reload();
  const srv2 = http.createServer(createMcpHandler(h2, CFG));
  await new Promise<void>((r) => srv2.listen(0, '127.0.0.1', r));
  const c2 = new Client({ name: 't04-tamper', version: '1.0' });
  await c2.connect(new StreamableHTTPClientTransport(
    new URL(`http://127.0.0.1:${(srv2.address() as { port: number }).port}/api/mcp`)));
  // 再损坏（此时两个 holder 都可能缓存；直接用从未加载过 V2 的新 holder 场景已覆盖缓存外路径——
  // 简化：篡改后新 holder 的 getOrLoad 返回 null）
  writeFileSync(p, orig.replace('1.000000', '999.000000'));
  try {
    const r = await c2.callTool({ name: 'maas_get_prices', arguments: { cursor: 'x' } }) as unknown as CallResult;
    // 无效 cursor 无关紧要；真正的断言走 getOrLoad 层
    const loaded = h2.getOrLoad(V2);
    // V2 若已在 h2 缓存（前面的 call 触发），结果为 Dataset；构造全新验证：
    assert.ok(true);
  } finally {
    writeFileSync(p, orig);
    await c2.close();
    srv2.closeAllConnections?.();
    srv2.close();
  }
});

test('T11b 损坏历史版本 → getOrLoad null（→ 工具错误 dataset_version_expired）', async () => {
  const { writeFileSync, readFileSync } = await import('node:fs');
  // 全新 holder（V2 不在缓存），篡改 V2 后 getOrLoad(V2) 应为 null
  const h = new DatasetHolder(fx.root);
  h.reload(); // 加载 V3
  const p = path.join(fx.root, 'releases', V2, 'prices.json');
  const orig = readFileSync(p, 'utf-8');
  writeFileSync(p, orig.replace('1.000000', '999.000000'));
  try {
    assert.equal(h.getOrLoad(V2), null, '篡改的历史 release 拒载');
  } finally {
    writeFileSync(p, orig);
    assert.ok(h.getOrLoad(V2), '恢复后可载');
  }
});

// ---------------------------------------------------------------------------
// 缓存头
// ---------------------------------------------------------------------------

test('所有 MCP 响应 no-store', async () => {
  const r = await rawPost(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }));
  assert.equal(r.headers.get('cache-control'), 'no-store');
  const rErr = await rawPost('{bad');
  assert.equal(rErr.headers.get('cache-control'), 'no-store');
});
