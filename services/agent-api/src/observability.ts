/** Internal diagnostics. Fixed routes, no URL/query/IP/body fields. */
import { AsyncLocalStorage } from 'node:async_hooks';
import { randomUUID } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Writable } from 'node:stream';
import type { DatasetHolder } from './dataset.js';

export type Diagnostic = Record<string, unknown> & { kind: string };
export type EventSink = (event: Diagnostic) => void;
interface Context { requestId: string; datasetVersion: string | null }
const context = new AsyncLocalStorage<Context>();
export function markDataset(version: string | null): void {
  const active = context.getStore(); if (active) active.datasetVersion = version;
}

export function routeTemplate(url: string | undefined): string {
  const route = (url ?? '').split('?')[0];
  if (route === '/api/mcp') return '/api/mcp';
  if (/^\/api\/v1\/(changes|prices|models|status|weekly)$/.test(route!)) return route!;
  const match = /^\/api\/v1\/(items|evidence|weekly)\/[^/]+$/.exec(route!);
  return match ? `/api/v1/${match[1]}/{id}` : 'unknown';
}

export function instrumentRequest<T>(handler: (req: IncomingMessage, res: ServerResponse) => T,
  holder: DatasetHolder, releaseId: string, sink?: EventSink): (req: IncomingMessage, res: ServerResponse) => T {
  if (!sink) return handler;
  return (req, res) => {
    const state = { requestId: randomUUID(), datasetVersion: holder.current?.version ?? null };
    const started = performance.now(), route = routeTemplate(req.url);
    if (route === '/api/mcp') res.setHeader('X-Request-Id', state.requestId);
    const method = ['GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'DELETE'].includes(req.method ?? '') ? req.method! : 'OTHER';
    res.once('finish', () => {
      try { sink({ kind: 'api.request', requestId: String(res.getHeader('X-Request-Id') ?? state.requestId),
        route, method, releaseId, datasetVersion: state.datasetVersion, statusCode: res.statusCode,
        elapsedMs: Math.round((performance.now() - started) * 1000) / 1000 }); } catch { /* diagnostics never fail a response */ }
    });
    return context.run(state, () => handler(req, res));
  };
}

/** Bound both our queue and Writable buffering; never sync-write diagnostic files. */
export class JsonlLogger {
  #queue: string[] = [];
  #queuedBytes = 0;
  #scheduled = false;
  #paused = false;
  #closed = false;
  #broken = false;
  dropped = 0;
  failedWrites = 0;
  constructor(private output: Writable = process.stdout, private maxBytes = 262144) {
    output.on('error', this.onError);
  }
  private onError = () => { this.failedWrites++; this.#broken = true; this.dropped += this.#queue.length;
    this.#queue = []; this.#queuedBytes = 0; this.output.removeListener('drain', this.resume); };
  private resume = () => { this.#paused = false; this.schedule(); };
  get state() { return { queuedBytes: this.#queuedBytes, dropped: this.dropped, failedWrites: this.failedWrites }; }
  emit = (event: Diagnostic): void => {
    if (this.#closed || this.#broken) return;
    try {
      const line = JSON.stringify({ timestamp: new Date().toISOString(), ...event }) + '\n';
      const bytes = Buffer.byteLength(line);
      if (bytes > 8192 || this.#queuedBytes + bytes > this.maxBytes) { this.dropped++; return; }
      this.#queue.push(line); this.#queuedBytes += bytes; this.schedule();
    } catch { this.dropped++; }
  };
  private schedule(): void {
    if (this.#scheduled || this.#paused || this.#broken) return;
    this.#scheduled = true;
    setImmediate(() => {
      this.#scheduled = false;
      for (let i = 0; i < 50 && this.#queue.length; i++) {
        const line = this.#queue.shift()!; this.#queuedBytes -= Buffer.byteLength(line);
        try {
          if (!this.output.write(line, error => { if (error) this.onError(); })) {
            this.#paused = true; this.output.once('drain', this.resume); return;
          }
        } catch { this.onError(); return; }
      }
      if (this.#queue.length) this.schedule();
    });
  }
  async close(): Promise<void> {
    this.#closed = true;
    const deadline = performance.now() + 1000;
    while (this.#queue.length && !this.#broken && performance.now() < deadline) await new Promise(r => setTimeout(r, 5));
    this.dropped += this.#queue.length; this.#queue = []; this.#queuedBytes = 0;
    this.output.removeListener('drain', this.resume);
    // An stdout EPIPE must never terminate an otherwise healthy service.
  }
}

export function freshnessSummary(holder: DatasetHolder, now = Date.now()) {
  const counts = { fresh: 0, stale: 0, unknown: 0 };
  const ds = holder.current;
  if (!ds) return { alive: true, ready: false, freshness: 'unknown', ...counts };
  const states = [...ds.status.sourceStreams.map(s => ({ state: s.state, at: s.lastSuccessDate ? `${s.lastSuccessDate}T23:59:59+08:00` : null })),
    ...ds.status.priceStreams.map(s => ({ state: s.state, at: s.lastSuccessAt }))];
  for (const source of states) {
    const time = source.at ? Date.parse(source.at) : NaN;
    if (!Number.isFinite(time) || time > now + 86400000) counts.unknown++;
    else if (source.state !== 'ok' || now - time > 48 * 3600000) counts.stale++;
    else counts.fresh++;
  }
  return { alive: true, ready: true, freshness: !states.length ? 'unknown' : counts.stale ? 'stale' : counts.unknown ? 'unknown' : 'fresh', ...counts };
}
