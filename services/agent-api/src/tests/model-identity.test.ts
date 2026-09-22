/**
 * Task 07 T07-3：modelId/familyId 查询契约测试（T08–T17 核心）。
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Dataset, DatasetError, DatasetHolder } from '../dataset.js';
import { createHandler } from '../http.js';
import { createMcpHandler } from '../mcp.js';
import { ReleaseFixture } from './fixture.js';
import { runListQuery, normalizeQuery, encodeCursor, setCursorSecret } from '../query.js';
import type { ModelIdentityCatalog } from '../dataset.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

setCursorSecret('t07-identity-mcp-secret');

const zeroModel = 'alibaba:zero-model';
const zeroFamily = 'alibaba:zero-family';
const catalog: ModelIdentityCatalog = {
  models: [
    { modelId: 'alibaba:qwen-coder-plus', modelName: 'Qwen Coder Plus', familyId: 'alibaba:qwen-coder', familyName: 'Qwen Coder' },
    { modelId: 'alibaba:qwen-coder-turbo', modelName: 'Qwen Coder Turbo', familyId: 'alibaba:qwen-coder', familyName: 'Qwen Coder' },
    { modelId: 'anthropic:claude-sonnet-4.5', modelName: 'Claude Sonnet 4.5' },
    { modelId: zeroModel, modelName: 'Zero Model', familyId: zeroFamily, familyName: 'Zero Family' },
  ],
  families: [
    { familyId: 'alibaba:qwen-coder', familyName: 'Qwen Coder' },
    { familyId: zeroFamily, familyName: 'Zero Family' },
  ],
};
let fx: ReleaseFixture;

let server: http.Server;
let base: string;

before(async () => {
  const root = mkdtempSync(path.join(tmpdir(), 't07-identity-'));
  fx = new ReleaseFixture(root);
  fx.writeRelease('ds_' + 'a'.repeat(64), {
    modelIdentities: catalog,
    prices: [
      { factKey: 'fk1', providerId: 'alibaba', modelKey: 'qwen-coder-plus',
        modelId: 'alibaba:qwen-coder-plus', modelName: 'Qwen Coder Plus',
        familyId: 'alibaba:qwen-coder', familyName: 'Qwen Coder', component: 'input' },
      { factKey: 'fk2', providerId: 'alibaba', modelKey: 'qwen-coder-turbo',
        modelId: 'alibaba:qwen-coder-turbo', modelName: 'Qwen Coder Turbo',
        familyId: 'alibaba:qwen-coder', familyName: 'Qwen Coder', component: 'input' },
      { factKey: 'fk3', providerId: 'anthropic', modelKey: 'claude-sonnet-4.5',
        modelId: 'anthropic:claude-sonnet-4.5', modelName: 'Claude Sonnet 4.5',
        familyId: 'anthropic:claude-sonnet', familyName: 'Claude Sonnet', component: 'input' },
      { factKey: 'fk4', providerId: 'alibaba', modelKey: 'qwen-flash-us',
        component: 'input' },
    ],
    changes: [
      { id: 'price_' + '1'.repeat(64), observationDate: '2026-09-01', providerId: 'alibaba',
        recordType: 'price_change', model: 'qwen-coder-plus', modelId: 'alibaba:qwen-coder-plus', status: 'active',
      },
    ],
  });
  const holder = new DatasetHolder(root);
  assert.equal(holder.reload(), true, holder.lastReloadError ?? 'reload failed');
  const ds = holder.current!;
  for (const entity of [...ds.changes, ...ds.prices, ...ds.itemsById.values()]) {
    assert.notEqual(entity.modelId, zeroModel);
    assert.notEqual(entity.familyId, zeroFamily);
  }
  server = http.createServer(createHandler(holder, {
    rateLimit: { capacity: 100, refillPerMinute: 1000 },
  }));
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', () => r()));
  base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
});

after(async () => {
  if (server) await new Promise<void>((resolve) => server.close(() => resolve()));
  fx?.cleanup();
});

test('T08: modelId 精确过滤', async () => {
  const res = await fetch(`${base}/api/v1/prices?modelId=alibaba:qwen-coder-plus`);
  assert.equal(res.status, 200);
  const body = await res.json() as unknown as Record<string, any>;
  assert.equal(body.items.length, 1);
  assert.equal(body.items[0].modelId, 'alibaba:qwen-coder-plus');
});

test('T09: familyId 返回明确成员集合', async () => {
  const res = await fetch(`${base}/api/v1/prices?familyId=alibaba:qwen-coder`);
  assert.equal(res.status, 200);
  const body = await res.json() as unknown as Record<string, any>;
  const mids = body.items.map((x: { modelId: string }) => x.modelId).sort();
  assert.deepEqual(mids, ['alibaba:qwen-coder-plus', 'alibaba:qwen-coder-turbo']);
});

test('T10: model 与 modelId 语义不同', async () => {
  // model=modelKey 原始串
  const r1 = await fetch(`${base}/api/v1/prices?model=qwen-coder-plus`);
  const b1 = await r1.json() as { items: unknown[] };
  assert.equal(b1.items.length, 1);
  // modelId=identity（同串形态但语义独立——unresolved 的 qwen-flash-us 用 model 查得到）
  const r2 = await fetch(`${base}/api/v1/prices?model=qwen-flash-us`);
  const b2 = await r2.json() as { items: unknown[] };
  assert.equal(b2.items.length, 1);
  // 该原始串未在 catalog 注册为 modelId，必须 400。
  const r3 = await fetch(`${base}/api/v1/prices?modelId=alibaba:qwen-flash-us`);
  assert.equal(r3.status, 400);
  assert.equal((await r3.json() as { code: string }).code, 'invalid_model_id');
});

test('T11: unknown modelId → 400', async () => {
  const res = await fetch(`${base}/api/v1/prices?modelId=invalid-format`);
  assert.equal(res.status, 400);
  const body = await res.json() as { code: string };
  assert.equal(body.code, 'invalid_model_id');
});

test('T12: unknown familyId → 400', async () => {
  const res = await fetch(`${base}/api/v1/prices?familyId=bad format`);
  assert.equal(res.status, 400);
  const body = await res.json() as { code: string };
  assert.equal(body.code, 'invalid_family_id');
});

test('T23: 无 modelId 客户端不回归（旧字段照常）', async () => {
  const res = await fetch(`${base}/api/v1/prices?provider=alibaba&limit=10`);
  assert.equal(res.status, 200);
  const body = await res.json() as { items: { modelKey: string }[] };
  assert.ok(body.items.length >= 3);
  assert.ok(body.items.every((x) => typeof x.modelKey === 'string'));
});

test('T11a: malformed modelId → 400', async () => {
  const res = await fetch(`${base}/api/v1/prices?modelId=invalid-format`);
  assert.equal(res.status, 400);
});

test('T11b: well-formed unknown modelId → 400', async () => {
  // 格式合法但 registry 中不存在的 modelId → 400（不返回 200 empty）
  const res = await fetch(`${base}/api/v1/prices?modelId=alibaba:ghost-model`);
  assert.equal(res.status, 400);
  const body = await res.json() as { code: string };
  assert.equal(body.code, 'invalid_model_id');
});

test('T11c: known modelId but no records → 200 empty', async () => {
  // registry 中存在但当前 dataset 无记录——合法 200 empty
  // before 已断言该 identity 在 changes/prices/items 三者中均不存在。
  const res = await fetch(`${base}/api/v1/prices?modelId=${zeroModel}`);
  assert.equal(res.status, 200);
  const body = await res.json() as { items: unknown[] };
  assert.equal(body.items.length, 0);
});

test('T12a: malformed familyId → 400', async () => {
  const res = await fetch(`${base}/api/v1/prices?familyId=bad-format`);
  assert.equal(res.status, 400);
});

test('T12b: well-formed unknown familyId → 400', async () => {
  const res = await fetch(`${base}/api/v1/prices?familyId=alibaba:ghost-family`);
  assert.equal(res.status, 400);
  const body = await res.json() as { code: string };
  assert.equal(body.code, 'invalid_family_id');
});

test('T12c: known familyId but no records → 200 empty', async () => {
  const res = await fetch(`${base}/api/v1/prices?familyId=${zeroFamily}`);
  assert.equal(res.status, 200);
  assert.deepEqual((await res.json() as { items: unknown[] }).items, []);
});

test('T11d: changes endpoint known-but-zero-record → 200 empty', async () => {
  // catalog-only identity，整个 dataset 无记录。
  const res = await fetch(`${base}/api/v1/changes?modelId=${zeroModel}`);
  assert.equal(res.status, 200);
  const body = await res.json() as { items: unknown[] };
  assert.equal(body.items.length, 0);
});

test('T11e: changes endpoint modelId 正向过滤生效（顶层 modelId，非 price.modelId）', async () => {
  // before 的 change（09-01，modelId=alibaba:qwen-coder-plus）在默认窗口外，
  // 用显式窗口包含它，验证 changes endpoint 顶层 modelId 过滤真实命中。
  const res = await fetch(`${base}/api/v1/changes?modelId=alibaba:qwen-coder-plus&from=2026-09-01&to=2026-09-02`);
  assert.equal(res.status, 200);
  const body = await res.json() as { items: { modelId?: string }[] };
  assert.equal(body.items.length, 1);
  assert.equal(body.items[0]!.modelId, 'alibaba:qwen-coder-plus');
  // 反向：用不匹配的 modelId 查同一窗口，应 200 empty（非零记录 identity）
  const res2 = await fetch(`${base}/api/v1/changes?modelId=alibaba:qwen-coder-turbo&from=2026-09-01&to=2026-09-02`);
  assert.equal(res2.status, 200);
  assert.deepEqual((await res2.json() as { items: unknown[] }).items, []);
});

test('T12d: changes endpoint known familyId → 200', async () => {
  const res = await fetch(`${base}/api/v1/changes?familyId=${zeroFamily}`);
  assert.equal(res.status, 200);
  assert.deepEqual((await res.json() as { items: unknown[] }).items, []);
});

const oldVersion = 'ds_' + 'b'.repeat(64);
const newVersion = 'ds_' + 'c'.repeat(64);
const historyPrices = [1, 2].map((n) => ({
  factKey: `history-${n}`, providerId: 'alibaba', modelKey: `history-${n}`,
  modelId: zeroModel, familyId: zeroFamily, familyName: 'Zero Family', component: 'input',
}));

test('T13: old cursor 从磁盘加载历史 catalog，current 删除 identity 不影响续页', () => {
  const fx = new ReleaseFixture(mkdtempSync(path.join(tmpdir(), 't07-history-')));
  try {
    fx.writeRelease(oldVersion, { modelIdentities: catalog, prices: historyPrices });
    const initial = new DatasetHolder(fx.root);
    assert.equal(initial.reload(), true);
    for (const [key, value] of [['modelId', zeroModel], ['familyId', zeroFamily]]) {
      const first = runListQuery(initial, 'prices', new URLSearchParams({ [key!]: value!, limit: '1' }));
      assert.equal(first.problem, undefined);
      const cursor = first.result!.page.nextCursor;
      assert.ok(cursor);
      fx.writeRelease(newVersion, { prices: historyPrices });
      // 新 holder 保证走磁盘历史加载，不依赖内存 cache。
      const current = new DatasetHolder(fx.root);
      assert.equal(current.reload(), true);
      const next = runListQuery(current, 'prices', new URLSearchParams({ cursor }));
      assert.equal(next.problem, undefined);
      assert.equal(next.result!.ds.version, oldVersion);
      assert.equal(next.result!.page.items.length, 1);
      assert.equal(next.result!.page.nextCursor, null);
      const historical = Dataset.load(fx.root, oldVersion);
      assert.ok(historical.enums.validModelIds.has(zeroModel));
      assert.ok(historical.enums.validFamilyIds.has(zeroFamily));
    }
  } finally { fx.cleanup(); }
});

test('T14: current 新增 identity 不污染旧 cursor 的 query 校验', () => {
  const fx = new ReleaseFixture(mkdtempSync(path.join(tmpdir(), 't07-isolation-')));
  try {
    fx.writeRelease(oldVersion, { prices: historyPrices });
    fx.writeRelease(newVersion, { modelIdentities: catalog, prices: historyPrices });
    const holder = new DatasetHolder(fx.root);
    assert.equal(holder.reload(), true);
    for (const [key, value, code] of [
      ['modelId', zeroModel, 'invalid_model_id'],
      ['familyId', zeroFamily, 'invalid_family_id'],
    ]) {
      const { normalized, problems } = normalizeQuery('prices', new URLSearchParams({ [key!]: value! }), holder.current!);
      assert.deepEqual(problems, []);
      // 使用服务端签名的测试 cursor，隔离验证历史 query 校验，不被 MAC 拒绝掩盖。
      const cursor = encodeCursor({ v: 1, sv: '1.0', ds: oldVersion, ep: 'prices',
        qh: normalized!.qh, qp: normalized!.params, k: ['alibaba', 'history-1', 'input', 'history-1'] });
      const result = runListQuery(holder, 'prices', new URLSearchParams({ cursor }));
      assert.equal(result.problem?.status, 400);
      assert.equal(result.problem?.code, code);
    }
    assert.equal(holder.getOrLoad(oldVersion)!.enums.validModelIds.size, 0);
    assert.equal(holder.getOrLoad(oldVersion)!.enums.validFamilyIds.size, 0);
  } finally { fx.cleanup(); }
});

for (const corruption of ['missing-file', 'missing-entry', 'bytes', 'hash', 'malformed', 'shape', 'dangling-family'] as const) {
  test(`T15: catalog ${corruption} → current/history load fail，reload 保留旧数据`, () => {
    const fx = new ReleaseFixture(mkdtempSync(path.join(tmpdir(), 't07-corrupt-')));
    try {
      fx.writeRelease(oldVersion, { modelIdentities: catalog, prices: historyPrices });
      const holder = new DatasetHolder(fx.root);
      assert.equal(holder.reload(), true);
      const previous = holder.current;
      const dir = path.join(fx.root, 'releases', oldVersion);
      const file = path.join(dir, 'model-identities.json');
      let raw = readFileSync(file, 'utf-8');
      if (corruption === 'missing-file') rmSync(file);
      if (corruption === 'bytes') writeFileSync(file, raw + ' ');
      if (corruption === 'hash') writeFileSync(file, raw.replace('Zero Model', 'Gone Model'));
      if (['malformed', 'shape', 'dangling-family'].includes(corruption)) {
        raw = corruption === 'malformed' ? '{' : corruption === 'shape' ? '[]' : JSON.stringify({
          models: [{ modelId: zeroModel, modelName: 'Zero Model', familyId: 'alibaba:missing' }], families: [],
        });
        writeFileSync(file, raw);
      }
      for (const manifestPath of [path.join(fx.root, 'manifest.json'), path.join(dir, 'manifest.json')]) {
        const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
        if (corruption === 'missing-entry') {
          manifest.files = manifest.files.filter((f: { path: string }) => !f.path.endsWith('/model-identities.json'));
        } else if (['malformed', 'shape', 'dangling-family'].includes(corruption)) {
          const entry = manifest.files.find((f: { path: string }) => f.path.endsWith('/model-identities.json'));
          entry.bytes = Buffer.byteLength(raw);
          entry.sha256 = createHash('sha256').update(raw).digest('hex');
        }
        writeFileSync(manifestPath, JSON.stringify(manifest));
      }
      assert.throws(() => Dataset.load(fx.root), DatasetError);
      assert.throws(() => Dataset.loadDirect(fx.root, oldVersion), DatasetError);
      assert.equal(holder.reload(), false);
      assert.equal(holder.current, previous);
      assert.match(holder.lastReloadError!, /identity catalog/);
    } finally { fx.cleanup(); }
  });
}

// ---------------------------------------------------------------------------
// T18/T19：REST 与 MCP 在 identity 校验上行为一致（共用 runListQuery）
// MCP 侧：unknown identity → isError + invalid_*；known-but-empty → 200 empty
// ---------------------------------------------------------------------------
test('T18/T19: MCP unknown identity 与 REST 一致 / known-but-empty 一致', async () => {
  const root = mkdtempSync(path.join(tmpdir(), 't07-mcp-identity-'));
  const mcpFx = new ReleaseFixture(root);
  mcpFx.writeRelease('ds_' + 'd'.repeat(64), {
    modelIdentities: catalog,
    prices: [
      { factKey: 'fk1', providerId: 'alibaba', modelKey: 'qwen-coder-plus',
        modelId: 'alibaba:qwen-coder-plus', modelName: 'Qwen Coder Plus',
        familyId: 'alibaba:qwen-coder', familyName: 'Qwen Coder', component: 'input' },
    ],
  });
  const mcpHolder = new DatasetHolder(root);
  assert.equal(mcpHolder.reload(), true, mcpHolder.lastReloadError ?? 'reload failed');
  const mcpServer = http.createServer(createMcpHandler(mcpHolder, {
    originAllowlist: ['https://daily.maas.click'],
    maxBodyBytes: 64 * 1024,
    rateLimit: { capacity: 100, refillPerMinute: 1000 },
  }));
  await new Promise<void>((r) => mcpServer.listen(0, '127.0.0.1', () => r()));
  const mcpBase = `http://127.0.0.1:${(mcpServer.address() as { port: number }).port}/api/mcp`;
  const client = new Client({ name: 't07-identity-mcp', version: '1.0' });
  await client.connect(new StreamableHTTPClientTransport(new URL(mcpBase)));
  try {
    // T18：unknown identity → isError + invalid_model_id（与 REST 同 code）
    const unknown = await client.callTool({ name: 'maas_get_prices', arguments: { modelId: 'alibaba:ghost-model' } }) as unknown as
      { isError?: boolean; structuredContent?: { error?: { code: string } } };
    assert.equal(unknown.isError, true);
    assert.equal(unknown.structuredContent!.error!.code, 'invalid_model_id');

    const unknownFamily = await client.callTool({ name: 'maas_get_prices', arguments: { familyId: 'alibaba:ghost-family' } }) as unknown as
      { isError?: boolean; structuredContent?: { error?: { code: string } } };
    assert.equal(unknownFamily.isError, true);
    assert.equal(unknownFamily.structuredContent!.error!.code, 'invalid_family_id');

    // T19：known-but-empty identity → 200 empty（与 REST 同语义）
    const empty = await client.callTool({ name: 'maas_get_prices', arguments: { modelId: zeroModel } }) as unknown as
      { isError?: boolean; structuredContent?: { items?: unknown[] } };
    assert.equal(empty.isError, undefined);
    assert.deepEqual(empty.structuredContent!.items, []);

    const emptyFamily = await client.callTool({ name: 'maas_get_changes', arguments: { familyId: zeroFamily } }) as unknown as
      { isError?: boolean; structuredContent?: { items?: unknown[] } };
    assert.equal(emptyFamily.isError, undefined);
    assert.deepEqual(emptyFamily.structuredContent!.items, []);
  } finally {
    await client.close().catch(() => {});
    mcpServer.closeAllConnections?.();
    await new Promise<void>((r) => mcpServer.close(() => r()));
    mcpFx.cleanup();
  }
});
