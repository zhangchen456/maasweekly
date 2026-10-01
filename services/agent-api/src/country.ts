import type { IncomingMessage, ServerResponse } from 'node:http';
import { createRequire } from 'node:module';
import { isIP } from 'node:net';

const require = createRequire(import.meta.url);
let lookup: (ip: string) => { country: string } | null;
let databaseDate = NaN;
try {
  lookup = require('geoip-country').lookup;
  const date = require('geoip-country/package.json').version.match(/(\d{4})(\d{2})(\d{2})\d{4}$/);
  if (date) databaseDate = Date.parse(`${date[1]}-${date[2]}-${date[3]}T00:00:00Z`);
}
catch { lookup = () => null; }

/** Nginx overwrites this header from its socket peer. The agent binds loopback only. */
export function countryFor(req: Pick<IncomingMessage, 'socket' | 'headers'>): string | null {
  // Stop using old data rather than presenting outdated country mappings.
  if (!Number.isFinite(databaseDate) || Date.now() - databaseDate > 21 * 86400000) return null;
  const peer = req.socket.remoteAddress;
  if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(peer ?? '')) return null;
  const ip = req.headers['x-maas-client-ip'];
  if (typeof ip !== 'string' || ip.length > 45 || !isIP(ip)) return null;
  try {
    const value = lookup(ip)?.country;
    return value && /^[A-Z]{2}$/.test(value) ? value : null;
  } catch { return null; }
}

export function countryHandler(req: IncomingMessage, res: ServerResponse) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.statusCode = 405; res.setHeader('Allow', 'GET, HEAD'); res.end(); return;
  }
  // No addresses, request headers or precise locations are logged or returned.
  res.end(req.method === 'HEAD' ? undefined : JSON.stringify({ country: countryFor(req) }));
}
