#!/usr/bin/env node
// Exercise the installed runtime outside its repository; no deployment.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';

const release = path.resolve(process.argv[2] ?? '');
if (!process.argv[2]) throw new Error('Usage: architecture-release-smoke.mjs <release-dir> <report-path>');
const manifest = JSON.parse(fs.readFileSync(path.join(release, 'metadata/release-manifest.json')));
const reserve = http.createServer();
await new Promise(resolve => reserve.listen(0, '127.0.0.1', resolve));
const port = reserve.address().port;
await new Promise(resolve => reserve.close(resolve));
const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'maas-runtime-smoke-'));
const child = spawn(process.execPath, [path.join(release, 'agent-api/dist/server.js')], { cwd,
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), PUBLIC_DATA_ROOT: path.join(release, 'data/public/v1'),
    MAAS_RELEASE_DIR: release, RELOAD_INTERVAL_MS: '0', CURSOR_SECRET: 'isolated-release-smoke', MCP_ALLOWED_ORIGINS: '' },
  stdio: ['ignore', 'pipe', 'pipe'] });
let diagnostic = ''; let exitCode;
child.stdout.on('data', value => { diagnostic += value.toString(); });
child.stderr.on('data', value => { diagnostic += value.toString(); });
child.on('exit', code => { exitCode = code; });
const base = `http://127.0.0.1:${port}`;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (exitCode !== undefined) throw new Error(`runtime exited: ${diagnostic.slice(-3000)}`);
    try { const response = await fetch(base + '/api/v1/status'); ready = response.status === 200; if (ready) break; }
    catch { /* booting */ }
    await sleep(100);
  }
  assert.ok(ready, 'runtime did not become ready');
  const rest = {};
  for (const endpoint of ['status', 'changes?limit=1', 'prices?limit=1', 'models']) {
    const response = await fetch(base + '/api/v1/' + endpoint);
    assert.equal(response.status, 200);
    const json = await response.json(); assert.equal(json.datasetVersion, manifest.datasetVersion);
    rest[endpoint] = response.status;
  }
  const rpc = async (method, params, id) => {
    const response = await fetch(base + '/api/mcp', { method: 'POST', headers: {
      'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
      body: JSON.stringify({ jsonrpc: '2.0', id, method, params }) });
    assert.equal(response.status, 200); return response.json();
  };
  assert.ok((await rpc('initialize', { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'release-smoke', version: '1' } }, 1)).result);
  const tools = (await rpc('tools/list', {}, 2)).result.tools.map(tool => tool.name);
  for (const name of ['maas_get_changes', 'maas_get_prices', 'maas_get_item', 'maas_get_evidence', 'maas_get_weekly']) assert.ok(tools.includes(name));
  const call = (await rpc('tools/call', { name: 'maas_get_changes', arguments: { limit: 1 } }, 3)).result;
  assert.equal(call.isError ?? false, false); assert.equal(call.structuredContent.datasetVersion, manifest.datasetVersion);
  const feeds = ['feed.xml', 'feed/weekly.xml'];
  for (const file of feeds) assert.match(fs.readFileSync(path.join(release, 'site', file), 'utf8'), /<rss\b/);
  const skillRoot = path.join(release, 'site/maas-skill');
  const skill = JSON.parse(fs.readFileSync(path.join(skillRoot, 'manifest.json')));
  assert.equal(skill.skillName, 'maas-daily');
  for (const entry of skill.files) {
    const bytes = fs.readFileSync(path.join(skillRoot, entry.path));
    assert.equal(bytes.length, entry.bytes); assert.equal(createHash('sha256').update(bytes).digest('hex'), entry.sha256);
  }
  for (const [source, date] of [['test-esc', '2026-01-01'], ['test-wd', '2026-01-02']]) {
    const id = 'obs_' + createHash('sha256').update(JSON.stringify([source, date])).digest('hex');
    assert.equal(fs.existsSync(path.join(release, 'site/item', id)), false);
  }
  const report = { verifiedAt: new Date().toISOString(), rid: manifest.releaseId, commit: manifest.gitCommit,
    datasetVersion: manifest.datasetVersion, dataThrough: manifest.dataThrough,
    runtimeCwdOutsideRepository: true, productionDependenciesOnly: !fs.existsSync(path.join(release, 'agent-api/node_modules/typescript')),
    rest, mcp: { initialize: true, tools, datasetVersion: call.structuredContent.datasetVersion },
    staticFeeds: feeds, skillFilesVerified: skill.files.length, fixturePagesAbsent: true,
    scope: 'Local installed Node process plus immutable static bytes; not nginx/CDN or live deployment' };
  const output = path.resolve(process.argv[3]); fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); console.log(JSON.stringify(report));
} finally {
  child.kill('SIGTERM'); await Promise.race([new Promise(resolve => child.once('exit', resolve)), sleep(4000)]);
  if (exitCode === undefined) child.kill('SIGKILL');
  fs.rmSync(cwd, { recursive: true, force: true });
}
