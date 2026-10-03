import { sharedRoutes, localizedRoute } from './locale-routes';
export type Locale = 'zh' | 'en';
export function translatedPaths() { return sharedRoutes; }
export const languageRoute = localizedRoute;
