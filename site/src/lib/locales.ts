import { translatedModels } from './model-pages';
export type Locale = 'zh' | 'en';
let paths: string[] | undefined;
export function translatedPaths() {
  return paths ??= ['/', '/models/', '/pricing/', '/method/', '/agent/',
    ...translatedModels().map(p => `/model/${p.model.modelId}/`)];
}
export function languageRoute(path: string, locale: Locale) {
  const base = path.replace(/^\/en(?=\/|$)/, '') || '/';
  const normalized = base === '/' ? '/' : `${base.replace(/\/+$/, '')}/`;
  return translatedPaths().includes(normalized)
    ? (locale === 'en' ? `/en${normalized}` : normalized) : null;
}
