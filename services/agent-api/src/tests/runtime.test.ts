import { test } from 'node:test';
import { Worker } from 'node:worker_threads';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import type { IncomingMessage } from 'node:http';
import { Dataset, DatasetHolder, type Manifest } from '../dataset.js';
import { ClientRateLimiter, clientKey, normalizeClientIp } from '../rate-limit.js';
import { runListQueryAsync, normalizeQuery, listChanges, listPrices, decodeCursor, type CursorPayload } from '../query.js';
import { ReleaseFixture } from './fixture.js';

const v = (n: number) => 'ds_' + String(n).repeat(64);
function fixture() {
  const fx = new ReleaseFixture(mkdtempSync(path.join(tmpdir(), 'ar02-')));
  const changes = Array.from({ length: 30 }, (_, i) => ({
    id: `obs_${String(i).padStart(64, '0')}`, observationDate: `2026-09-${String(10 + i % 7).padStart(2, '0')}`,
    providerId: i % 2 ? 'openai' : 'alibaba', status: i % 5 ? 'active' : 'withdrawn', title: `Query ${i}`,
  }));
  const prices = Array.from({ length: 30 }, (_, i) => ({
    factKey: `f${i}`, providerId: i < 15 ? 'alibaba' : 'openai', modelKey: `m${String(i).padStart(2, '0')}`, component: 'input',
  }));
  fx.writeRelease(v(1), { changes, prices });
  return { fx, changes, prices };
}

test('worker verifies candidates; ten unchanged polls parse zero business files; force failure retains current', async () => {
  const { fx } = fixture(); const holder = new DatasetHolder(fx.root);
  try {
    assert.equal(await holder.reloadAsync(), 'changed');
    const current = holder.current;
    for (let i = 0; i < 10; i++) assert.equal(await holder.reloadAsync(), 'unchanged');
    assert.equal(holder.metrics.businessLoads, 1); assert.equal(holder.metrics.unchangedPolls, 10);
    writeFileSync(path.join(fx.root, 'releases', v(1), 'prices.json'), '[]');
    assert.equal(await holder.reloadAsync({ force: true }), 'failed');
    assert.equal(holder.current, current); assert.match(holder.lastReloadError!, /bytes|sha256/);
    fx.writeRelease(v(2), { changes: [{ id: 'next', observationDate: '2026-09-16' }], tamper: 'hash' });
    assert.equal(await holder.reloadAsync(), 'failed'); assert.equal(holder.current, current);
  } finally { holder.close(); fx.cleanup(); }
});

test('historical first reads single-flight; zero cache budget reloads retained cursor and genuine deletion returns 409', async () => {
  const { fx, changes, prices } = fixture();
  const holder = new DatasetHolder(fx.root, { maxRetainedVersions: 0, maxRetainedBytes: 0 });
  try {
    assert.equal(await holder.reloadAsync(), 'changed');
    const first = await runListQueryAsync(holder, 'changes', new URLSearchParams('limit=2&includeWithdrawn=true'));
    const token = first.result!.page.nextCursor!;
    fx.writeRelease(v(2), { changes, prices }); assert.equal(await holder.reloadAsync(), 'changed');
    const before = holder.metrics.businessLoads;
    const pages = await Promise.all(Array.from({ length: 8 }, () => runListQueryAsync(holder, 'changes', new URLSearchParams({ cursor: token }))));
    assert.equal(holder.metrics.businessLoads - before, 1);
    for (const page of pages) { assert.equal(page.result?.ds.version, v(1)); assert.equal(page.result?.page.items.length, 2); }
    assert.equal(holder.cacheState.entries, 0); assert.equal(holder.cacheState.inFlight, 0);
    assert.equal((await runListQueryAsync(holder, 'changes', new URLSearchParams({ cursor: token }))).result?.ds.version, v(1));
    rmSync(path.join(fx.root, 'releases', v(1)), { recursive: true });
    assert.equal((await runListQueryAsync(holder, 'changes', new URLSearchParams({ cursor: token }))).problem?.status, 409);
  } finally { holder.close(); fx.cleanup(); }
});

