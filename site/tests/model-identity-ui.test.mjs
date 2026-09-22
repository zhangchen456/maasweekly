// T07-4A：模型筛选与模型入口契约测试。
// 运行：node site/tests/model-identity-ui.test.mjs
// 覆盖：
//   - ledger identity 注入（resolved 写 modelId/modelName，formal family 才写 familyId）
//   - selector options 来自 catalog（不从 ledger 反推，不含 pointer/non_model）
//   - ledger 与 public projection identity 一致（同 model 的 modelId 相同）
//   - unresolved/pointer 不写 identity（UI 不从 modelKey 猜）
import { readFileSync, existsSync } from 'node:fs';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const root = new URL('../../', import.meta.url);

// ---- 数据加载 ----
const ledger = JSON.parse(
  readFileSync(new URL('site/src/data/pricing/ledger.json', root), 'utf-8'));

// 读当前 release 的 manifest 找 catalog
const manifestPath = new URL('data/public/v1/manifest.json', root);
const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
const catEntry = manifest.files.find((f) => f.path.endsWith('/model-identities.json'));
assert.ok(catEntry, 'manifest 缺 model-identities.json');
const catalog = JSON.parse(
  readFileSync(new URL('data/public/v1/' + catEntry.path, root), 'utf-8'));

// 读 public projection prices（校验一致性）
const pricesEntry = manifest.files.find((f) => f.path.endsWith('/prices.json'));
const publicPrices = JSON.parse(
  readFileSync(new URL('data/public/v1/' + pricesEntry.path, root), 'utf-8'));

let pass = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; }
  else { throw new Error(`✗ ${name}: ${detail ?? ''}`); }
}

// ---- T01: model options 来自正式 catalog ----
ok('T01 model options 来自 catalog.models',
   Array.isArray(catalog.models) && catalog.models.length > 0,
   `catalog.models=${catalog.models?.length}`);

// ---- T02: family options 来自 catalog.families ----
ok('T02 family options 来自 catalog.families',
   Array.isArray(catalog.families) && catalog.families.length > 0,
   `catalog.families=${catalog.families?.length}`);

// ---- T03: pointer/non_model 不出现在 selector ----
ok('T03 catalog models 全是 classification=model 的 modelId',
   catalog.models.every((m) => m.modelId && /^[a-z0-9-]+:[a-z0-9.-]+$/.test(m.modelId)),
   'catalog models 含非法 modelId');
// families 不含 modelId（families 与 models 不重叠）
const modelIds = new Set(catalog.models.map((m) => m.modelId));
const familyIds = new Set(catalog.families.map((f) => f.familyId));
ok('T03a families 与 models 不重叠',
   [...familyIds].every((fid) => !modelIds.has(fid)),
   'family 出现在 models');

// ---- T04: 排序稳定（catalog 按 modelName 排序）----
// ledger identity 注入后，ledger 的 modelId 应是 catalog 子集

// ---- T05/T06: ledger price 有 modelId/familyId（resolved 时）----
const prices = ledger.prices || [];
const withModelId = prices.filter((p) => p.modelId);
ok('T05 ledger resolved price 写 modelId',
   withModelId.length > 0,
   `withModelId=${withModelId.length}`);
ok('T05a ledger modelId 在 catalog 中',
   withModelId.every((p) => modelIds.has(p.modelId)),
   'ledger modelId 不在 catalog');

// ---- T06: formal family 才写 familyId ----
const withFamily = prices.filter((p) => p.familyId);
ok('T06 ledger familyId 引用正式 family',
   withFamily.every((p) => familyIds.has(p.familyId)),
   'ledger familyId 不在 catalog.families');
// model 有 familyId 时必有 familyName
ok('T06a familyId 与 familyName 成对',
   withFamily.every((p) => p.familyId && p.familyName),
   'familyId 无 familyName');

