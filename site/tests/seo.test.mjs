import { writePublicFixture } from './public-release-fixture.mjs';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { stripTypeScriptTypes } from 'node:module';
import { XMLParser, XMLValidator } from 'fast-xml-parser';
import { JSDOM } from 'jsdom';
import { canonicalUrl } from '../src/lib/seo.ts';
import { loadVerifiedRelease } from '../src/lib/release.ts';
import { modelPage, featuredModels } from '../src/lib/model-pages.ts';
import { homeModelGroups } from '../src/lib/home-models.ts';
import { priceCells, priceUnit } from '../src/lib/price-display.ts';
import { priceChangeLink } from '../src/lib/record-links.ts';

const dist = path.resolve('dist');
const release = loadVerifiedRelease(undefined, { select: ['prices', 'changes', 'modelIdentities'] });
const htmlFor = route => readFileSync(path.join(dist, route, 'index.html'), 'utf8');
const docFor = route => new JSDOM(htmlFor(route)).window.document;

const archivedPrice = release.prices.find(p => p.links.itemPermalink);
assert(archivedPrice);
assert.equal(priceChangeLink({ id: archivedPrice.links.itemPermalink.split('/')[2] }).href, archivedPrice.links.itemPermalink);
assert.deepEqual(priceChangeLink({ id: 'price_' + '0'.repeat(64), evidence_url: 'https://example.com/pricing' }),
  { href: 'https://example.com/pricing', label: '官方定价' });
assert.deepEqual(priceChangeLink({ id: '../escape', evidence_url: 'javascript:alert(1)' }),
  { href: '/pricing/', label: '价格台账' });

assert.equal(canonicalUrl('/pricing?utm_source=x#prices'), 'https://daily.maas.click/pricing/');
assert.equal(canonicalUrl('https://evil.example/model/deepseek:deepseek-v4-pro/?q=x'),
  'https://daily.maas.click/model/deepseek:deepseek-v4-pro/');
assert.equal(canonicalUrl('/'), 'https://daily.maas.click/');
assert.match(readFileSync(path.join(dist, 'robots.txt'), 'utf8'), /Allow: \/\n\nSitemap: https:\/\/daily\.maas\.click\/sitemap\.xml/);

