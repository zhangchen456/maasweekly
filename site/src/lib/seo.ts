import { SITE_CANONICAL } from '../config/public-access.ts';

/** HTML routes use the existing directory/index.html form, without query or fragment. */
export function canonicalUrl(value: string): string {
  const pathname = new URL(value, SITE_CANONICAL).pathname;
  const route = pathname === '/' ? '/' : `${pathname.replace(/\/+$/, '')}/`;
  return new URL(route, SITE_CANONICAL).href;
}

export function safeWebUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}
