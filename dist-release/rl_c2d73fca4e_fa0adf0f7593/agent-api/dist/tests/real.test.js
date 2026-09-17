/**
 * T18（HTTP 半）：对真实导出的 release 起服务，六类核心查询返回真实
 * 数据、公开引用零悬空（抽样）、性能计时。
 * 运行：npm run test:real（需先 export-public-data.py）
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatasetHolder } from '../dataset.js';
import { createHandler } from '../http.js';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');
const DATA_ROOT = process.env.PUBLIC_DATA_ROOT
    ?? path.join(repoRoot, 'data', 'public', 'v1');
let server;
let base;
const t0 = Date.now();
before(async () => {
    const holder = new DatasetHolder(DATA_ROOT);
    assert.ok(holder.reload(), `真实 release 加载失败: ${holder.lastReloadError}`);
    server = http.createServer(createHandler(holder, { rateLimit: { capacity: 100000, refillPerMinute: 1000000 } }));
    await new Promise((r) => server.listen(0, '127.0.0.1', r));
    base = `http://127.0.0.1:${server.address().port}`;
});
after(() => {
    server.closeAllConnections?.();
    server.close();
});
async function get(p) {
    return fetch(base + p);
}
test('T18 六类核心查询返回真实数据', async () => {
    // 1. changes
    const r1 = await get('/api/v1/changes?limit=5');
    assert.equal(r1.status, 200);
    const d1 = await r1.json();
    assert.ok(d1.items.length > 0);
    assert.ok(d1.datasetVersion.startsWith('ds_'));
    assert.ok(d1.query.from && d1.query.to);
    // 2. prices
    const r2 = await get('/api/v1/prices?limit=5');
    const d2 = await r2.json();
    assert.ok(d2.items.length > 0);
    assert.ok(d2.items.every((p) => typeof p.amount === 'string' && p.unitQuantity > 0));
    // 3. item（取第一条 change 的 id）
    const id1 = d1.items[0].id;
    const r3 = await get(`/api/v1/items/${id1}`);
    assert.equal(r3.status, 200);
    const d3 = await r3.json();
    assert.equal(d3.item.id, id1);
    // 4. evidence（取一条 price change 的证据）
    const r4q = await get('/api/v1/changes?type=price&limit=1');
    const d4q = await r4q.json();
    const eid = d4q.items[0].evidenceIds[0];
    const r4 = await get(`/api/v1/evidence/${eid}`);
    assert.equal(r4.status, 200);
    const d4 = await r4.json();
    assert.ok(d4.item.excerptText.length > 0 && d4.item.excerptHash.length === 64);
    // 5. weekly
    const r5 = await get('/api/v1/weekly?limit=3');
    const d5 = await r5.json();
    assert.ok(d5.items.length > 0);
    const wid = d5.items[0].id;
    const r5b = await get(`/api/v1/weekly/${wid}`);
    assert.equal(r5b.status, 200);
    // 6. status
    const r6 = await get('/api/v1/status');
    const d6 = await r6.json();
    assert.ok(d6.status.providers.length >= 15);
    assert.ok(d6.status.priceStreams.length === 8);
});
test('T18 公开引用零悬空（抽样 200 条）', async () => {
    // 抽样 change 的 evidenceIds 全部可达
    const r = await get('/api/v1/changes?type=price&limit=100&from=2026-09-01&to=2026-09-17');
    const d = await r.json();
    assert.ok(d.items.length > 50, `真实价格事件应有数百条，实得 ${d.items.length}`);
    for (const c of d.items.slice(0, 200)) {
        for (const eid of c.evidenceIds) {
            const re = await get(`/api/v1/evidence/${eid}`);
            assert.equal(re.status, 200, `悬空证据: ${eid}`);
        }
        assert.ok(c.links.permalink.startsWith('/item/'));
    }
    // prices 的证据引用抽样
    const rp = await get('/api/v1/prices?limit=100');
    const dp = await rp.json();
    for (const p of dp.items) {
        if (p.evidenceId) {
            const re = await get(`/api/v1/evidence/${p.evidenceId}`);
            assert.equal(re.status, 200, `悬空证据: ${p.evidenceId}`);
        }
    }
});
test('T18 性能与元数据一致性', async () => {
    const t = Date.now();
    await get('/api/v1/changes?limit=100');
    const changesMs = Date.now() - t;
    const t2 = Date.now();
    await get('/api/v1/prices?limit=100');
    const pricesMs = Date.now() - t2;
    console.log(`[perf] changes(limit=100): ${changesMs}ms, prices(limit=100): ${pricesMs}ms, 总时长: ${Date.now() - t0}ms`);
    // 六类查询同一 datasetVersion
    const versions = new Set();
    for (const p of ['/api/v1/changes?limit=1', '/api/v1/prices?limit=1',
        '/api/v1/weekly?limit=1', '/api/v1/status']) {
        const d = await (await get(p)).json();
        versions.add(d.datasetVersion);
    }
    assert.equal(versions.size, 1, `六类查询必须同一 datasetVersion: ${[...versions]}`);
});
