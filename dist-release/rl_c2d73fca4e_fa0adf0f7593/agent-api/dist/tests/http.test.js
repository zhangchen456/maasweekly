/**
 * HTTP 层测试（T06–T14、T16）：起真实服务器 + fetch。
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
let server;
let base;
let fx;
before(async () => {
    const root = mkdtempSync(path.join(tmpdir(), 't03-api-'));
    fx = new ReleaseFixture(root);
    fx.writeRelease('ds_' + '1'.repeat(64), {
        changes: [
            { id: 'obs_' + 'a'.repeat(64), observationDate: '2026-09-15', title: 'OpenAI 博客更新' },
            { id: 'obs_' + 'b'.repeat(64), observationDate: '2026-09-14', providerId: 'alibaba', title: '阿里更新' },
            { id: 'price_' + 'c'.repeat(64), observationDate: '2026-09-15', recordType: 'price_change',
                title: '价格变化', evidenceId: 'ev_' + 'e'.repeat(64) },
            { id: 'obs_' + 'd'.repeat(64), observationDate: '2026-09-01', status: 'withdrawn', title: '已撤回' },
        ],
        prices: [
            { factKey: 'f1', providerId: 'openai', modelKey: 'gpt-test', component: 'input', amount: '1.000000' },
            { factKey: 'f2', providerId: 'openai', modelKey: 'gpt-test', component: 'output', amount: '2.000000' },
            { factKey: 'f3', providerId: 'alibaba', modelKey: 'qwen-test', component: 'input',
                amount: '0.500000', currency: 'CNY', region: 'cn',
                contextBand: { min: 0, max: 32000 },
                timeCondition: { period: 'cache_write_1h', tz: 'UTC', schedule: '1h' } },
        ],
    });
    const holder = new DatasetHolder(root);
    assert.ok(holder.reload(), '加载 fixture 失败');
    server = http.createServer(createHandler(holder, { rateLimit: { capacity: 10000, refillPerMinute: 100000 } }));
    await new Promise((r) => server.listen(0, '127.0.0.1', r));
    base = `http://127.0.0.1:${server.address().port}`;
});
after(() => {
    server.closeAllConnections?.();
    server.close();
    fx.cleanup();
});
async function get(p, headers = {}) {
    return fetch(base + p, { headers });
}
test('T06 changes 默认查询（dataThrough 锚定 7 天窗口）', async () => {
    const r = await get('/api/v1/changes');
    assert.equal(r.status, 200);
    const d = await r.json();
    const q = d.query;
    assert.equal(q.from, '2026-09-10');
    assert.equal(q.to, '2026-09-17'); // [from, to) 语义：to = D+1
    const items = d.items;
    // 默认窗口内：09-15 两条 + 09-14 一条（09-01 withdrawn 且窗口外）
    assert.equal(items.length, 3);
    // 排序：日期倒序
    assert.ok(items[0].observationDate >= items[1].observationDate);
});
test('T06 provider/type/q/from/to 组合', async () => {
    const r = await get('/api/v1/changes?provider=alibaba');
    const d = await r.json();
    assert.equal(d.items.length, 1);
    assert.equal(d.items[0]['providerId'], 'alibaba');
    const r2 = await get('/api/v1/changes?type=price');
    const d2 = await r2.json();
    assert.equal(d2.items.length, 1);
    assert.equal(d2.items[0]['recordType'], 'price_change');
    const r3 = await get('/api/v1/changes?q=博客');
    const d3 = await r3.json();
    assert.equal(d3.items.length, 1);
    const r4 = await get('/api/v1/changes?from=2026-09-14&to=2026-09-15');
    const d4 = await r4.json();
    assert.equal(d4.items.length, 1, '[from,to) 窗口只含 09-14');
    const r5 = await get('/api/v1/changes?from=2026-09-14&to=2026-09-16');
    const d5 = await r5.json();
    assert.equal(d5.items.length, 3);
});
test('T07 prices 条件完整（contextBand/timeCondition/原币种/Decimal 字符串）', async () => {
    const r = await get('/api/v1/prices?provider=alibaba');
    const d = await r.json();
    assert.equal(d.items.length, 1);
    const p = d.items[0];
    assert.equal(p['currency'], 'CNY');
    assert.equal(p['amount'], '0.500000');
    assert.deepEqual(p['contextBand'], { min: 0, max: 32000 });
    assert.deepEqual(p['timeCondition'], { period: 'cache_write_1h', tz: 'UTC', schedule: '1h' });
    // 多组件不合并
    const r2 = await get('/api/v1/prices?provider=openai');
    const d2 = await r2.json();
    assert.equal(d2.items.length, 2);
});
test('T08a withdrawn 默认隐藏', async () => {
    const r = await get('/api/v1/changes?from=2026-08-30&to=2026-09-16');
    const d = await r.json();
    assert.ok(!d.items.some((i) => i['status'] === 'withdrawn'));
});
test('T08b includeWithdrawn=true 返回 withdrawn', async () => {
    const r = await get('/api/v1/changes?from=2026-08-30&to=2026-09-16&includeWithdrawn=true');
    const d = await r.json();
    assert.ok(d.items.some((i) => i['status'] === 'withdrawn'));
});
test('T09 item/evidence/weekly 实体与未知 404', async () => {
    const rid = await get('/api/v1/changes?from=2026-09-15&to=2026-09-16');
    const dd = await rid.json();
    const id = dd.items.find((i) => i['recordType'] === 'price_change')['id'];
    const r = await get(`/api/v1/items/${id}`);
    assert.equal(r.status, 200);
    const item = (await r.json())['item'];
    assert.ok(Array.isArray(item['revisionHistory']));
    // evidence 引用闭环
    const eid = item['evidenceIds'][0];
    const re = await get(`/api/v1/evidence/${eid}`);
    assert.equal(re.status, 200);
    const ev = (await re.json())['item'];
    assert.equal(ev['excerptText'], 'EVIL<script>alert("xss")</script>END $1 / 1M tokens');
    // 未知 404
    assert.equal((await get('/api/v1/items/obs_unknown')).status, 404);
    assert.equal((await get('/api/v1/evidence/ev_unknown')).status, 404);
    assert.equal((await get('/api/v1/weekly/1999-01-01')).status, 404);
    // weekly 不混入滚动摘要（id 集合 = fixture 的两期）
    const rw = await get('/api/v1/weekly');
    const dw = await rw.json();
    assert.deepEqual(dw.items.map((w) => w.id), ['2026-09-01', '2026-08-25']);
});
test('T10 参数校验 400 Problem JSON', async () => {
    const cases = [
        ['limit=0', 'invalid_limit'],
        ['limit=101', 'invalid_limit'],
        ['limit=abc', 'invalid_limit'],
        ['q=x', 'invalid_q'],
        ['provider=nope', 'invalid_provider'],
        ['type=weird', 'invalid_type'],
        ['from=2026-09-15', 'partial_window'],
        ['from=2026-09-15&to=2026-09-15', 'invalid_window'],
        ['from=2020-01-01&to=2026-09-16', 'window_too_large'],
        ['zzz=1', 'unknown_parameter'],
        ['limit=1&limit=2', 'duplicate_parameter'],
    ];
    for (const [qs, code] of cases) {
        const r = await get(`/api/v1/changes?${qs}`);
        assert.equal(r.status, 400, qs);
        assert.equal(r.headers.get('content-type'), 'application/problem+json; charset=utf-8', qs);
        const body = await r.json();
        assert.equal(body['code'], code, `${qs} → ${body['code']}`);
        assert.ok(body['recovery'], `${qs} 缺 recovery`);
        assert.ok(body['requestId']);
    }
});
test('T11 同版本翻完全部页（limit=1，无重复无遗漏）', async () => {
    let url = '/api/v1/changes?limit=1&includeWithdrawn=true&from=2026-08-30&to=2026-09-16';
    const seen = [];
    for (let i = 0; i < 20; i++) {
        const r = await get(url);
        assert.equal(r.status, 200);
        const d = await r.json();
        seen.push(...d.items.map((x) => x.id));
        if (!d.page.nextCursor)
            break;
        url = `/api/v1/changes?cursor=${d.page.nextCursor}`;
    }
    assert.equal(seen.length, 4);
    assert.equal(new Set(seen).size, 4, '无重复');
});
test('T11b cursor 与其他参数冲突 → 400', async () => {
    const r1 = await get('/api/v1/changes?limit=1');
    const d1 = await r1.json();
    const r = await get(`/api/v1/changes?cursor=${d1.page.nextCursor}&limit=2`);
    assert.equal(r.status, 400);
    const body = await r.json();
    assert.equal(body['code'], 'cursor_conflict');
});
test('T13 ETag / 304', async () => {
    const r1 = await get('/api/v1/status');
    assert.equal(r1.status, 200);
    const etag = r1.headers.get('etag');
    assert.ok(etag);
    const r2 = await get('/api/v1/status', { 'If-None-Match': etag });
    assert.equal(r2.status, 304);
    assert.equal(await r2.text(), '');
    const r3 = await get('/api/v1/status', { 'If-None-Match': '"stale"' });
    assert.equal(r3.status, 200);
});
test('T14 HEAD/OPTIONS/CORS/超长 cursor 413', async () => {
    const rh = await get('/api/v1/status');
    // HEAD：200 + 相同 ETag + X-Request-Id 存在 + 无 body
    const rHead = await fetch(base + '/api/v1/status', { method: 'HEAD' });
    assert.equal(rHead.status, 200);
    assert.equal(rHead.headers.get('etag'), rh.headers.get('etag'));
    assert.ok(rHead.headers.get('x-request-id'));
    assert.equal(await rHead.text(), '');
    // OPTIONS
    const rOpt = await fetch(base + '/api/v1/changes', { method: 'OPTIONS' });
    assert.equal(rOpt.status, 204);
    assert.equal(rOpt.headers.get('access-control-allow-origin'), '*');
    assert.equal(rOpt.headers.get('access-control-allow-credentials'), null);
    // 超长 cursor → 413
    const long = 'x'.repeat(5000);
    const r413 = await get(`/api/v1/changes?cursor=${long}`);
    assert.equal(r413.status, 413);
    // CORS expose
    assert.ok(rh.headers.get('access-control-expose-headers')?.includes('ETag'));
    // X-Request-Id 每请求唯一
    assert.ok(rh.headers.get('x-request-id'));
});
test('T16 恶意 excerpt 原样返回 / 路径编码不越界', async () => {
    // excerptText 已含 <script>（fixture 注入），上面 T09 已验证原样返回
    // 路径编码攻击
    assert.equal((await get('/api/v1/items/%2e%2e%2f%2e%2e%2frecords')).status, 404);
    assert.equal((await get('/api/v1/items/..%2F..%2Frecords')).status, 404);
    assert.equal((await get('/api/v1//changes')).status, 404);
    assert.equal((await get('/api/v1/items/a%00b')).status, 404);
});
test('T16b 未知路径 404（无通配）', async () => {
    assert.equal((await get('/api/v1/whatever')).status, 404);
    assert.equal((await get('/api/v2/changes')).status, 404);
    assert.equal((await get('/etc/passwd')).status, 404);
});
test('T14b 无数据版本 503', async () => {
    const emptyRoot = mkdtempSync(path.join(tmpdir(), 't03-empty-'));
    const h = new DatasetHolder(emptyRoot);
    const srv = http.createServer(createHandler(h, { rateLimit: { capacity: 10000, refillPerMinute: 100000 } }));
    await new Promise((r) => srv.listen(0, '127.0.0.1', r));
    const b2 = `http://127.0.0.1:${srv.address().port}`;
    const r = await fetch(b2 + '/api/v1/changes');
    assert.equal(r.status, 503);
    const body = await r.json();
    assert.equal(body['code'], 'no_data_available');
    // status 端点仍可用
    assert.equal((await fetch(b2 + '/api/v1/status')).status, 200);
    srv.closeAllConnections?.();
    srv.close();
});
