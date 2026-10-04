// @ts-check
import { defineConfig } from 'astro/config';
import { SITE_CANONICAL } from './src/config/public-access.ts';
import privateWeekly from './scripts/private-weekly.mjs';
import seoSitemap from './scripts/seo-sitemap.mjs';

// https://astro.build/config
export default defineConfig({
  site: SITE_CANONICAL,
  vite: { server: { proxy: {
    '/api/pro/': 'http://127.0.0.1:8787',
    '/api/account/': 'http://127.0.0.1:8787',
    '/api/v1/': 'http://127.0.0.1:8787',
  } } },
  integrations: [privateWeekly(),seoSitemap(SITE_CANONICAL)],
  markdown: {
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
