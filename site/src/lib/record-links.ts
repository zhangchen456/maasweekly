import { existsSync } from 'node:fs';
import path from 'node:path';
import { safeWebUrl } from './seo.ts';

/** Legacy daily diffs may have IDs that were never accepted into the archive. */
export function priceChangeLink(change: { id?: string; evidence_url?: string }) {
  if (change.id && /^price_[0-9a-f]{64}$/.test(change.id)
      && existsSync(path.join(process.cwd(), '..', 'data', 'price-records', `${change.id}.json`))) {
    return { href: `/item/${change.id}/`, label: '详情' };
  }
  const source = safeWebUrl(change.evidence_url);
  return source ? { href: source, label: '官方定价' } : { href: '/pricing/', label: '价格台账' };
}