test('a superseded candidate never replaces current and closed loader cannot publish', async () => {
  const { fx, changes, prices } = fixture();
  let unblock!: () => void, started!: () => void;
  const gate = new Promise<void>(r => { unblock = r; });
  const ready = new Promise<void>(r => { started = r; });
  const holder = new DatasetHolder(fx.root, { loader: async (root, manifest: Manifest) => {
    const ds = Dataset.loadManifest(root, manifest); started(); await gate; return ds;
  } });
  try {
    const old = holder.reloadAsync(); await ready;
    fx.writeRelease(v(2), { changes, prices }); const next = holder.reloadAsync();
    unblock(); assert.equal(await old, 'superseded'); assert.equal(await next, 'changed');
    assert.equal(holder.current!.version, v(2));
    holder.close(); assert.equal(await holder.reloadAsync(), 'failed');
  } finally { unblock(); holder.close(); fx.cleanup(); }
});

test('no valid startup yields 503; aborted worker settles without publishing', async () => {
  const { fx } = fixture();
  const empty = new DatasetHolder(path.join(fx.root, 'missing'));
  const holder = new DatasetHolder(fx.root);
  try {
    assert.equal(await empty.reloadAsync(), 'failed');
    assert.equal((await runListQueryAsync(empty, 'prices', new URLSearchParams())).problem?.status, 503);
    const job = holder.reloadAsync(); holder.close();
    assert.ok(['failed', 'superseded'].includes(await job)); assert.equal(holder.current, null);
  } finally { empty.close(); holder.close(); fx.cleanup(); }
});

test('valid hashes cannot conceal broken references; historical LRU obeys its version budget', async () => {
  const { fx, changes, prices } = fixture(); const holder = new DatasetHolder(fx.root, { maxRetainedVersions: 1 });
  try {
    assert.equal(await holder.reloadAsync(), 'changed');
    fx.writeRelease(v(2), { changes, prices }); assert.equal(await holder.reloadAsync(), 'changed');
    fx.writeRelease(v(3), { changes, prices }); assert.equal(await holder.reloadAsync(), 'changed');
    assert.ok(await holder.getOrLoadAsync(v(1))); assert.ok(await holder.getOrLoadAsync(v(2)));
    assert.equal(holder.cacheState.entries, 1);
    const loads = holder.metrics.businessLoads; assert.ok(await holder.getOrLoadAsync(v(1)));
    assert.equal(holder.metrics.businessLoads, loads + 1); assert.equal(holder.current!.version, v(3));
    const file = path.join(fx.root, 'releases', v(3), 'items.json'); writeFileSync(file, '[]');
    for (const target of [path.join(fx.root, 'manifest.json'), path.join(fx.root, 'releases', v(3), 'manifest.json')]) {
      const manifest = JSON.parse(readFileSync(target, 'utf8')) as Manifest;
      const entry = manifest.files.find(f => f.path.endsWith('/items.json'))!;
      entry.bytes = 2; entry.sha256 = createHash('sha256').update('[]').digest('hex');
      writeFileSync(target, JSON.stringify(manifest));
    }
    const current = holder.current;
    assert.equal(await holder.reloadAsync({ force: true }), 'failed');
    assert.match(holder.lastReloadError!, /引用缺失/); assert.equal(holder.current, current);
    const fresh = new DatasetHolder(fx.root); assert.equal(await fresh.getOrLoadAsync(v(3)), null); fresh.close();
  } finally { holder.close(); fx.cleanup(); }
});

