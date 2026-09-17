// @ts-check
import { defineConfig } from 'astro/config';
import { SITE_CANONICAL } from './src/config/public-access.ts';

// https://astro.build/config
export default defineConfig({
  site: SITE_CANONICAL,
  markdown: {
    shikiConfig: {
      theme: 'github-dark',
      wrap: true,
    },
  },
});
