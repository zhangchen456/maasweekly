#!/usr/bin/env node
// Isolated, repeatable API capacity sampling. Build agent-api before running.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { createHash } from 'node:crypto';
import { performance, monitorEventLoopDelay } from 'node:perf_hooks';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Dataset, DatasetHolder } from '../services/agent-api/dist/dataset.js';
import { createHandler } from '../services/agent-api/dist/http.js';
import { runListQuery, setCursorSecret } from '../services/agent-api/dist/query.js';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const arg = (key, fallback) => args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
const hash = value => createHash('sha256').update(value).digest('hex');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const percentile = (values, p) => [...values].sort((a, b) => a - b)[Math.max(0, Math.ceil(values.length * p) - 1)];
const stats = values => ({ medianMs: percentile(values, .5), minMs: Math.min(...values), maxMs: Math.max(...values) });

function makeSample(source, target, factor) {
  const original = JSON.parse(fs.readFileSync(path.join(source, 'manifest.json')));
  const data = {};
  // Fixed seed, remapping all stable IDs and embedded permalinks consistently.
  const transform = (value, replica, key = '') => {
    if (Array.isArray(value)) return value.map(v => transform(v, replica, key));
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, transform(v, replica, k)]));
    if (typeof value !== 'string') return value;
    if (key === 'factKey') return hash(`ar-capacity-v1:${replica}:${value}`);
    return value.replace(/\b(obs|price|pfv|ev)_([0-9a-f]{64})\b/g, (_, prefix, id) => `${prefix}_${hash(`ar-capacity-v1:${replica}:${prefix}:${id}`)}`);
  };
  for (const entry of original.files) {
    const name = path.basename(entry.path, '.json');
    const value = JSON.parse(fs.readFileSync(path.join(source, entry.path)));
    data[name] = ['changes', 'items', 'prices', 'evidence'].includes(name)
      ? Array.from({ length: factor }, (_, r) => value.map(v => transform(v, r))).flat() : value;
  }
  const cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  data.changes.sort((a, b) => cmp(b.observationDate, a.observationDate) || cmp(a.id, b.id));
  data.prices.sort((a, b) => cmp(a.providerId, b.providerId) || cmp(a.modelKey, b.modelKey) || cmp(a.component, b.component) || cmp(a.factKey, b.factKey));
  for (const name of ['items', 'evidence']) data[name].sort((a, b) => cmp(a.id, b.id));
  for (const name of ['changes', 'items', 'prices', 'evidence']) {
    if (new Set(data[name].map(x => x.id)).size !== data[name].length) throw new Error(`duplicate ${name} IDs`);
  }
  const evidence = new Set(data.evidence.map(x => x.id));
  for (const c of data.changes) for (const id of c.evidenceIds) if (!evidence.has(id)) throw new Error(`dangling evidence ${id}`);
  for (const p of data.prices) if (p.evidenceId && !evidence.has(p.evidenceId)) throw new Error(`dangling price evidence ${p.evidenceId}`);
  const version = `ds_${hash(`ar-capacity-v1:${original.datasetVersion}:${factor}`)}`;
  const files = [];
  const dir = path.join(target, 'releases', version);
  fs.mkdirSync(dir, { recursive: true });
  for (const [name, value] of Object.entries(data)) {
    const bytes = Buffer.from(JSON.stringify(value));
    fs.writeFileSync(path.join(dir, `${name}.json`), bytes);
    files.push({ path: `releases/${version}/${name}.json`, bytes: bytes.length, sha256: hash(bytes) });
  }
  const manifest = { ...original, datasetVersion: version, files, retainedVersions: [] };
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(manifest));
  fs.writeFileSync(path.join(target, 'manifest.json'), JSON.stringify(manifest));
  return { sourceVersion: original.datasetVersion, seed: 'ar-capacity-v1', factor, synthetic: true, identityCatalogExpanded: false };
}