const xml = readFileSync(path.join(dist, 'sitemap.xml'), 'utf8');
assert.equal(XMLValidator.validate(xml), true);
const urls = new XMLParser().parse(xml).urlset.url.map(entry => entry.loc);
assert.equal(new Set(urls).size, urls.length);
assert(!xml.includes('lastmod'), 'no fabricated modification times');
for (const url of urls) {
  const u = new URL(url);
  assert.equal(u.origin, 'https://daily.maas.click');
  assert.equal(u.search + u.hash, '');
  assert(!u.pathname.startsWith('/evidence/') && !u.pathname.startsWith('/api/'));
  const file = path.join(dist, decodeURIComponent(u.pathname), 'index.html');
  assert(existsSync(file), `unbuilt sitemap URL: ${url}`);
  const html = readFileSync(file, 'utf8');
  assert(!/<meta name="robots" content="[^\"]*noindex/.test(html), url);
  assert.equal(html.match(/<link rel="canonical" href="([^\"]+)"/)?.[1], url);
  for (const match of html.matchAll(/href="(\/item\/[^"?#]+)"/g)) {
    assert(existsSync(path.join(dist, match[1], 'index.html')), `dangling item link in ${url}: ${match[1]}`);
  }
}
for (const route of ['', 'pricing', 'models', 'changes', 'weekly']) {
  const doc = docFor(route);
  assert.equal(doc.querySelectorAll('link[rel=canonical]').length, 1);
  assert(doc.querySelector('meta[name=description]').content.length > 20);
  assert.equal(doc.querySelectorAll('h1').length, 1);
  assert.equal(doc.querySelectorAll('script[data-maas-analytics]').length, 1);
}

const home = docFor('');
assert.equal(home.querySelectorAll('.market-table').length,1,'one shared price table');
assert.equal(home.querySelectorAll('[role=tab]').length,3);
assert.equal(home.querySelectorAll('[role=tab][aria-selected=true]').length,1);
assert.equal(home.querySelector('[data-home-group]:not([hidden])').dataset.homeGroup,'flagship');
assert.equal(home.querySelectorAll('[data-home-model]').length,18);
assert.equal(home.querySelectorAll('[data-quote-amount]').length,36,'all models have input and output quotes');
const featured = featuredModels();
assert(featured.length <= 5, 'only featured models with fresh, complete evidence are promoted');
for (const page of [...featured, modelPage('anthropic:claude-sonnet-4.5')]) {
  const doc = docFor(`model/${page.model.modelId}`);
  assert(!doc.querySelector('.model-detail').textContent.includes('加载中'));
  const rows = [...doc.querySelectorAll('#current-prices tbody tr')];
  assert.equal(rows.length, page.prices.length, 'all model price conditions are rendered');
  assert.equal(doc.querySelector('h1').textContent, `${page.model.modelName} API 价格与变化`);
  for (let i = 0; i < rows.length; i++) {
    const cells = priceCells(page.prices[i]);
    assert.equal(rows[i].querySelectorAll('td').length, 4);
    assert.equal(rows[i].querySelector('td strong').textContent, cells[0]);
    assert.equal(rows[i].querySelector('td .price-subline').textContent, cells[1]);
    assert.equal(rows[i].querySelector('.billing-badge').textContent, cells[2]);
    assert.equal(rows[i].querySelector('.detail-amount').textContent, `${page.prices[i].amount} ${page.prices[i].currency}`);
    assert.equal(rows[i].querySelector('.detail-amount + .price-subline').textContent, `每 ${priceUnit(page.prices[i].unitQuantity, page.prices[i].unitName)}`);
    assert.deepEqual([...rows[i].querySelectorAll('.price-facts dd')].map(dd => dd.textContent), cells.slice(4), 'all source conditions remain in details');
    assert.equal(rows[i].dataset.priceId, page.prices[i].id);
    for (const a of rows[i].querySelectorAll('a')) assert(existsSync(path.join(dist, a.getAttribute('href'), 'index.html')));
  }
  assert.equal(doc.querySelectorAll('#recent-changes .change-card').length, page.changes.length);
  if (page.prices.some(p => p.quality.state === 'stale')) assert(doc.querySelector('#current-prices').textContent.includes('沿用旧数据'));
}
const empty = release.modelIdentities.models.find(m => !release.prices.some(p => p.modelId === m.modelId)
  && modelPage(m.modelId).changes.length === 0);
assert(empty);
assert.match(docFor(`model/${empty.modelId}`).querySelector('meta[name=robots]').content, /noindex/);
assert(!urls.includes(canonicalUrl(`/model/${empty.modelId}/`)));
assert(!existsSync(path.join(dist, 'model/unknown:ghost/index.html')));
for (const route of ['', 'pricing', 'models']) {
  const doc = docFor(route);
  if (route === '') for (const group of homeModelGroups()) for (const page of group.models) {
    assert(doc.querySelector(`[data-home-model="${page.pick.modelId}"]`));
    if (page.modelHref) assert(doc.querySelector(`a[href="${page.modelHref}"]`));
  }
  else for (const page of featured) assert(doc.querySelector(`a[href="/model/${page.model.modelId}/"]`));
}

// Exercise the actual refresh implementation, including cursor pagination and failure fallback.
const source = readFileSync('src/scripts/model-refresh.ts', 'utf8').replace(/^import .*;\n/gm, '');
const runtime = stripTypeScriptTypes(source, { mode: 'strip' });
async function refreshScenario(kind) {
  const page = modelPage('alibaba:qwen-plus');
  const dom = new JSDOM(htmlFor(`model/${page.model.modelId}`), { runScripts: 'outside-only', url: 'https://daily.maas.click/model/alibaba:qwen-plus/' });
  const win = dom.window;
  const calls = [];
  win.priceCells = priceCells;
  win.priceUnit = priceUnit;
  win.priceHeaders = (await import('../src/lib/price-display.ts')).priceHeaders;
  win.fetch = async value => {
    calls.push(value);
    if (kind === 'offline') throw new Error('offline');
    const u = new URL(value, win.location.href);
    const offset = Number(u.searchParams.get('cursor') || 0);
    const isPrices = u.pathname.endsWith('/prices');
    if (!u.searchParams.has('cursor')) assert.equal(u.searchParams.get('modelId'), page.model.modelId);
    else assert.equal([...u.searchParams].length, 1);
    return { ok: true, json: async () => ({
      datasetVersion: kind === 'version' ? 'ds_other' : release.datasetVersion,
      items: isPrices ? page.prices.slice(offset, offset + 20) : page.changes,
      page: { nextCursor: isPrices && offset + 20 < page.prices.length ? String(offset + 20) : null },
    }) };
  };
  win.eval(runtime);
  const before = win.document.getElementById('current-prices').innerHTML;
  assert.equal(calls.length, 0, 'static content does not require a browser API call');
  win.document.getElementById('refresh-model').click();
  for (let i = 0; i < 100 && win.document.getElementById('refresh-model').disabled; i++) await new Promise(r => setTimeout(r, 10));
  assert.equal(win.document.getElementById('refresh-model').disabled, false);
  if (kind === 'ok') {
    assert.equal(calls.length, Math.ceil(page.prices.length / 20) + 1);
    assert.equal(win.document.querySelectorAll('#current-prices tbody tr').length, page.prices.length);
    assert.equal(win.document.querySelector('#current-prices td strong').textContent, priceCells(page.prices[0])[0]);
    assert.match(win.document.getElementById('refresh-status').textContent, /已核对/);
  } else {
    assert.equal(win.document.getElementById('current-prices').innerHTML, before);
    assert.match(win.document.getElementById('refresh-status').textContent, /已保留/);
  }
  dom.window.close();
}
await refreshScenario('ok'); await refreshScenario('offline'); await refreshScenario('version');

// New price/evidence reads must retain the signed release's integrity checks.
const fixture = mkdtempSync(path.join(tmpdir(), 'maas-seo-integrity-'));
try {
  const version = 'ds_' + 'a'.repeat(64);
  mkdirSync(path.join(fixture, 'releases', version), { recursive: true });
  for (const collection of ['prices', 'evidence']) {
    const relative = `releases/${version}/${collection}.json`;
    const data = Buffer.from('[{"id":"fixture"}]');
    const entry = { path: relative, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex') };
    writeFileSync(path.join(fixture, relative), data);
    const manifest = writePublicFixture(fixture, version, { [collection]: [{ id: 'fixture' }] });
    writeFileSync(path.join(fixture, 'manifest.json'), JSON.stringify(manifest));
    assert.equal(loadVerifiedRelease(fixture, { select: [collection] })[collection][0].id, 'fixture');
    writeFileSync(path.join(fixture, relative), '[{"id":"tamper!"}]');
    assert.throws(() => loadVerifiedRelease(fixture, { select: [collection] }), /bytes|sha256/);
    writeFileSync(path.join(fixture, 'manifest.json'), JSON.stringify({ ...manifest, files: [] }));
    assert.throws(() => loadVerifiedRelease(fixture, { select: [collection] }), /不在 manifest/);
  }
} finally { rmSync(fixture, { recursive: true, force: true }); }
console.log(`✓ SEO: ${urls.length} sitemap routes, five featured models, full price conditions, no-JS content, refresh pagination/fallback and release integrity`);
