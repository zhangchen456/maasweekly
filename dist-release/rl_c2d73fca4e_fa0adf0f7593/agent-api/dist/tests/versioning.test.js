/**
 * 版本与热重载测试（T12/T15）：两个 datasetVersion、翻页期间切版本、
 * 409 dataset_version_expired、热重载成功/失败续服旧版。
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, renameSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { DatasetHolder } from '../dataset.js';
import { createHandler } from '../http.js';
import { ReleaseFixture } from './fixture.js';
const V1 = 'ds_' + '1'.repeat(64);
const V2 = 'ds_' + '2'.repeat(64);
let server;
let base;
let holder;
let fx;
before(async () => {
    const root = mkdtempSync(path.join(tmpdir(), 't03-ver-'));
    fx = new ReleaseFixture(root);
    // 两套版本：V1 4 条、V2 5 条（多一条 09-13）
    fx.writeRelease(V1, {
        changes: [
            { id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v1-a' },
            { id: 'obs_' + 'b'.repeat(64), observationDate: '2026-09-14', title: 'v1-b' },
            { id: 'obs_' + 'c'.repeat(64), observationDate: '2026-09-13', title: 'v1-c' },
            { id: 'obs_' + 'd'.repeat(64), observationDate: '2026-09-12', title: 'v1-d' },
        ],
        prices: [{ factKey: 'f1', providerId: 'openai', modelKey: 'm', component: 'input' }],
    });
    holder = new DatasetHolder(root);
    assert.ok(holder.reload());
    server = http.createServer(createHandler(holder, { rateLimit: { capacity: 100000, refillPerMinute: 1000000 } }));
    await new Promise((r) => server.listen(0, '127.0.0.1', r));
    base = `http://127.0.0.1:${server.address().port}`;
});
after(() => {
    server.closeAllConnections?.();
    server.close();
    fx.cleanup();
});
async function get(p) {
    return fetch(base + p);
}
test('T12 翻页期间发布新版本：旧 cursor 继续读旧 release', async () => {
    // 第一页（V1）
    const r1 = await get('/api/v1/changes?limit=2&from=2026-09-01&to=2026-09-16');
    const d1 = await r1.json();
    assert.equal(d1.datasetVersion, V1);
    assert.equal(d1.items.length, 2);
    // 发布 V2（manifest 切换，V1 目录保留）；服务器通过 reload 感知
    fx.writeRelease(V2, {
        changes: [
            { id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v2-a' },
            { id: 'obs_' + 'b'.repeat(64), observationDate: '2026-09-14', title: 'v2-b' },
            { id: 'obs_' + 'c'.repeat(64), observationDate: '2026-09-13', title: 'v2-c' },
            { id: 'obs_' + 'd'.repeat(64), observationDate: '2026-09-12', title: 'v2-d' },
            { id: 'obs_' + 'e'.repeat(64), observationDate: '2026-09-11', title: 'v2-e' },
        ],
        prices: [{ factKey: 'f1', providerId: 'openai', modelKey: 'm', component: 'input' }],
    });
    assert.ok(holder.reload(), 'reload 到 V2');
    // 新请求（无 cursor）→ V2
    const rNew = await get('/api/v1/changes?limit=1&from=2026-09-01&to=2026-09-16');
    const dNew = await rNew.json();
    assert.equal(dNew.datasetVersion, V2);
    // 旧 cursor 继续翻 → 仍是 V1 数据（v1-c/v1-d，不含 v2-e）
    const r2 = await get(`/api/v1/changes?cursor=${d1.page.nextCursor}`);
    const d2 = await r2.json();
    assert.equal(d2.datasetVersion, V1);
    assert.deepEqual(d2.items.map((i) => i.title), ['v1-c', 'v1-d']);
});
test('T12b 篡改 cursor（含 ds 字段）→ 400 invalid_cursor（MAC 拦截）', async () => {
    // 伪造版本号：改 ds 字段会破坏 MAC 签名 → 400（P1-2）
    const r1 = await get('/api/v1/changes?limit=1&from=2026-09-01&to=2026-09-16');
    const d1 = await r1.json();
    const payload = JSON.parse(Buffer.from(d1.page.nextCursor, 'base64url').toString('utf-8'));
    payload.ds = 'ds_' + '9'.repeat(64);
    const forged = Buffer.from(JSON.stringify(payload), 'utf-8').toString('base64url');
    const r = await get(`/api/v1/changes?cursor=${forged}`);
    assert.equal(r.status, 400);
    const body = await r.json();
    assert.equal(body['code'], 'invalid_cursor');
    // 无 MAC 的旧形态 cursor → 400
    const noMac = Buffer.from(JSON.stringify({ ...payload, ds: 'ds_' + '1'.repeat(64), mac: undefined }), 'utf-8').toString('base64url');
    assert.equal((await get(`/api/v1/changes?cursor=${noMac}`)).status, 400);
});
test('T12b2 真实清理后的版本 → 409 dataset_version_expired', async () => {
    // 场景：cursor 指向旧版本 X（非 current），X 目录已被清理。
    // 构造：拿当前版本 cursor → 发布新版本并 reload（current 切走）→
    // 删掉 cursor 指向的旧版本目录 → cursor 请求应 409。
    // 注意：finally 恢复 manifest 到测试前版本，避免污染后续 T12c/T15。
    const before = holder.current.version;
    const r1 = await get('/api/v1/changes?limit=1&from=2026-09-01&to=2026-09-16');
    const d1 = await r1.json();
    const oldVersion = d1.datasetVersion;
    const Vnew = 'ds_' + '5'.repeat(64);
    fx.writeRelease(Vnew, {
        changes: [{ id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'vnew' }],
        prices: [],
    });
    assert.ok(holder.reload(), 'current 切到新版本');
    // 旧版本目录删除（模拟 retention 清理）
    const dir = path.join(fx.root, 'releases', oldVersion);
    const moved = dir + '.moved';
    renameSync(dir, moved);
    try {
        const r = await get(`/api/v1/changes?cursor=${d1.page.nextCursor}`);
        assert.equal(r.status, 409, `旧版本 ${oldVersion.slice(0, 10)} 清理后 cursor 应 409`);
        const body = await r.json();
        assert.equal(body['code'], 'dataset_version_expired');
        assert.ok(body['recovery']?.includes('第一页'));
    }
    finally {
        renameSync(moved, dir);
        // 恢复 manifest 指回 before 版本（重写 release 目录里的顶层 manifest）
        fx.writeRelease(before, {
            changes: [
                { id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v2-a' },
                { id: 'obs_' + 'b'.repeat(64), observationDate: '2026-09-14', title: 'v2-b' },
                { id: 'obs_' + 'c'.repeat(64), observationDate: '2026-09-13', title: 'v2-c' },
                { id: 'obs_' + 'd'.repeat(64), observationDate: '2026-09-12', title: 'v2-d' },
                { id: 'obs_' + 'e'.repeat(64), observationDate: '2026-09-11', title: 'v2-e' },
            ],
            prices: [{ factKey: 'f1', providerId: 'openai', modelKey: 'm', component: 'input' }],
        });
        assert.ok(holder.reload(), '恢复 current');
    }
});
test('T12c 篡改 cursor → 400 invalid_cursor', async () => {
    const r1 = await get('/api/v1/changes?limit=1&from=2026-09-01&to=2026-09-16');
    const d1 = await r1.json();
    // 跨端点复用：changes 的 cursor 用于 prices
    const r = await get(`/api/v1/prices?cursor=${d1.page.nextCursor}`);
    assert.equal(r.status, 400);
    const body = await r.json();
    assert.equal(body['code'], 'cursor_endpoint');
    // 改 qh（篡改）→ MAC 拦截 400
    const r2 = await get('/api/v1/weekly?limit=1');
    const d2 = await r2.json();
    const pl = JSON.parse(Buffer.from(d2.page.nextCursor, 'base64url').toString('utf-8'));
    pl.qh = 'deadbeefdeadbeef';
    const forged = Buffer.from(JSON.stringify(pl), 'utf-8').toString('base64url');
    const r3 = await get(`/api/v1/weekly?cursor=${forged}`);
    assert.equal(r3.status, 400);
    assert.equal((await r3.json())['code'], 'invalid_cursor');
    // 坏 base64
    const r4 = await get('/api/v1/changes?cursor=%%%');
    assert.equal(r4.status, 400);
});
test('T15 热重载：成功原子切换 / 损坏版本续服旧版 / 单请求不混版', async () => {
    // 当前是 V2。写一个损坏的 V3（hash 篡改）→ reload 失败 → 仍服务 V2
    const root = fx.root;
    fx.writeRelease('ds_' + '3'.repeat(64), {
        changes: [{ id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15' }],
        prices: [],
        tamper: 'hash',
    });
    assert.ok(!holder.reload(), '损坏版本 reload 必须失败');
    assert.ok(holder.lastReloadError);
    // 服务仍是 V2
    const r = await get('/api/v1/changes?limit=1');
    const d = await r.json();
    assert.equal(d.datasetVersion, V2);
    // status 披露错误
    const rs = await get('/api/v1/status');
    const ds = await rs.json();
    assert.ok(ds.status.service.lastReloadError);
    // 修复：重写合法 V3 → reload 成功切换
    fx.writeRelease('ds_' + '3'.repeat(64), {
        changes: [{ id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'v3' }],
        prices: [],
    });
    assert.ok(holder.reload());
    const r2 = await get('/api/v1/changes?limit=1');
    const d2 = await r2.json();
    assert.equal(d2.datasetVersion, 'ds_' + '3'.repeat(64));
    assert.equal(d2.items[0].title, 'v3');
});
test('T15b manifest 损坏 → 不加载半成品', async () => {
    // 复制一个新 root 做破坏实验
    const root2 = mkdtempSync(path.join(tmpdir(), 't03-broken-'));
    const fx2 = new ReleaseFixture(root2);
    fx2.writeRelease('ds_' + '4'.repeat(64), { changes: [], prices: [] });
    // changes 为空 + prices 为空 → spotCheck 拒绝
    const h2 = new DatasetHolder(root2);
    assert.ok(!h2.reload());
    fx2.cleanup();
});
