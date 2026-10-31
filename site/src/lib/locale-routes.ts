import type { Locale } from './locales';
export const sharedRoutes = ['/', '/models/', '/pricing/', '/method/', '/agent/', '/subscription/', '/subscription/payments/', '/subscription/sandbox/', '/account/', '/feedback/', '/account/unsubscribe/', '/pro/', '/pro/weekly/', '/pro/unsubscribe/', '/leaderboards/', '/changes/', '/sources/', '/weekly/', '/compare/', '/guides/', '/about/', '/changelog/'];
export function localizedRoute(path: string, locale: Locale) {
  const base = path.replace(/^\/en(?=\/|$)/, '') || '/';
  const normalized = base === '/' ? '/' : `${base.replace(/\/+$/, '')}/`;
  return sharedRoutes.includes(normalized) || /^\/(model|weekly|daily|item|evidence|guides)\/[^/]+\/$/.test(normalized)
    ? (locale === 'en' ? `/en${normalized}` : normalized) : null;
}
export function localizedHref(href: string, locale: Locale) {
  if (!href.startsWith('/') || href.startsWith('//')) return href;
  const match=href.match(/^([^?#]*)([?#].*)?$/)!;
  return (localizedRoute(match[1],locale) ?? match[1])+(match[2] ?? '');
}