async function sample(factor) {
  const source = path.join(repo, 'data/public/v1');
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'maas-capacity-'));
  let server;
  try {
    const sampleMeta = factor === 1 ? { factor, synthetic: false } : makeSample(source, temp, factor);
    const root = factor === 1 ? source : temp;
    global.gc?.();
    const loads = [], reloads = [];
    let holder;
    for (let round = 0; round < 3; round++) {
      holder = new DatasetHolder(root);
      const start = performance.now();
      if (!holder.reload()) throw new Error(holder.lastReloadError);
      loads.push(performance.now() - start);
      const again = performance.now();
      holder.reload();
      reloads.push(performance.now() - again);
      global.gc?.();
    }
    const ds = holder.current;
    const steadyMemory = process.memoryUsage();
    setCursorSecret('isolated-capacity-fixture');
    const model = ds.prices.find(p => p.modelId)?.modelId;
    const provider = ds.prices[0].providerId;
    const queries = [
      '/api/v1/changes?limit=100', `/api/v1/changes?provider=${provider}&limit=100`,
      `/api/v1/changes?modelId=${encodeURIComponent(model)}&limit=100`, '/api/v1/changes?q=pricing&limit=100',
      '/api/v1/prices?limit=100', `/api/v1/prices?provider=${provider}&component=input&limit=100`,
      `/api/v1/prices?modelId=${encodeURIComponent(model)}&limit=100`, '/api/v1/prices?q=pro&limit=100',
    ];
    server = http.createServer(createHandler(holder, { rateLimit: { capacity: 1000000, refillPerMinute: 1000000 } }));
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const base = `http://127.0.0.1:${server.address().port}`;
    for (const query of queries) await (await fetch(base + query)).arrayBuffer();
    const throughput = [];
    for (const concurrency of [1, 10, 30]) {
      const rounds = [];
      for (let round = 0; round < 3; round++) {
        const delay = monitorEventLoopDelay({ resolution: 10 }); delay.enable();
        const latencies = [], statuses = {};
        let i = 0;
        const start = performance.now();
        await Promise.all(Array.from({ length: concurrency }, async () => {
          for (;;) {
            const n = i++; if (n >= 60) break;
            const t = performance.now(); const response = await fetch(base + queries[n % queries.length]);
            await response.arrayBuffer();
            latencies.push(performance.now() - t); statuses[response.status] = (statuses[response.status] ?? 0) + 1;
          }
        }));
        await pause(20); delay.disable();
        rounds.push({ requests: latencies.length, statuses, elapsedMs: performance.now() - start,
          p50Ms: percentile(latencies, .5), p95Ms: percentile(latencies, .95), p99Ms: percentile(latencies, .99), eventLoopP99Ms: delay.percentile(99) / 1e6 });
      }
      throughput.push({ concurrency, rounds });
    }
    const delay = monitorEventLoopDelay({ resolution: 10 }); delay.enable(); await pause(30);
    const beforeReload = performance.now(); holder.reload(); const reloadMs = performance.now() - beforeReload;
    await pause(30); delay.disable();
    const paging = {};
    for (const endpoint of ['changes', 'prices']) {
      const seen = new Set(); let raw = new URLSearchParams({ limit: '100' }); let pages = 0;
      if (endpoint === 'changes') {
        const from = new Date(`${ds.dataThrough}T00:00:00Z`); from.setUTCDate(from.getUTCDate() - 89);
        const to = new Date(`${ds.dataThrough}T00:00:00Z`); to.setUTCDate(to.getUTCDate() + 1);
        raw.set('from', from.toISOString().slice(0, 10)); raw.set('to', to.toISOString().slice(0, 10)); raw.set('includeWithdrawn', 'true');
      }
      const started = performance.now();
      do {
        const { result, problem } = runListQuery(holder, endpoint, raw);
        if (problem) throw new Error(JSON.stringify(problem));
        pages++;
        for (const item of result.page.items) { if (seen.has(item.id)) throw new Error('duplicate cursor item'); seen.add(item.id); }
        if (!result.page.nextCursor) break;
        raw = new URLSearchParams({ cursor: result.page.nextCursor });
      } while (pages < 10000);
      // Compare the exact normalized first-page window, including withdrawn entries.
      const observedExpected = endpoint === 'prices' ? ds.prices.length : ds.changes.filter(c => {
        const from = new Date(`${ds.dataThrough}T00:00:00Z`); from.setUTCDate(from.getUTCDate() - 89);
        return c.observationDate >= from.toISOString().slice(0, 10) && c.observationDate <= ds.dataThrough;
      }).length;
      if (seen.size !== observedExpected) throw new Error(`paging mismatch ${seen.size}/${observedExpected}`);
      paging[endpoint] = { pages, items: seen.size, elapsedMs: performance.now() - started, duplicateOrMissing: false };
    }
    const historical = JSON.parse(fs.readFileSync(path.join(source, 'manifest.json'))).retainedVersions.find(v => v.datasetVersion !== ds.version);
    let historicalLoad = null;
    if (factor === 1 && historical) { const t = performance.now(); const old = Dataset.loadDirect(source, historical.datasetVersion); historicalLoad = { version: old.version, elapsedMs: performance.now() - t }; }
    const low = new DatasetHolder(root); low.reload();
    const limiter = http.createServer(createHandler(low, { rateLimit: { capacity: 2, refillPerMinute: 1 } }));
    await new Promise(resolve => limiter.listen(0, '127.0.0.1', resolve));
    const rateStatuses = [];
    try { for (let i = 0; i < 3; i++) { const response = await fetch(`http://127.0.0.1:${limiter.address().port}/api/v1/prices`); rateStatuses.push(response.status); await response.arrayBuffer(); } }
    finally { limiter.closeAllConnections(); await new Promise(resolve => limiter.close(resolve)); }
    return { ...sampleMeta, datasetVersion: ds.version, dataThrough: ds.dataThrough,
      counts: { changes: ds.changes.length, prices: ds.prices.length, evidence: ds.evidenceById.size },
      load: stats(loads), sameVersionReload: stats(reloads), reloadEventLoop: { elapsedMs: reloadMs, maxMs: delay.max / 1e6 },
      historicalLoad, throughput, paging, limiterStatuses: rateStatuses, steadyMemory, finalMemory: process.memoryUsage() };
  } finally {
    if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

if (args.includes('--factor')) {
  console.log(JSON.stringify(await sample(Number(arg('--factor', '1')))));
} else {
  const output = path.resolve(arg('--output', 'docs/architecture/refactoring-2026-10/baseline.json'));
  const results = [1, 5, 10].map(factor => JSON.parse(execFileSync(process.execPath, ['--expose-gc', fileURLToPath(import.meta.url), '--factor', String(factor)], { maxBuffer: 8 * 1024 * 1024 })));
  const report = { measuredAt: new Date().toISOString(), commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim(),
    environment: { node: process.version, os: `${os.platform()} ${os.release()}`, arch: os.arch(), cpus: os.cpus().length, cpu: os.cpus()[0].model, totalMemory: os.totalmem() },
    method: { rounds: 3, requestsPerRound: 60, syntheticSeed: 'ar-capacity-v1', scope: 'local HTTP; 5x/10x unique remapped IDs; unchanged model catalog; no production traffic' },
    budgets: { concurrency: 10, queryP95Ms: 200, eventLoopP99Ms: 50, sameVersionBusinessParses: 0 }, results };
  fs.mkdirSync(path.dirname(output), { recursive: true }); fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(`Saved ${output}`);
}
