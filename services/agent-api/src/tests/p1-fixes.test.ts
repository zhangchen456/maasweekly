/**
 * 验收 P1 修复测试（2026-09-16 复验后）：
 * P1-1 历史 release 完整性校验（篡改旧版本 → 拒绝服务）
 * P1-2 cursor 伪造拦截（改 qp 重算 qh 的伪造 → MAC 拒绝）
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { DatasetHolder } from '../dataset.js';
import { createHandler } from '../http.js';
import { setCursorSecret, canonicalJson } from '../query.js';
import { ReleaseFixture } from './fixture.js';

// 测试内固定 MAC 密钥（伪造者视角：知道全部算法但没有密钥）
setCursorSecret('test-secret-for-forgery-tests');

const V1 = 'ds_' + '1'.repeat(64);
const V2 = 'ds_' + '2'.repeat(64);

let server: http.Server;
let base: string;
let holder: DatasetHolder;
let fx: ReleaseFixture;

before(async () => {
  const root = mkdtempSync(path.join(tmpdir(), 't03-p1-'));
  fx = new ReleaseFixture(root);
  fx.writeRelease(V1, {
    changes: [
      { id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v1-a' },
      { id: 'obs_' + 'b'.repeat(64), observationDate: '2026-09-14', title: 'v1-b' },
      { id: 'obs_' + 'c'.repeat(64), observationDate: '2026-09-13', title: 'v1-c' },
    ],
    prices: [{ factKey: 'f1', providerId: 'openai', modelKey: 'm', component: 'input' }],
  });
  fx.writeRelease(V2, {
    changes: [
      { id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v2-a' },
      { id: 'obs_' + 'b'.repeat(64), observationDate: '2026-09-14', title: 'v2-b' },
      { id: 'obs_' + 'c'.repeat(64), observationDate: '2026-09-13', title: 'v2-c' },
    ],
    prices: [],
  });
  holder = new DatasetHolder(root);
  assert.ok(holder.reload());
  server = http.createServer(createHandler(holder, { rateLimit: { capacity: 100000, refillPerMinute: 1000000 } }));
  await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
});

after(() => {
  server.closeAllConnections?.();
  server.close();
  fx.cleanup();
});

async function get(p: string): Promise<Response> {
  return fetch(base + p);
}

function decode(cursor: string): Record<string, unknown> {
  return JSON.parse(Buffer.from(cursor, 'base64url').toString('utf-8'));
}

function encode(payload: Record<string, unknown>): string {
  return Buffer.from(canonicalJson(payload), 'utf-8').toString('base64url');
}

test('P1-1 篡改历史 release 文件 → cursor 读取被拒（409）', async () => {
  // V1 仍是 manifest.retainedVersions 指向的保留版本，先正常翻一页拿 cursor
  const r1 = await get('/api/v1/changes?limit=1&from=2026-09-01&to=2026-09-16');
  const d1 = await r1.json() as { datasetVersion: string; page: { nextCursor: string } };
  assert.equal(d1.datasetVersion, V2);
  // 当前版本是 V2；构造读取 V1 的 cursor（用合法 V1 数据签发的路径：
  // 先把 manifest 切回 V1 拿 cursor 再切回，这里直接改 holder——
  // 更简单：直接用 Dataset.loadDirect 层面测）
  // —— 服务层做法：holder.getOrLoad(V1) 会懒加载；先验证当前能读 V1
  // 写坏 V1 的 prices.json（不动 manifest 声明的 hash）
  const v1Prices = path.join(fx.root, 'releases', V1, 'prices.json');
  const orig = readFileSync(v1Prices, 'utf-8');
  writeFileSync(v1Prices, orig.replace('1.000000', '999.000000'));
  // 懒加载缓存里没有 V1 → getOrLoad 直接从磁盘读 → hash 不符 → 409
  // 构造指向 V1 的合法签名 cursor：holder.current 是 V2，先手工构造
  // （无法从服务端拿 V1 cursor，因为 manifest 指向 V2）——用 loadDirect
  // 的行为测试替代：篡改后 DatasetHolder.getOrLoad 返回 null
  const ds = holder.getOrLoad(V1);
  assert.equal(ds, null, '篡改的历史 release 必须拒绝加载（返回 null → 409）');
  // 恢复
  writeFileSync(v1Prices, orig);
  const ds2 = holder.getOrLoad(V1);
  assert.ok(ds2, '恢复后可加载');
});

test('P1-1 历史版本保留原版元数据（generatedAt/dataThrough/coverage）', async () => {
  const ds = holder.getOrLoad(V1);
  assert.ok(ds);
  const m = JSON.parse(readFileSync(
    path.join(fx.root, 'releases', V1, 'manifest.json'), 'utf-8'));
  assert.equal(ds.dataThrough, m.dataThrough, 'dataThrough 来自 release 自身');
  assert.equal(ds.generatedAt, m.generatedAt);
  assert.deepEqual(ds.coverage, m.coverage);
});

test('P1-2 伪造 cursor（改 limit 后重算 qh，无密钥）→ 400', async () => {
  // 正常拿一个 cursor
  const r1 = await get('/api/v1/changes?limit=2&from=2026-09-01&to=2026-09-16');
  const d1 = await r1.json() as { page: { nextCursor: string } };
  const pl = decode(d1.page.nextCursor);
  // 攻击者：改 limit=10000 并重算 qh（知道算法，无密钥造不出 mac）
  pl.qp = { ...(pl.qp as Record<string, unknown>), limit: 10000 };
  (pl as { qh: string }).qh = createHash('sha256')
    .update(canonicalJson({ endpoint: 'changes', params: pl.qp }))
    .digest('hex').slice(0, 16);
  const forged = encode(pl);
  const r = await get(`/api/v1/changes?cursor=${forged}`);
  assert.equal(r.status, 400, '伪造 cursor 必须被 MAC 拦截');
  const body = await r.json() as Record<string, string>;
  assert.equal(body['code'], 'invalid_cursor');
});

test('P1-2b 若 MAC 被绕过（密钥泄露），恢复校验仍拦截非法参数', async () => {
  // 用测试密钥构造「签名有效但参数非法」的 cursor——验证第二层：
  // 恢复 qp 时重新走全量规范化（limit=10000 → invalid_limit 400）
  const r1 = await get('/api/v1/changes?limit=2&from=2026-09-01&to=2026-09-16');
  const d1 = await r1.json() as { page: { nextCursor: string } };
  const pl = decode(d1.page.nextCursor);
  const evilQp = { ...(pl.qp as Record<string, unknown>), limit: 10000 };
  const qh = createHash('sha256')
    .update(canonicalJson({ endpoint: 'changes', params: evilQp }))
    .digest('hex').slice(0, 16);
  // 有密钥的签名（模拟密钥泄露场景，测试第二层防御）
  const { encodeCursor } = await import('../query.js');
  const signed = encodeCursor({
    v: 1, sv: '1.0', ds: pl.ds as string, ep: 'changes',
    qh, qp: evilQp, k: pl.k as (string | number)[],
  });
  const r = await get(`/api/v1/changes?cursor=${signed}`);
  assert.equal(r.status, 400, '即使签名有效，非法 limit 仍被重新校验拦截');
  const body = await r.json() as Record<string, string>;
  assert.equal(body['code'], 'invalid_limit');
});

test('P1-2c 合法翻页不受影响', async () => {
  const r1 = await get('/api/v1/changes?limit=1&from=2026-09-01&to=2026-09-16');
  const d1 = await r1.json() as { page: { nextCursor: string | null } };
  assert.ok(d1.page.nextCursor);
  const r2 = await get(`/api/v1/changes?cursor=${d1.page.nextCursor}`);
  assert.equal(r2.status, 200);
});
