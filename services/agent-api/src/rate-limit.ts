import type { IncomingMessage } from 'node:http';
import { isIP } from 'node:net';

export interface RateLimitConfig {
  capacity: number;
  refillPerMinute: number;
  globalCapacity?: number;
  globalRefillPerMinute?: number;
  maxClients?: number;
  idleTtlMs?: number;
  trustLoopbackProxy?: boolean;
}

export class TokenBucket {
  #tokens: number;
  #last: number;
  constructor(private capacity: number, private refillPerMin: number, private clock = Date.now) {
    if (!Number.isFinite(capacity) || capacity <= 0 || !Number.isFinite(refillPerMin) || refillPerMin <= 0) throw new Error('invalid rate-limit budget');
    this.#tokens = capacity; this.#last = clock();
  }
  take(): boolean {
    const now = this.clock();
    this.#tokens = Math.min(this.capacity, this.#tokens + Math.max(0, now - this.#last) / 60000 * this.refillPerMin);
    this.#last = now;
    if (this.#tokens >= 1) { this.#tokens--; return true; }
    return false;
  }
  retryAfterSeconds(): number { return Math.max(1, Math.ceil((1 - this.#tokens) / (this.refillPerMin / 60))); }
}

export function normalizeClientIp(ip: string): string | null {
  const kind = isIP(ip);
  if (kind === 4) return ip;
  if (kind !== 6 || ip.includes('%')) return null;
  const value = new URL(`http://[${ip}]`).hostname.slice(1, -1).toLowerCase();
  const mapped = /^::ffff:([0-9a-f]+):([0-9a-f]+)$/.exec(value);
  if (mapped) {
    const a = parseInt(mapped[1]!, 16), b = parseInt(mapped[2]!, 16);
    return `${a >>> 8}.${a & 255}.${b >>> 8}.${b & 255}`;
  }
  return value;
}

export function clientKey(req: Pick<IncomingMessage, 'socket' | 'headers'>, trustLoopbackProxy = false): string {
  const peer = normalizeClientIp(req.socket.remoteAddress ?? '') ?? 'unknown';
  if (trustLoopbackProxy && (peer === '127.0.0.1' || peer === '::1')) {
    const header = req.headers['x-maas-client-ip'];
    const ip = typeof header === 'string' && header.length <= 45 ? normalizeClientIp(header) : null;
    if (ip) return ip;
  }
  return peer;
}

/** Per-client buckets are bounded; rejected client traffic never drains the global guard. */
export class ClientRateLimiter {
  #clients = new Map<string, { bucket: TokenBucket; lastSeen: number }>();
  #global: TokenBucket;
  #overflow: TokenBucket;
  #nextSweep = 0;
  #max: number;
  #ttl: number;
  constructor(private config: RateLimitConfig, private clock = Date.now) {
    this.#global = new TokenBucket(config.globalCapacity ?? Math.max(1000, config.capacity * 100), config.globalRefillPerMinute ?? Math.max(1000, config.refillPerMinute * 100), clock);
    this.#overflow = new TokenBucket(config.capacity, config.refillPerMinute, clock);
    this.#max = config.maxClients ?? 10000; this.#ttl = config.idleTtlMs ?? 300000;
    if (!Number.isSafeInteger(this.#max) || this.#max < 1 || !Number.isFinite(this.#ttl) || this.#ttl <= 0) throw new Error('invalid client bucket budget');
  }
  get size(): number { return this.#clients.size; }
  take(req: Pick<IncomingMessage, 'socket' | 'headers'>): { allowed: boolean; retryAfterSeconds: number } {
    const now = this.clock();
    if (now >= this.#nextSweep) {
      for (const [key, entry] of this.#clients) if (now - entry.lastSeen >= this.#ttl) this.#clients.delete(key);
      this.#nextSweep = now + Math.min(this.#ttl, 30000);
    }
    const key = clientKey(req, this.config.trustLoopbackProxy);
    let entry = this.#clients.get(key);
    if (!entry && this.#clients.size < this.#max) {
      entry = { bucket: new TokenBucket(this.config.capacity, this.config.refillPerMinute, this.clock), lastSeen: now };
      this.#clients.set(key, entry);
    }
    if (entry) entry.lastSeen = now;
    const bucket = entry?.bucket ?? this.#overflow;
    if (!bucket.take()) return { allowed: false, retryAfterSeconds: bucket.retryAfterSeconds() };
    if (!this.#global.take()) return { allowed: false, retryAfterSeconds: this.#global.retryAfterSeconds() };
    return { allowed: true, retryAfterSeconds: 0 };
  }
}
