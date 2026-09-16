/**
 * MCP 真实数据测试（Task 04：T02/T03）。
 * 真实 data/public/v1 release；同一 holder 同时挂 REST 与 MCP——
 * 五工具真实查询（T02）+ REST/MCP 同条件 deepEqual（T03）。
 * 运行：npm run test:mcp:real（需先 export-public-data.py）
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { DatasetHolder } from '../dataset.js';
import { setCursorSecret } from '../query.js';
import { createHandler } from '../http.js';
import { createMcpHandler } from '../mcp.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');
const DATA_ROOT = process.env.PUBLIC_DATA_ROOT
  ?? path.join(repoRoot, 'data', 'public', 'v1');

setCursorSecret('mcp-real-test');

let server: http.Server;
let restBase: string;
let mcpBase: string;
let client: Client;

before(async () => {
  const holder = new DatasetHolder(DATA_ROOT);
  assert.ok(holder.reload(), `真实 release 加载失败: ${holder.lastReloadError}`);
  const cfg = {
    originAllowlist: ['https://daily.maas.click'],
    maxBodyBytes: 256 * 1024,
    rateLimit: { capacity: 100000, refillPerMinute: 1000000 },
  };
  const rest = createHandler(holder, cfg);
  const mcp = createMcpHandler(holder, cfg);
  server = http.createServer((req, res) => {
    if ((req.url ?? '').split('?')[0] === '/api/mcp') {
      void mcp(req, res);
      return;
    }
    void rest(req, res);
  });
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
  const port = (server.address() as { port: number }).port;
  restBase = `http://127.0.0.1:${port}/api/v1`;
  mcpBase = `http://127.0.0.1:${port}/api/mcp`;
  client = new Client({ name: 't04-real', version: '1.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL(mcpBase)));
});

after(async () => {
  await client.close().catch(() => {});
  server.closeAllConnections?.();
  server.close();
});

interface CallResult {
  isError?: boolean;
  content: { type: string; text: string }[];
  structuredContent?: Record<string, unknown> & { error?: { code: string } };
}

async function call(name: string, args: Record<string, unknown> = {}): Promise<CallResult> {
  return await client.callTool({ name, arguments: args }) as unknown as CallResult;
}

const norm = (x: unknown): unknown => JSON.parse(JSON.stringify(x));

// ---------------------------------------------------------------------------
// T02：五工具真实查询；文本与 structuredContent 一致
// ---------------------------------------------------------------------------

test('T02 maas_get_changes 真实数据 + 文本/结构一致', async () => {
  const r = await call('maas_get_changes');
  assert.ok(!r.isError);
  const sc = r.structuredContent!;
  assert.ok((sc.datasetVersion as string).startsWith('ds_'));
  const items = sc.items as Record<string, unknown>[];
  assert.ok(items.length > 0 && items.length <= 10);
  // 文本含版本（前 8 hex）、数据截至、条目 id
  const text = r.content[0]!.text;
  assert.ok(text.includes((sc.datasetVersion as string).slice(3, 11)), '文本含版本片段');
  assert.ok(text.includes(String(sc.dataThrough)), '文本含 dataThrough');
  assert.ok(text.includes((items[0]!.id as string).slice(0, 12)), '文本含条目 id');
});

test('T02 maas_get_prices 真实数据（金额/币种/单位/证据）', async () => {
  const r = await call('maas_get_prices', { provider: 'openai', limit: 5 });
  assert.ok(!r.isError);
  const items = r.structuredContent!.items as Record<string, unknown>[];
  assert.ok(items.length > 0);
  for (const p of items) {
    assert.equal(typeof p.amount, 'string', '金额为字符串');
    assert.ok(['USD', 'CNY'].includes(p.currency as string));
    assert.ok(typeof p.unitQuantity === 'number');
    assert.ok(typeof p.observedAt === 'string');
  }
});

test('T02 maas_get_item / evidence / weekly 真实链路（含文本元数据，复验 P1-2）', async () => {
  const list = await call('maas_get_changes', { type: 'price', limit: 1 });
  const id = (list.structuredContent!.items as { id: string }[])[0]!.id;
  const item = await call('maas_get_item', { id });
  assert.ok(!item.isError);
  const evIds = (item.structuredContent!.item as { evidenceIds: string[] }).evidenceIds;
  assert.ok(evIds.length > 0);
  const ev = await call('maas_get_evidence', { id: evIds[0]! });
  assert.ok(!ev.isError);
  assert.ok(((ev.structuredContent!.item as { excerptText: string }).excerptText).length > 0);
  const wk = await call('maas_get_weekly');
  assert.ok(!wk.isError);
  const wItem = wk.structuredContent!.item as { id: string };
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(wItem.id), '正式周报 id 为日期');

  // P1-2（第二轮）：三个工具的文本必须含数据版本 + 数据截至 + 实际覆盖
  const scItem = item.structuredContent!;
  const itemText = item.content[0]!.text;
  assert.ok(itemText.includes(String(scItem.datasetVersion).slice(3, 11)), 'item 文本含版本片段');
  assert.ok(itemText.includes(String(scItem.dataThrough)), 'item 文本含 dataThrough');
  assert.ok(itemText.includes('不代表实时'), 'item 文本含快照声明');
  assert.ok(itemText.includes('实际覆盖:'), 'item 文本含实际覆盖');
  const scEv = ev.structuredContent!;
  const evText = ev.content[0]!.text;
  assert.ok(evText.includes(String(scEv.datasetVersion).slice(3, 11)), 'evidence 文本含版本片段');
  assert.ok(evText.includes(String(scEv.dataThrough)), 'evidence 文本含 dataThrough');
  assert.ok(evText.includes('实际覆盖:'), 'evidence 文本含实际覆盖');
  const scWk = wk.structuredContent!;
  const wkText = wk.content[0]!.text;
  assert.ok(wkText.includes(String(scWk.datasetVersion).slice(3, 11)), 'weekly 文本含版本片段');
  assert.ok(wkText.includes(String(scWk.dataThrough)), 'weekly 文本含 dataThrough');
  assert.ok(wkText.includes('实际覆盖:'), 'weekly 文本含实际覆盖');
});

test('T02b P1-2 第二轮：五工具及 weekly 三种模式逐一含版本/截至/覆盖', async () => {
  const list = await call('maas_get_changes', { type: 'price', limit: 1 });
  const id = (list.structuredContent!.items as { id: string }[])[0]!.id;
  const evId = ((await call('maas_get_item', { id }))
    .structuredContent!.item as { evidenceIds: string[] }).evidenceIds[0]!;
  const cases: [string, Record<string, unknown>][] = [
    ['maas_get_changes', {}],
    ['maas_get_prices', { provider: 'openai', limit: 1 }],
    ['maas_get_item', { id }],
    ['maas_get_evidence', { id: evId }],
    ['maas_get_weekly', {}],                       // 默认最新
    ['maas_get_weekly', { id: '2026-09-01' }],     // 指定
    ['maas_get_weekly', { limit: 2 }],             // 列表
  ];
  for (const [name, args] of cases) {
    const r = await call(name, args);
    assert.ok(!r.isError, `${name} ${JSON.stringify(args)} 失败`);
    const text = r.content[0]!.text;
    const sc = r.structuredContent!;
    assert.ok(text.includes('数据版本:'), `${name} ${JSON.stringify(args)} 缺数据版本`);
    assert.ok(text.includes(String(sc.dataThrough)), `${name} ${JSON.stringify(args)} 缺数据截至`);
    assert.ok(text.includes('实际覆盖:'), `${name} ${JSON.stringify(args)} 缺实际覆盖`);
    assert.ok(text.includes('不代表实时'), `${name} ${JSON.stringify(args)} 缺快照声明`);
  }
});

// ---------------------------------------------------------------------------
// T03：MCP 与 REST 同条件完全一致
// ---------------------------------------------------------------------------

test('T03 changes（同条件）REST ≡ MCP', async () => {
  // 显式传同 limit（REST 默认 20 / MCP 默认 10 是合同差异，非不一致）。
  // MCP 入参 limit 是 number（zod），from/URLSearchParams 值是 string——手工构造。
  const cases: [string, Record<string, unknown>][] = [
    ['limit=10', { limit: 10 }],
    ['limit=10&provider=openai&type=price', { limit: 10, provider: 'openai', type: 'price' }],
    ['limit=10&from=2026-09-14&to=2026-09-17', { limit: 10, from: '2026-09-14', to: '2026-09-17' }],
  ];
  for (const [qs, args] of cases) {
    const rest = await (await fetch(`${restBase}/changes?${qs}`)).json() as Record<string, unknown>;
    const mcp = await call('maas_get_changes', args);
    assert.ok(!mcp.isError, `MCP 失败: ${JSON.stringify(mcp.structuredContent?.error)}`);
    assert.deepEqual(norm(mcp.structuredContent), norm(rest),
      `changes ${qs} REST/MCP 不一致`);
  }
});

test('T03 prices（model 精确 + q 包含）REST ≡ MCP', async () => {
  // 取真实 model 名
  const sample = await call('maas_get_prices', { limit: 1 });
  const modelKey = (sample.structuredContent!.items as { modelKey: string }[])[0]!.modelKey;
  const rest = await (await fetch(`${restBase}/prices?model=${encodeURIComponent(modelKey)}&limit=10`)).json() as Record<string, unknown>;
  const mcp = await call('maas_get_prices', { model: modelKey, limit: 10 });
  assert.deepEqual(norm(mcp.structuredContent), norm(rest), 'prices model 精确不一致');
  // q 包含
  const frag = modelKey.slice(0, 4);
  const restQ = await (await fetch(`${restBase}/prices?q=${encodeURIComponent(frag)}&limit=10`)).json() as Record<string, unknown>;
  const mcpQ = await call('maas_get_prices', { q: frag, limit: 10 });
  assert.deepEqual(norm(mcpQ.structuredContent), norm(restQ), 'prices q 包含不一致');
});

test('T03 weekly REST ≡ MCP', async () => {
  const rest = await (await fetch(`${restBase}/weekly?limit=3`)).json() as Record<string, unknown>;
  const mcp = await call('maas_get_weekly', { limit: 3 });
  assert.deepEqual(norm(mcp.structuredContent), norm(rest), 'weekly 不一致');
});

test('T03 翻页一致性（MCP 翻页与 REST 全量）', async () => {
  // REST limit=100 全量（REST 上限 100）
  const rest = await (await fetch(`${restBase}/changes?limit=100`)).json() as { items: { id: string }[] };
  const restIds = (rest.items as { id: string }[]).map((x) => x.id);
  // MCP limit=30 逐页（上限 30）
  const mcpIds: string[] = [];
  let cursor: string | undefined;
  let guard = 0;
  while (guard++ < 10) {
    const page = await call('maas_get_changes', cursor ? { cursor } : { limit: 30 });
    const sc = page.structuredContent!;
    mcpIds.push(...(sc.items as { id: string }[]).map((x) => x.id));
    cursor = (sc.page as { nextCursor: string | null }).nextCursor ?? undefined;
    if (!cursor) break;
  }
  // REST 100 条与 MCP 前若干页（30 的整数倍窗口内）比较：MCP 页数 ≥ 3 时
  // 前 90 条应与 REST 前 90 条一致
  assert.equal(mcpIds.length >= 90 || mcpIds.length === restIds.length, true,
    `MCP 总数 ${mcpIds.length} vs REST ${restIds.length}`);
  const n = Math.min(mcpIds.length, 90);
  assert.deepEqual(mcpIds.slice(0, n), restIds.slice(0, n), '翻页顺序与 REST 一致');
  assert.equal(new Set(mcpIds).size, mcpIds.length, 'MCP 翻页无重复');
});
