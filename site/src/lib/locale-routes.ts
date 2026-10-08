import type { Locale } from './locales';
export const sharedRoutes = ['/', '/models/', '/pricing/', '/method/', '/agent/', '/subscription/', '/account/', '/feedback/', '/account/unsubscribe/', '/leaderboards/', '/changes/', '/sources/', '/weekly/', '/compare/', '/guides/', '/about/', '/changelog/'];
export function localizedRoute(path: string, locale: Locale) {
  const base = path.replace(/^\/en(?=\/|$)/, '') || '/';
  const normalized = base === '/' ? '/' : `${base.replace(/\/+$/, '')}/`;
  return sharedRoutes.includes(normalized) || /^\/(model|weekly|daily|item|evidence|guides)\/[^/]+\/$/.test(normalized)
    ? (locale === 'en' ? `/en${normalized}` : normalized) : null;
}
