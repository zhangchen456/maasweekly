// @ts-check
import node from '@astrojs/node';
import { defineConfig } from 'astro/config';
import { SITE_CANONICAL } from './src/config/public-access.ts';
import privateWeekly from './scripts/private-weekly.mjs';
import seoSitemap from './scripts/seo-sitemap.mjs';

const runtime = process.env.MAAS_SITE_RENDER_MODE === 'server';
// https://astro.build/config
export default defineConfig({
  site: SITE_CANONICAL,
  output: runtime ? 'server' : 'static',
  ...(runtime ? {adapter:node({mode:'middleware'}),session:false} : {}),
  vite: { server: { proxy: {
    '/api/admin/': 'http://127.0.0.1:8787',
    '/api/pro/': 'http://127.0.0.1:8787',
    '/api/account/': 'http://127.0.0.1:8787',
    '/api/v1/': 'http://127.0.0.1:8787',
  } } },
  integrations: runtime ? [{name:'runtime-weekly',hooks:{'astro:config:setup':({injectRoute})=>{
    injectRoute({pattern:'/_internal/weekly-body/[id]',entrypoint:'./src/internal/weekly-body.astro'});
    injectRoute({pattern:'/sitemap.xml',entrypoint:'./src/internal/sitemap.ts'});
    injectRoute({pattern:'/sitemaps/[shard].xml',entrypoint:'./src/internal/sitemap.ts'});
  }}}] : [privateWeekly(),seoSitemap(SITE_CANONICAL)],
  markdown: {
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