test('indexed queries match reference scans through all pages, filters and date boundaries', () => {
  const { fx } = fixture(); const holder = new DatasetHolder(fx.root);
  try {
    assert.ok(holder.reload()); const ds = holder.current!;
    for (const ep of ['changes', 'prices'] as const) {
      for (const provider of ['', 'openai', 'alibaba']) for (const q of ['', '01', 'query']) for (const limit of [1, 3, 20]) {
        const raw = new URLSearchParams({ limit: String(limit) });
        if (provider) raw.set('provider', provider); if (q) raw.set('q', q);
        if (ep === 'changes') { raw.set('from', '2026-09-11'); raw.set('to', '2026-09-15'); }
        const nq = normalizeQuery(ep, raw, ds).normalized!;
        const p = nq.params;
        const expected = ep === 'changes' ? ds.changes.filter(c => c.status !== 'withdrawn' && c.observationDate >= p.from! && c.observationDate < p.to!
          && (!provider || c.providerId === provider) && (!q || `${c.title}\u0000${c.summary ?? ''}`.toLowerCase().includes(q)))
          : ds.prices.filter(e => (!provider || e.providerId === provider) && (!q || e.modelKey.toLowerCase().includes(q)));
        const actual: unknown[] = []; let cursor: CursorPayload | undefined;
        do {
          const page = ep === 'changes' ? listChanges(ds, nq, cursor) : listPrices(ds, nq, cursor);
          actual.push(...page.items); cursor = page.nextCursor ? decodeCursor(page.nextCursor, ep, '1.0').payload : undefined;
        } while (cursor);
        assert.deepEqual(actual, expected, `${ep}/${provider}/${q}/${limit}`);
      }
    }
  } finally { holder.close(); fx.cleanup(); }
});

function req(ip: string, header?: string) {
  return { socket: { remoteAddress: ip }, headers: header ? { 'x-maas-client-ip': header } : {} } as Pick<IncomingMessage, 'socket' | 'headers'>;
}
test('client normalization and proxy trust reject spoofing and scoped/multiple IP headers', () => {
  assert.equal(normalizeClientIp('::ffff:192.0.2.1'), '192.0.2.1');
  assert.equal(normalizeClientIp('2001:0db8::1'), '2001:db8::1');
  assert.equal(normalizeClientIp('fe80::1%lo0'), null);
  assert.equal(clientKey(req('192.0.2.1', '192.0.2.2'), true), '192.0.2.1');
  assert.equal(clientKey(req('::ffff:127.0.0.1', '192.0.2.2'), true), '192.0.2.2');
  assert.equal(clientKey(req('127.0.0.1', '192.0.2.2')), '127.0.0.1');
  assert.equal(clientKey(req('127.0.0.1', '192.0.2.2,192.0.2.3'), true), '127.0.0.1');
});
test('per-client quotas, bounded TTL state and independent global guards', () => {
  let now = 0; const config = { capacity: 2, refillPerMinute: 2, maxClients: 2, idleTtlMs: 1000, globalCapacity: 5, globalRefillPerMinute: 5 };
  const rest = new ClientRateLimiter(config, () => now), mcp = new ClientRateLimiter(config, () => now);
  const a = req('192.0.2.1'), b = req('192.0.2.2');
  assert.ok(rest.take(a).allowed); assert.ok(rest.take(a).allowed);
  assert.equal(rest.take(a).allowed, false); assert.ok(rest.take(b).allowed); assert.ok(mcp.take(a).allowed);
  for (let i = 3; i < 100; i++) rest.take(req(`192.0.2.${i}`));
  assert.equal(rest.size, 2); assert.equal(rest.take(b).allowed, false);
  now = 60000; assert.ok(rest.take(b).allowed); assert.equal(rest.size, 1);
});

// Reproduce the terminal-message ordering without relying on scheduler luck.
// The worker must not exit while the parent's next-turn hydration is pending.
test('worker terminal messages wait for parent acknowledgement before exit', async () => {
  const { fx } = fixture();
  try {
    for (const valid of [true, false]) {
      const manifest = JSON.parse(readFileSync(path.join(fx.root, 'manifest.json'), 'utf8'));
      const worker = new Worker(new URL('../dataset-worker.js', import.meta.url),
        {workerData:{root:valid ? fx.root : path.join(fx.root,'missing'), manifest}});
      let exited = false;
      worker.on('exit', () => { exited = true; });
      try {
        while (true) {
          const [message] = await once(worker, 'message');
          if (message.kind === 'done' || message.kind === 'error') {
            assert.equal(message.kind, valid ? 'done' : 'error');
            await new Promise(resolve => setTimeout(resolve, 50));
            assert.equal(exited, false, 'terminal event must survive delayed hydration');
            const exit = once(worker, 'exit'); worker.postMessage('ack'); await exit;
            break;
          }
          worker.postMessage('ack');
        }
      } finally { await worker.terminate(); }
    }
  } finally { fx.cleanup(); }
});
