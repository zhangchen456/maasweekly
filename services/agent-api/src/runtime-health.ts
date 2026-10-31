/** Direct-loopback health for deployment verification; never served through a proxy. */
import type {IncomingMessage, ServerResponse} from 'node:http';
import path from 'node:path';
import type {DatasetHolder} from './dataset.js';
import {freshnessSummary} from './observability.js';

export function runtimeIdentity(directory = '') {
  const name = path.basename(directory);
  return /^[a-f0-9]{40}$/.test(name) || /^rl_[a-f0-9]{10}_[a-f0-9]{12}$/.test(name) ? name : 'local';
}

export function runtimeHealth(holder: DatasetHolder, processCode: string) {
  const dataset = holder.current, site = dataset?.manifest.site;
  return {
    schemaVersion: 1, processCode,
    ready: Boolean(dataset && site && !holder.lastReloadError),
    publication: dataset && site ? {
      datasetVersion: dataset.version, inputVersion: site.inputVersion,
      codeCommit: site.codeCommit, formatVersion: site.formatVersion,
    } : null,
    lastReloadAt: holder.lastReloadAt,
    lastReloadError: holder.lastReloadError ? 'dataset_load_failed' : null,
    dataThrough: dataset?.dataThrough ?? null,
    latestWeeklyId: dataset?.status.weekly.latestId ?? null,
    freshness: freshnessSummary(holder),
  };
}

export function createRuntimeHealthHandler(holder: DatasetHolder, processCode: string) {
  return (req: IncomingMessage, res: ServerResponse) => {
    const direct = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress ?? '')
      && /^127\.0\.0\.1:\d+$/.test(req.headers.host ?? '')
      && !req.headers['x-maas-client-ip'] && !req.headers['x-forwarded-for'] && !req.headers.forwarded;
    if (!direct || req.method !== 'GET' || req.url !== '/_runtime/health') {
      res.writeHead(404, {'Cache-Control': 'no-store'}); res.end(); return;
    }
    const value = runtimeHealth(holder, processCode);
    // Return diagnostic state even when not ready; the verifier must inspect ready and all versions.
    res.writeHead(200, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'});
    res.end(JSON.stringify(value));
  };
}
