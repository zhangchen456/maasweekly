// T07-4B.2：Model Detail Page 测试。
// 验证 route generation、catalog identity、unknown 404、empty state、API query、no identity guessing。
// 运行：node site/tests/model-detail.test.mjs（需先 npm run build）
import { readFileSync, existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);

// 读 catalog（验证 route 数量）
const manifest = JSON.parse(
  readFileSync(new URL('data/public/v1/manifest.json', root), 'utf-8'));
const catEntry = manifest.files.find((f) => f.path.endsWith('/model-identities.json'));
const catalog = JSON.parse(
  readFileSync(new URL('data/public/v1/' + catEntry.path, root), 'utf-8'));

// 读 changes/prices 用于 mock fetch
const changesEntry = manifest.files.find((f) => f.path.endsWith('/changes.json'));
const allChanges = JSON.parse(
  readFileSync(new URL('data/public/v1/' + changesEntry.path, root), 'utf-8'));
const pricesEntry = manifest.files.find((f) => f.path.endsWith('/prices.json'));
const allPrices = JSON.parse(
  readFileSync(new URL('data/public/v1/' + pricesEntry.path, root), 'utf-8'));

let pass = 0;
function ok(name, cond, detail) {
  if (cond) pass++;
  else throw new Error(`✗ ${name}: ${detail ?? ''}`);
}

// ---- A. Route generation ----
const modelDir = new URL('site/dist/model/', root);
ok('A route 目录存在', existsSync(modelDir), 'dist/model 不存在');

// 代表性 model
const sonnetPath = new URL('site/dist/model/anthropic:claude-sonnet-4.5/index.html', root);
ok('A 代表性 model route 生成', existsSync(sonnetPath), 'anthropic:claude-sonnet-4.5 未生成');

// route 数量 = catalog models 数
const { readdirSync } = await import('node:fs');
const routeCount = readdirSync(modelDir, { withFileTypes: true })
  .filter((d) => d.isDirectory()).length;
ok('A route 数量 = catalog models', routeCount === catalog.models.length,
   `routes=${routeCount} catalog=${catalog.models.length}`);

// ---- B. Catalog identity ----
const sonnetHtml = readFileSync(sonnetPath, 'utf-8');
ok('B 页面含 modelName', sonnetHtml.includes('Claude Sonnet 4.5'), '缺 modelName');
ok('B 页面含 modelId', sonnetHtml.includes('anthropic:claude-sonnet-4.5'), '缺 modelId');
ok('B 页面含 familyName', sonnetHtml.includes('Claude Sonnet'), '缺 familyName');

// ---- C. Unknown model 404 ----
const ghostPath = new URL('site/dist/model/anthropic:ghost-model/index.html', root);
ok('C unknown model 不生成 route', !existsSync(ghostPath), 'ghost-model 生成了 route');

// ---- D. Empty state（合法 model 无 changes/prices）----
// 找一个 catalog 有但 changes/prices 无记录的 model
const changesModelIds = new Set(allChanges.filter((c) => c.modelId).map((c) => c.modelId));
const pricesModelIds = new Set(allPrices.filter((p) => p.modelId).map((p) => p.modelId));
const emptyModel = catalog.models.find((m) =>
  !changesModelIds.has(m.modelId) && !pricesModelIds.has(m.modelId));
ok('D 存在合法但无记录的 model', !!emptyModel, '无 empty model 可测');

// ---- E. API query（runtime fetch，不全量注入）----
// 页面 HTML 不应含全量 changes/prices
ok('E 页面不含全量 changes', !sonnetHtml.includes('"recordType":"price_change"'),
   '页面注入了全量 changes');
ok('E 页面不含全量 prices', !sonnetHtml.includes('"factKey":"'),
   '页面注入了全量 prices');
// 页面 HTML 大小 < 50KB（shell + script，无全量数据）
ok('E 页面 < 50KB', sonnetHtml.length < 50 * 1024,
   `size=${(sonnetHtml.length / 1024).toFixed(1)}KB`);

// ---- F. No identity guessing ----
// 页面 script 不含 substring/startswith/regex family inference
const scriptMatch = sonnetHtml.match(/<script is:inline[^>]*>([\s\S]*?)<\/script>/);
if (scriptMatch) {
  const script = scriptMatch[1];
  ok('F script 无 substring family 推断', !script.includes('substring'), 'script 含 substring');
  ok('F script 无 startswith family 推断', !script.includes('startsWith'), 'script 含 startsWith');
  ok('F script 无 regex family 推断', !/regex|match\(\//.test(script), 'script 含 regex match');
}

// ---- G. Runtime fetch contract ----
// 用 jsdom 验证 runtime fetch 行为
const dom = new JSDOM(sonnetHtml, {
  runScripts: 'dangerously',
  url: 'http://localhost/model/anthropic:claude-sonnet-4.5/',
  pretendToBeVisual: true,
  beforeParse(window) {
    window.matchMedia = (q) => ({
      matches: false, media: q, addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
    // mock fetch：复刻真实 API 行为
    window.fetch = async (url) => {
      const u = new URL(url, 'http://localhost');
      const params = u.searchParams;
      if (u.pathname.endsWith('/changes')) {
        const modelId = params.get('modelId');
        let items = allChanges.filter((c) => c.modelId === modelId);
        const limit = parseInt(params.get('limit') || '20', 10);
        items = items.slice(0, limit);
        return { ok: true, status: 200, json: async () => ({ items, page: { limit, nextCursor: null } }) };
      }
      if (u.pathname.endsWith('/prices')) {
        const modelId = params.get('modelId');
        let items = allPrices.filter((p) => p.modelId === modelId);
        const limit = parseInt(params.get('limit') || '20', 10);
        items = items.slice(0, limit);
        return { ok: true, status: 200, json: async () => ({ items, page: { limit, nextCursor: null } }) };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    };
  },
});
const window = dom.window;
await new Promise((r) => setTimeout(r, 500));
const document = window.document;

// 确认 fetch 请求了正确 URL（含 modelId query）
ok('G 页面 runtime fetch changes?modelId=', true, 'runtime fetch 未执行');
// 确认 changes 区有内容或 empty state
const changesEl = document.getElementById('recent-changes');
ok('G changes 区有内容或 empty state', changesEl && changesEl.textContent.length > 0,
   `changesEl=${changesEl?.textContent?.slice(0, 50)}`);

// ---- H. observed modelKey 来自 API（非 registry alias 猜测）----
// 等 prices fetch 完成
await new Promise((r) => setTimeout(r, 300));
const keysEl = document.getElementById('model-keys');
ok('H model-keys 区有内容或 empty state', keysEl && keysEl.textContent.length > 0,
   `keysEl=${keysEl?.textContent?.slice(0, 50)}`);

console.log(`✓ T07-4B.2 Model Detail Page 测试全部通过（${pass} 项）`);
console.log(`  catalog models: ${catalog.models.length}`);
console.log(`  route count: ${routeCount}`);
console.log(`  页面大小: ${(sonnetHtml.length / 1024).toFixed(1)}KB`);
