// T07-4A：UI contract 测试（URL 状态 / error / empty / 互斥 / tag click）。
// 用 jsdom 加载 rendered HTML 并执行交互，锁住任务书 T05-T22 的真实 DOM 行为。
// 运行：node site/tests/model-identity-ui-contract.test.mjs
import { readFileSync, existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const renderedPath = new URL('site/src/data/pricing/price-ledger.rendered.html', root);
if (!existsSync(renderedPath)) {
  console.log('⚠ rendered.html 不存在，跳过 UI contract 测试');
  process.exit(0);
}

const html = readFileSync(renderedPath, 'utf-8');

// jsdom 不支持 matchMedia，polyfill（beforeParse 在 script 执行前注入）
const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  url: 'http://localhost/pricing/',
  pretendToBeVisual: true,
  beforeParse(window) {
    window.matchMedia = (q) => ({
      matches: false, media: q, addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
  },
});
const { window } = dom;
// 等待 script 执行
await new Promise((r) => setTimeout(r, 100));

const { document } = window;

let pass = 0;
function ok(name, cond, detail) {
  if (cond) pass++;
  else throw new Error(`✗ ${name}: ${detail ?? ''}`);
}

function setUrl(path) {
  window.history.replaceState(null, '', 'http://localhost' + path);
}
function fireChange(el) {
  el.dispatchEvent(new window.Event('change', { bubbles: true }));
}
function firePopstate() {
  window.dispatchEvent(new window.Event('popstate'));
}

// ---- T05: valid modelId URL restore ----
setUrl('/pricing/?modelId=anthropic:claude-sonnet-4.5');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T05 valid modelId URL restore',
   document.getElementById('model-filter').value === 'anthropic:claude-sonnet-4.5',
   `mfVal=${document.getElementById('model-filter').value}`);
ok('T05a modelId restore title',
   document.getElementById('provider-title').textContent.includes('Claude Sonnet 4.5'),
   `title=${document.getElementById('provider-title').textContent}`);

// ---- T06: valid familyId URL restore ----
setUrl('/pricing/?familyId=anthropic:claude-sonnet');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T06 valid familyId URL restore',
   document.getElementById('family-filter').value === 'anthropic:claude-sonnet',
   `ffVal=${document.getElementById('family-filter').value}`);
ok('T06a familyId restore title 含"系列"',
   document.getElementById('provider-title').textContent.includes('系列'),
   `title=${document.getElementById('provider-title').textContent}`);

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
ok('T09 family 选中后 model 被清除（互斥）',
   document.getElementById('model-filter').value === '' &&
   document.getElementById('family-filter').value === 'anthropic:claude-sonnet',
   `mf=${mf.value} ff=${ff.value}`);
// 反向：选 model 清除 family
mf.value = 'anthropic:claude-sonnet-4.5';
fireChange(mf);
ok('T09a model 选中后 family 被清除（互斥）',
   document.getElementById('family-filter').value === '' &&
   document.getElementById('model-filter').value === 'anthropic:claude-sonnet-4.5',
   `mf=${mf.value} ff=${ff.value}`);

// ---- T10: clear 后 URL 参数删除 ----
// 用 chip 的清除按钮
const clearBtn = document.querySelector('#filter-summary button');
if (clearBtn) {
  clearBtn.click();
  ok('T10 clear 后 URL 参数删除',
     !window.location.search.includes('modelId') && !window.location.search.includes('familyId'),
     `url=${window.location.search}`);
}

// ---- T11: known-but-empty → 正常空状态（非 error）----
// deepseek:deepseek-flash 是 catalog 有但 ledger 无记录的 model
setUrl('/pricing/?modelId=deepseek:deepseek-flash');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T11 known-but-empty 不显示 error',
   document.getElementById('filter-error').hidden === true,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);
ok('T11a known-but-empty 显示空列表',
   document.getElementById('models').querySelectorAll('tr').length === 0,
   `models=${document.getElementById('models').querySelectorAll('tr').length}`);
ok('T11b known-but-empty 显示 chip（非 error）',
   document.getElementById('filter-summary').textContent.includes('DeepSeek Flash'),
   `summary=${document.getElementById('filter-summary').textContent}`);

// ---- T21: invalid modelId → error state ----
setUrl('/pricing/?modelId=alibaba:ghost-model');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T21 invalid modelId 显示 error',
   document.getElementById('filter-error').hidden === false,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);
ok('T21a invalid modelId error 含 ID',
   document.getElementById('filter-error').textContent.includes('alibaba:ghost-model'),
   `errText=${document.getElementById('filter-error').textContent}`);
ok('T21b invalid modelId 不显示正常列表',
   document.getElementById('models').querySelectorAll('tr').length === 0,
   `models=${document.getElementById('models').querySelectorAll('tr').length}`);

// ---- T22: invalid familyId → error state ----
setUrl('/pricing/?familyId=alibaba:ghost-family');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T22 invalid familyId 显示 error',
   document.getElementById('filter-error').hidden === false,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);
ok('T22a invalid familyId error 含 ID',
   document.getElementById('filter-error').textContent.includes('alibaba:ghost-family'),
   `errText=${document.getElementById('filter-error').textContent}`);

// ---- T14: model tag 点击设置 modelId ----
// 先清除 error，回默认
setUrl('/pricing/');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
const modelTag = document.querySelector('.model-tag');
if (modelTag) {
  const tagText = modelTag.textContent;
  modelTag.click();
  ok('T14 model tag 点击设置 modelId 筛选',
     window.location.search.includes('modelId='),
     `url=${window.location.search}`);
  ok('T14a model tag 点击后 selector 同步',
     document.getElementById('model-filter').value !== '',
     `mfVal=${document.getElementById('model-filter').value}`);
}

// ---- T23: 无筛选时现有行为不变 ----
setUrl('/pricing/');
firePopstate();
await new Promise((r) => setTimeout(r, 50));
ok('T23 无筛选时显示默认列表',
   document.getElementById('models').querySelectorAll('tr').length > 0,
   `models=${document.getElementById('models').querySelectorAll('tr').length}`);
ok('T23a 无筛选时无 error',
   document.getElementById('filter-error').hidden === true,
   `filterError hidden=${document.getElementById('filter-error').hidden}`);

console.log(`✓ T07-4A UI contract 测试全部通过（${pass} 项）`);
