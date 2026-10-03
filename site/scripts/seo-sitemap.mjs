import { readdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const escapeXml = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');

/** Enumerate actual output pages, so the sitemap cannot advertise unbuilt routes. */
export default function seoSitemap(origin) {
  return {
    name: 'maas-seo-sitemap',
    hooks: {
      'astro:build:done': async ({ dir }) => {
        const root = fileURLToPath(dir);
        const urls = new Set();
        async function visit(relative = '') {
          for (const entry of await readdir(path.join(root, relative), { withFileTypes: true })) {
            const file = path.join(relative, entry.name);
            if (entry.isDirectory()) { await visit(file); continue; }
            if (entry.name !== 'index.html') continue;
            const route = '/' + relative.split(path.sep).filter(Boolean).join('/') + (relative ? '/' : '');
            // Evidence and tiny raw observation pages remain reachable through their parent records.
            const baseRoute = route.replace(/^\/en(?=\/)/, '');
            const eligible = /^\/(?:$|(?:models|pricing|leaderboards|changes|weekly|daily|agent|method|about)\/)/.test(baseRoute)
              || baseRoute.startsWith('/model/') || baseRoute.startsWith('/item/');
            if (!eligible) continue;
            const html = await readFile(path.join(root, file), 'utf8');
            if (/<meta\s+name="robots"\s+content="[^"]*noindex/i.test(html)) continue;
            if (baseRoute.startsWith('/item/obs_')) {
              const sourceHtml = route.startsWith('/en/') ? await readFile(path.join(root, baseRoute.slice(1), 'index.html'), 'utf8') : html;
              const summary = sourceHtml.match(/<p\s+class="summary-text"[^>]*>([\s\S]*?)<\/p>/)?.[1];
              if (!summary || summary.replace(/<[^>]*>/g, '').trim().length < 80) continue;
            }
            const canonical = html.match(/<link\s+rel="canonical"\s+href="([^"]+)"/i)?.[1];
            const expected = new URL(route, origin).href;
            if (canonical !== expected) throw new Error(`[seo] canonical mismatch: ${route}`);
            urls.add(expected);
          }
        }
        await visit();
        if (!urls.size) throw new Error('[seo] sitemap has no pages');
        // No reliable page modification timestamps: do not use build time as lastmod.
        const body = [...urls].sort().map(url => `  <url><loc>${escapeXml(url)}</loc></url>`).join('\n');
        await writeFile(path.join(root, 'sitemap.xml'),
          `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`);
        console.log(`[seo] sitemap: ${urls.size} built canonical pages`);
      },
    },
  };
}
