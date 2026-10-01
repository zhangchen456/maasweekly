#!/usr/bin/env node
import http from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pause = ms => new Promise(r => setTimeout(r, ms));
const reports = [];
for (const mode of ['enabled', 'disabled', 'unready']) {
  const probe = http.createServer(); await new Promise(r => probe.listen(0, '127.0.0.1', r));
  const port = probe.address().port; await new Promise(r => probe.close(r));
  const child = spawn(process.execPath, [path.join(repo, 'services/agent-api/dist/server.js')], {
    cwd: repo, env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', RELOAD_INTERVAL_MS: '0',
      MAAS_DIAGNOSTICS: mode === 'disabled' ? '0' : '1',
      PUBLIC_DATA_ROOT: mode === 'unready' ? '/tmp/maas-deliberately-absent-data' : path.join(repo, 'data/public/v1') }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '', error = '';
  child.stdout.on('data', data => { output += data; assert.ok(output.length < 1024 * 1024); });
  child.stderr.on('data', data => { error += data; });
  let response;
  try {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      try { response = await fetch(`http://127.0.0.1:${port}/api/v1/status?q=secret-canary`); break; }
      catch { if (child.exitCode !== null) throw Error(error); await pause(50); }
    }
    assert.ok(response, 'server readiness timed out');
    assert.equal(response.status, 200);
    if (mode === 'unready') { const prices = await fetch(`http://127.0.0.1:${port}/api/v1/prices`); assert.equal(prices.status, 503); await prices.arrayBuffer(); }
    const body = await response.json();
    await pause(50);
    child.kill('SIGTERM'); await once(child, 'exit');
    const events = output.trim() ? output.trim().split('\n').map(line => JSON.parse(line)) : [];
    assert.ok(!output.includes(repo)); assert.ok(!output.includes('secret-canary'));
    if (mode === 'disabled') assert.equal(events.length, 0);
    else {
      const request = events.find(e => e.kind === 'api.request' && e.route === '/api/v1/status'); assert.ok(request?.requestId);
      assert.equal(request.datasetVersion, body.datasetVersion ?? null);
      assert.equal(request.route, '/api/v1/status');
      assert.equal(events.find(e => e.kind === 'runtime.sample').health.ready, mode !== 'unready');
      assert.equal(events.find(e => e.kind === 'dataset.load').result, mode === 'unready' ? 'failed' : 'changed');
    }
    reports.push({ mode, statusCode: response.status, datasetVersion: body.datasetVersion ?? null, events });
  } finally { if (child.exitCode === null) { child.kill('SIGKILL'); await once(child, 'exit'); } }
}
const target = process.argv[2];
assert.ok(target, 'output file required'); fs.writeFileSync(target, JSON.stringify({ measuredAt: new Date().toISOString(), reports }, null, 2) + '\n');
console.log('Actual server diagnostics enabled/disabled/unready: passed');
