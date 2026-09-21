/**
 * Task 07 T07-3：modelId/familyId 查询契约测试（T08–T17 核心）。
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { DatasetHolder } from '../dataset.js';
import { createHandler } from '../http.js';
import { ReleaseFixture } from './fixture.js';

let server: http.Server;
let base: string;

before(async () => {
  const root = mkdtempSync(path.join(tmpdir(), 't07-identity-'));
  const fx = new ReleaseFixture(root);
  fx.writeRelease('ds_' + 'a'.repeat(64), {
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
      { factKey: 'fk4', providerId: 'alibaba', modelKey: 'qwen-flash-us', component: 'input' },
    ],
    changes: [
      { id: 'price_' + '1'.repeat(64), observationDate: '2026-09-01', providerId: 'alibaba',
        recordType: 'price_change', model: 'qwen-coder-plus', status: 'active',
      },
    ] as never,
  });
  const holder = new DatasetHolder(root);
  holder.reload();
  server = http.createServer(createHandler(holder, {
    rateLimit: { capacity: 100, refillPerMinute: 1000 },
  }));
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', () => r()));
  base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
});

after(() => server.close());

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
  // 该记录无 modelId——modelId 查询查不到（合法 200 空）
  const r3 = await fetch(`${base}/api/v1/prices?modelId=alibaba:qwen-flash-us`);
  const b3 = await r3.json() as { items: unknown[] };
  assert.equal(b3.items.length, 0);
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