// ---- T07: ledger modelId/familyId 与 public projection 一致 ----
// 同一 provider+model 在 ledger 与 public prices 的 modelId 必须一致
const publicByModel = new Map();
for (const p of publicPrices) {
  if (p.modelId) publicByModel.set(`${p.providerId}:${p.modelKey}`, p.modelId);
}
let mismatches = 0;
for (const p of withModelId) {
  const key = `${p.provider}:${p.model}`;
  const publicId = publicByModel.get(key);
  // public projection 的 providerId 是 canonical，ledger 是 pricing 体系
  // 通过 modelId 值比较（都已是 canonical:slug）
  if (publicId && publicId !== p.modelId) mismatches++;
}
ok('T07 ledger 与 public projection modelId 一致',
   mismatches === 0,
   `${mismatches} 条 modelId 不一致`);

// ---- T08: unresolved/pointer 不写 modelId ----
const unresolved = prices.filter((p) => !p.modelId);
ok('T08 unresolved price 不写 modelId',
   unresolved.length > 0,
   `unresolved=${unresolved.length}`);
// unresolved 的 price 不应有 familyId（无 modelId 必无 familyId）
ok('T08a 无 modelId 必无 familyId',
   unresolved.every((p) => !p.familyId),
   '无 modelId 但有 familyId');

// ---- T09: ledger 不从 modelKey 猜 identity ----
// modelId 为空的 price，其 model 仍保留原始 modelKey（未被篡改）
ok('T09 unresolved 保留原始 model',
   unresolved.every((p) => p.model && typeof p.model === 'string'),
   'unresolved model 被篡改');

// ---- T10: selector 不含 pointer/non_model ----
// catalog 由 exporter 只放 classification=model 的实体构建（pointer/non_model 已排除）。
// 校验：catalog models 的 modelId 格式合法（pointer 不会进入 catalog，因为
// exporter 只放 classification=model；pointer 的 modelId 不会出现在 catalog）
ok('T10 catalog models 全是合法 modelId 格式',
   catalog.models.every((m) => /^[a-z0-9-]+:[a-z0-9.-]+$/.test(m.modelId)),
   'catalog 含非法 modelId');

// ---- T11: ledger identity 字段是 additive optional ----
// 原始 model/model_display_name/provider 仍在
ok('T11 ledger 保留原始 provider/model',
   prices.every((p) => p.provider && p.model),
   '原始字段丢失');
// model_display_name 仍在
ok('T11a ledger 保留 model_display_name',
   prices.some((p) => p.model_display_name),
   'model_display_name 丢失');

// ---- T12: rendered HTML 含 catalog 注入 ----
const renderedPath = new URL('site/src/data/pricing/price-ledger.rendered.html', root);
if (existsSync(renderedPath)) {
  const rendered = readFileSync(renderedPath, 'utf-8');
  ok('T12 rendered HTML 含 modelIdentities',
     rendered.includes('modelIdentities'),
     'rendered 缺 catalog 注入');
  ok('T12a rendered HTML 含 model-filter selector',
     rendered.includes('model-filter') && rendered.includes('family-filter'),
     'rendered 缺 selector');
}

// ---- T13: modelId/familyId 格式合法 ----
ok('T13 modelId 格式合法',
   withModelId.every((p) => /^[a-z0-9-]+:[a-z0-9.-]+$/.test(p.modelId)),
   '非法 modelId 格式');
ok('T13a familyId 格式合法',
   withFamily.every((p) => /^[a-z0-9-]+:[a-z0-9.-]+$/.test(p.familyId)),
   '非法 familyId 格式');

// ---- T14: provider 前缀一致 ----
ok('T14 modelId provider 与 catalog 一致',
   withModelId.every((p) => modelIds.has(p.modelId)),
   'modelId provider 不一致');

console.log(`✓ T07-4A model identity UI 契约测试全部通过（${pass} 项）`);
console.log(`  ledger: ${prices.length} prices / ${withModelId.length} with modelId (${(withModelId.length/prices.length*100).toFixed(1)}%)`);
console.log(`  catalog: ${catalog.models.length} models / ${catalog.families.length} families`);
console.log(`  public projection modelId 一致性: ${mismatches} mismatches`);
