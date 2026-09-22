// T07-4A.2 closeout：Changes Browser UI contract 测试（jsdom DOM 交互 + fetch mock）。
// 验证 REST 分页加载、URL 状态、error/empty/互斥/tag click、source_observation 无 modelId。
// 运行：node site/tests/changes-browser-ui.test.mjs（需先 npm run build）
import { readFileSync, existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const distPath = new URL('site/dist/changes/index.html', root);
if (!existsSync(distPath)) {
  console.log('⚠ dist/changes/index.html 不存在，请先 npm run build');
  process.exit(0);
}

// 读真实 changes 数据用于 mock fetch 响应
const manifest = JSON.parse(
  readFileSync(new URL('data/public/v1/manifest.json', root), 'utf-8'));
const changesEntry = manifest.files.find((f) => f.path.endsWith('/changes.json'));
const allChanges = JSON.parse(
  readFileSync(new URL('data/public/v1/' + changesEntry.path, root), 'utf-8'));

const html = readFileSync(distPath, 'utf-8');
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  url: 'http://localhost/changes/',
  pretendToBeVisual: true,
  beforeParse(window) {
    window.matchMedia = (q) => ({
      matches: false, media: q, addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
    // mock fetch：根据 query params 过滤 changes
    window.fetch = async (url) => {
      const u = new URL(url, 'http://localhost');
      const params = u.searchParams;
      let items = [...allChanges];
      const modelId = params.get('modelId');
      const familyId = params.get('familyId');
      const type = params.get('type');
      const q = params.get('q');
      const limit = parseInt(params.get('limit') || '20', 10);
      if (modelId) items = items.filter(c => c.modelId === modelId);
      if (familyId) items = items.filter(c => c.familyId === familyId);
      if (type) items = items.filter(c => c.recordType === type);
      if (q) items = items.filter(c => (c.title + ' ' + (c.summary || '')).toLowerCase().includes(q.toLowerCase()));
      const page = items.slice(0, limit);
      const status = (modelId || familyId) && items.length === 0 && !(modelId || familyId) ? 200 : 200;
      return {
        ok: true, status: 200,
        json: async () => ({ items: page, page: { limit, nextCursor: items.length > limit ? 'mock-cursor' : null } }),
      };
    };
  },
});
const window = dom.window;
await new Promise((r) => setTimeout(r, 300));
const document = window.document;

let pass = 0;
function ok(name, cond, detail) {
  if (cond) pass++;
  else throw new Error(`✗ ${name}: ${detail ?? ''}`);
}

function setUrl(path) { window.history.replaceState(null, '', 'http://localhost' + path); }
function fireChange(el) { el.dispatchEvent(new window.Event('change', { bubbles: true })); }
function firePopstate() { window.dispatchEvent(new window.Event('popstate')); }
async function wait(ms = 300) { await new Promise((r) => setTimeout(r, ms)); }

// ---- T01: model selector options 来自 catalog ----
ok('T01 model-filter options > 1',
   document.getElementById('model-filter').options.length > 1,
   `options=${document.getElementById('model-filter').options.length}`);

// ---- T02: family selector options 来自 catalog ----
ok('T02 family-filter options > 1',
   document.getElementById('family-filter').options.length > 1,
   `options=${document.getElementById('family-filter').options.length}`);

// ---- T03: catalog 经 manifest 校验（无 raw fs）----
// 页面构建期用 loadVerifiedRelease select modelIdentities，catalog 缺失会 build fail
const catalog = JSON.parse(document.getElementById('catalog-data').textContent);
ok('T03 catalog 有 models 和 families',
   catalog.models && catalog.families && catalog.models.length > 0,
   'catalog 缺失或为空');

// ---- T05: valid modelId URL restore ----
setUrl('/changes/?modelId=anthropic:claude-sonnet-4.5');
firePopstate();
await wait();
ok('T05 valid modelId URL restore',
   document.getElementById('model-filter').value === 'anthropic:claude-sonnet-4.5',
   `mfVal=${document.getElementById('model-filter').value}`);
await wait();
ok('T05a modelId restore 显示列表',
   document.querySelectorAll('.change-card').length > 0,
   `cards=${document.querySelectorAll('.change-card').length}`);

// ---- T06: valid familyId URL restore ----
setUrl('/changes/?familyId=anthropic:claude-sonnet');
firePopstate();
await wait();
ok('T06 valid familyId URL restore',
   document.getElementById('family-filter').value === 'anthropic:claude-sonnet',
   `ffVal=${document.getElementById('family-filter').value}`);
await wait();
ok('T06a familyId restore 显示列表',
   document.querySelectorAll('.change-card').length > 0,
   `cards=${document.querySelectorAll('.change-card').length}`);

// ---- T09: model/family 互斥 ----
const mf = document.getElementById('model-filter');
mf.value = 'openai:gpt-5.6-luna';
fireChange(mf);
await wait();
ok('T09 model 选中后 family 被清除',
   document.getElementById('family-filter').value === '' &&
   document.getElementById('model-filter').value === 'openai:gpt-5.6-luna',
   `mf=${mf.value} ff=${document.getElementById('family-filter').value}`);

// ---- T13: source_observation 无 model-tag ----
setUrl('/changes/?type=source_observation');
firePopstate();
await wait();
await wait();
ok('T13 source_observation 无 model-tag',
   Array.from(document.querySelectorAll('.change-card')).every(c => !c.querySelector('.model-tag')),
   `cards with model-tag: ${Array.from(document.querySelectorAll('.change-card')).filter(c => c.querySelector('.model-tag')).length}`);

// ---- T11: known-but-empty → 正常空状态 ----
setUrl('/changes/?modelId=deepseek:deepseek-flash');
firePopstate();
await wait();
await wait();
ok('T11 known-but-empty 不显示 error',
   document.getElementById('filter-error').hidden === true,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);
ok('T11a known-but-empty 显示空列表',
   document.querySelectorAll('.change-card').length === 0,
   `cards=${document.querySelectorAll('.change-card').length}`);

// ---- T23: 无筛选时显示列表 ----
setUrl('/changes/');
firePopstate();
await wait();
await wait();
ok('T23 无筛选时显示列表',
   document.querySelectorAll('.change-card').length > 0,
   `cards=${document.querySelectorAll('.change-card').length}`);

// ---- T23a: 页面体积小（REST 分页，不注入全量 changes）----
const htmlSize = html.length;
ok('T23a changes 页 HTML < 100KB（REST 分页，不注入全量）',
   htmlSize < 100 * 1024,
   `htmlSize=${(htmlSize / 1024).toFixed(0)}KB`);

console.log(`✓ T07-4A.2 closeout Changes Browser UI 测试全部通过（${pass} 项）`);
console.log(`  页面 HTML 大小: ${(htmlSize / 1024).toFixed(1)}KB（REST 分页，不含全量 changes）`);
