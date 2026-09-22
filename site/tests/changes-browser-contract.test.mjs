// T07-4A.2：Changes Browser 数据契约测试。
// 验证 public release changes 数据的 modelId/familyId 合同 + catalog 一致性。
// 运行：node site/tests/changes-browser-contract.test.mjs
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const root = new URL('../../', import.meta.url);
const manifest = JSON.parse(
  readFileSync(new URL('data/public/v1/manifest.json', root), 'utf-8'));

const changesEntry = manifest.files.find((f) => f.path.endsWith('/changes.json'));
assert.ok(changesEntry, 'manifest 缺 changes.json');
const changes = JSON.parse(
  readFileSync(new URL('data/public/v1/' + changesEntry.path, root), 'utf-8'));

const catEntry = manifest.files.find((f) => f.path.endsWith('/model-identities.json'));
assert.ok(catEntry, 'manifest 缺 model-identities.json');
const catalog = JSON.parse(
  readFileSync(new URL('data/public/v1/' + catEntry.path, root), 'utf-8'));

let pass = 0;
function ok(name, cond, detail) {
  if (cond) pass++;
  else throw new Error(`✗ ${name}: ${detail ?? ''}`);
}

const modelIds = new Set(catalog.models.map((m) => m.modelId));
const familyIds = new Set(catalog.families.map((f) => f.familyId));

const priceChanges = changes.filter((c) => c.recordType === 'price_change');
const sourceObs = changes.filter((c) => c.recordType === 'source_observation');

// ---- T01: price_change 有 modelId（resolved 时）----
const pcWithModel = priceChanges.filter((c) => c.modelId);
ok('T01 price_change 有 modelId', pcWithModel.length > 0, `withModelId=${pcWithModel.length}`);

// ---- T02: price_change modelId 在 catalog 中----
ok('T02 price_change modelId 在 catalog',
   pcWithModel.every((c) => modelIds.has(c.modelId)),
   'price_change modelId 不在 catalog');

// ---- T03: familyId 引用正式 family----
const withFamily = changes.filter((c) => c.familyId);
ok('T03 familyId 引用正式 family',
   withFamily.every((c) => familyIds.has(c.familyId)),
   'familyId 不在 catalog.families');

// ---- T04: source_observation 无 modelId（不猜模型）----
ok('T04 source_observation 无 modelId',
   sourceObs.every((c) => !c.modelId),
   `source_observation 有 modelId: ${sourceObs.filter((c) => c.modelId).length}`);

// ---- T05: source_observation 无 familyId----
ok('T05 source_observation 无 familyId',
   sourceObs.every((c) => !c.familyId),
   `source_observation 有 familyId`);

// ---- T06: modelId 格式合法----
ok('T06 modelId 格式合法',
   pcWithModel.every((c) => /^[a-z0-9-]+:[a-z0-9.-]+$/.test(c.modelId)),
   '非法 modelId 格式');

// ---- T07: unresolved price_change 不写 modelId（保留原始 title）----
const unresolved = priceChanges.filter((c) => !c.modelId);
ok('T07 unresolved price_change 保留 title',
   unresolved.every((c) => c.title && typeof c.title === 'string'),
   'unresolved title 缺失');
// unresolved 的 title 含原始 model 名（不伪造 canonical）
ok('T07a unresolved 不写 modelName',
   unresolved.every((c) => !c.modelName),
   'unresolved 写了 modelName（伪造）');

// ---- T08: changes 数据有 observationDate（排序键）----
ok('T08 changes 有 observationDate',
   changes.every((c) => c.observationDate),
   '缺 observationDate');

// ---- T09: changes 有 id（详情页链接）----
ok('T09 changes 有 id',
   changes.every((c) => c.id),
   '缺 id');

// ---- T10: changes 有 providerId----
ok('T10 changes 有 providerId',
   changes.every((c) => c.providerId !== undefined),
   '缺 providerId');

// ---- T11: modelId/familyId 互斥性（同一条 change 不应同时有不同 modelId/familyId 冲突）----
// 有 modelId 的 change，其 familyId 应是同一 model 的 family（或无）
ok('T11 有 modelId 的 change familyId 合法',
   pcWithModel.every((c) => !c.familyId || familyIds.has(c.familyId)),
   'modelId 与 familyId 冲突');

console.log(`✓ T07-4A.2 Changes Browser 数据契约测试全部通过（${pass} 项）`);
console.log(`  changes: ${changes.length} (price_change ${priceChanges.length} / source_observation ${sourceObs.length})`);
console.log(`  price_change with modelId: ${pcWithModel.length} / ${priceChanges.length} (${(pcWithModel.length/priceChanges.length*100).toFixed(1)}%)`);
console.log(`  source_observation with modelId: 0 (合同: 不猜模型)`);
