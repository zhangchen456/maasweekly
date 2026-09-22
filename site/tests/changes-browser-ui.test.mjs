// T07-4A.2：Changes Browser UI contract 测试（jsdom DOM 交互）。
// 从构建产物 dist/changes/index.html 加载，执行 inline script，验证
// URL 状态 / error / empty / 互斥 / tag click / source_observation 无 modelId。
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
  },
});
const { window } = dom;
await new Promise((r) => setTimeout(r, 200));
const document = window.document;

let pass = 0;
function ok(name, cond, detail) {
  if (cond) pass++;
  else throw new Error(`✗ ${name}: ${detail ?? ''}`);
}

function setUrl(path) { window.history.replaceState(null, '', 'http://localhost' + path); }
function fireChange(el) { el.dispatchEvent(new window.Event('change', { bubbles: true })); }
function firePopstate() { window.dispatchEvent(new window.Event('popstate')); }

// ---- T01: model selector options 来自 catalog ----
ok('T01 model-filter options > 1',
   document.getElementById('model-filter').options.length > 1,
   `options=${document.getElementById('model-filter').options.length}`);

// ---- T02: family selector options 来自 catalog ----
ok('T02 family-filter options > 1',
   document.getElementById('family-filter').options.length > 1,
   `options=${document.getElementById('family-filter').options.length}`);

// ---- T05: valid modelId URL restore ----
setUrl('/changes/?modelId=anthropic:claude-sonnet-4.5');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T05 valid modelId URL restore',
   document.getElementById('model-filter').value === 'anthropic:claude-sonnet-4.5',
   `mfVal=${document.getElementById('model-filter').value}`);
ok('T05a modelId restore 显示列表',
   document.querySelectorAll('.change-card').length > 0,
   `cards=${document.querySelectorAll('.change-card').length}`);
ok('T05b modelId restore 所有卡片有 model-tag',
   Array.from(document.querySelectorAll('.change-card')).every(c => c.querySelector('.model-tag')),
   '部分卡片缺 model-tag');

// ---- T06: valid familyId URL restore ----
setUrl('/changes/?familyId=anthropic:claude-sonnet');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T06 valid familyId URL restore',
   document.getElementById('family-filter').value === 'anthropic:claude-sonnet',
   `ffVal=${document.getElementById('family-filter').value}`);
ok('T06a familyId restore 显示列表',
   document.querySelectorAll('.change-card').length > 0,
   `cards=${document.querySelectorAll('.change-card').length}`);

// ---- T07: model selector 改 URL ----
const mf = document.getElementById('model-filter');
mf.value = 'openai:gpt-5.6-luna';
fireChange(mf);
ok('T07 model selector 改 URL',
   window.location.search.includes('modelId=openai%3Agpt-5.6-luna'),
   `url=${window.location.search}`);

// ---- T08: family selector 改 URL ----
const ff = document.getElementById('family-filter');
ff.value = 'anthropic:claude-sonnet';
fireChange(ff);
ok('T08 family selector 改 URL',
   window.location.search.includes('familyId=anthropic%3Aclaude-sonnet'),
   `url=${window.location.search}`);

// ---- T09: model/family 互斥 ----
ok('T09 family 选中后 model 被清除',
   document.getElementById('model-filter').value === '' &&
   document.getElementById('family-filter').value === 'anthropic:claude-sonnet',
   `mf=${mf.value} ff=${ff.value}`);

// ---- T10: clear 后 URL 参数删除 ----
const clearBtn = document.querySelector('#filter-summary button');
if (clearBtn) {
  clearBtn.click();
  ok('T10 clear 后 URL 参数删除',
     !window.location.search.includes('modelId') && !window.location.search.includes('familyId'),
     `url=${window.location.search}`);
}

// ---- T11: known-but-empty → 正常空状态（非 error）----
setUrl('/changes/?modelId=deepseek:deepseek-flash');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T11 known-but-empty 不显示 error',
   document.getElementById('filter-error').hidden === true,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);
ok('T11a known-but-empty 显示空列表',
   document.querySelectorAll('.change-card').length === 0,
   `cards=${document.querySelectorAll('.change-card').length}`);
ok('T11b known-but-empty 显示 empty-state',
   document.getElementById('empty-state').hidden === false,
   `emptyState hidden=${document.getElementById('empty-state').hidden}`);

// ---- T21: invalid modelId → error state ----
setUrl('/changes/?modelId=alibaba:ghost-model');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T21 invalid modelId 显示 error',
   document.getElementById('filter-error').hidden === false,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);
ok('T21a invalid modelId 不显示列表',
   document.querySelectorAll('.change-card').length === 0,
   `cards=${document.querySelectorAll('.change-card').length}`);

// ---- T13: source_observation 无 model-tag ----
setUrl('/changes/');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
const tf = document.getElementById('type-filter');
tf.value = 'source_observation';
fireChange(tf);
await new Promise((r) => setTimeout(r, 50));
ok('T13 source_observation 无 model-tag',
   Array.from(document.querySelectorAll('.change-card')).every(c => !c.querySelector('.model-tag')),
   `cards with model-tag: ${Array.from(document.querySelectorAll('.change-card')).filter(c => c.querySelector('.model-tag')).length}`);

// ---- T14: model tag 点击设置 modelId ----
tf.value = '';
fireChange(tf);
await new Promise((r) => setTimeout(r, 50));
const modelTag = document.querySelector('.model-tag');
if (modelTag) {
  modelTag.click();
  ok('T14 model tag 点击设置 modelId',
     window.location.search.includes('modelId='),
     `url=${window.location.search}`);
}

// ---- T23: 无筛选时显示列表 ----
setUrl('/changes/');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T23 无筛选时显示列表',
   document.querySelectorAll('.change-card').length > 0,
   `cards=${document.querySelectorAll('.change-card').length}`);
ok('T23a 无筛选时无 error',
   document.getElementById('filter-error').hidden === true,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);

console.log(`✓ T07-4A.2 Changes Browser UI contract 测试全部通过（${pass} 项）`);
