import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { Writable } from 'node:stream';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { JsonlLogger, instrumentRequest, markDataset, routeTemplate, freshnessSummary, type Diagnostic } from '../observability.js';
import { DatasetHolder, Dataset } from '../dataset.js';
import { ReleaseFixture } from './fixture.js';
const version = 'ds_' + '1'.repeat(64);
const tick = () => new Promise<void>(r => setImmediate(r));
function response() {
  const res = new EventEmitter() as ServerResponse;
  const headers = new Map<string, unknown>();
  res.statusCode = 200;
  res.getHeader = (key: string) => headers.get(key) as string;
  res.setHeader = (key: string, value: unknown) => { headers.set(key, value); return res; };
  return res;
}
test('fixed routes never retain private query, entity or arbitrary path', () => {
  assert.equal(routeTemplate('/api/v1/items/private-id?q=secret&cursor=token'), '/api/v1/items/{id}');
  assert.equal(routeTemplate('/private/secret?q=abc'), 'unknown');
  assert.equal(routeTemplate('/api/v1/prices?q=secret'), '/api/v1/prices');
});
test('concurrent request contexts report their actual dataset; disabled instrumentation preserves handler', async () => {
  const holder = { current: { version } } as DatasetHolder;
  const events: Diagnostic[] = [];
  const handler = async (_req: IncomingMessage, res: ServerResponse) => {
    await tick(); markDataset(res.statusCode === 409 ? 'historical' : version); res.emit('finish'); return 42;
  };
  assert.equal(instrumentRequest(handler, holder, 'local'), handler);
  const wrapped = instrumentRequest(handler, holder, 'rl_abc_def', e => events.push(e));
  const old = response(); old.statusCode = 409;
  await Promise.all([wrapped({ url: '/api/mcp', method: 'POST' } as IncomingMessage, old),
    wrapped({ url: '/api/v1/prices?cursor=secret', method: 'GET' } as IncomingMessage, response())]);
  assert.deepEqual(events.map(e => e.datasetVersion).sort(), [version, 'historical'].sort());
  assert.ok(old.getHeader('X-Request-Id')); assert.ok(!JSON.stringify(events).includes('secret'));
  assert.equal(await instrumentRequest(handler, holder, 'local', () => { throw Error('broken'); })({} as IncomingMessage, response()), 42);
});
test('logger bounds queued bytes, rejects oversized/cyclic events and tolerates broken streams', async () => {
  let output = '';
  const stream = new Writable({ write(chunk, _enc, done) { output += chunk; done(); } });
  const logger = new JsonlLogger(stream, 512);
  for (let n = 0; n < 100; n++) logger.emit({ kind: 'test', n });
  logger.emit({ kind: 'huge', text: 'x'.repeat(9000) });
  const cyclic: Diagnostic = { kind: 'cyclic' }; cyclic.self = cyclic; logger.emit(cyclic);
  assert.ok(logger.state.queuedBytes <= 512); assert.ok(logger.dropped > 0);
  await logger.close(); assert.ok(output.split('\n').filter(Boolean).every(s => JSON.parse(s).timestamp));
  const broken = new Writable({ write(_c, _e, done) { done(Error('EPIPE')); } });
  const failure = new JsonlLogger(broken); failure.emit({ kind: 'test' }); await tick(); await tick();
  assert.ok(failure.failedWrites > 0); await failure.close();
  let release!: () => void;
  const slow = new Writable({ highWaterMark: 1, write(_c, _e, done) { release = done; } });
  const bounded = new JsonlLogger(slow, 512);
  bounded.emit({ kind: 'first' }); await tick();
  for (let n = 0; n < 100; n++) bounded.emit({ kind: 'later', n });
  assert.ok(bounded.state.queuedBytes <= 512); assert.ok(slow.writableLength < 100);
  release(); await bounded.close(); slow.destroy();
});
test('readiness is independent of stale freshness', () => {
  assert.equal(freshnessSummary({ current: null } as DatasetHolder).ready, false);
  const holder = { current: { status: { sourceStreams: [{ state: 'failed', lastSuccessDate: '2026-09-01' }], priceStreams: [] } } } as unknown as DatasetHolder;
  assert.deepEqual(freshnessSummary(holder, Date.parse('2026-10-01T00:00:00Z')), { alive: true, ready: true, freshness: 'stale', fresh: 0, stale: 1, unknown: 0 });
});
test('an unchanged poll cannot invalidate an in-flight forced audit', async () => {
  const fx = new ReleaseFixture(mkdtempSync(path.join(tmpdir(), 'ar08-'))); fx.writeRelease(version, { changes: [{ id: 'test', observationDate: '2026-10-01' }] });
  let unblock!: () => void, started!: () => void;
  const gate = new Promise<void>(r => { unblock = r; }); const ready = new Promise<void>(r => { started = r; });
  let calls = 0;
  const holder = new DatasetHolder(fx.root, { loader: async (root, manifest) => {
    if (++calls === 1) return Dataset.loadManifest(root, manifest);
    started(); await gate; throw Error('audit failure');
  } });
  try {
    assert.equal(await holder.reloadAsync(), 'changed'); const audit = holder.reloadAsync({ force: true }); await ready;
    assert.equal(await holder.reloadAsync(), 'unchanged'); unblock(); assert.equal(await audit, 'failed');
    assert.equal(holder.current?.version, version); assert.equal(holder.lastReloadError, 'audit failure');
  } finally { unblock(); holder.close(); fx.cleanup(); }
});
