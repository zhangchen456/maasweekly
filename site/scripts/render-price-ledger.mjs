// 价格台账数据注入：ledger.json → price-ledger.fragment.html 的 GOAL_DATA 标记。
// 产物：src/data/pricing/price-ledger.rendered.html（pricing.astro 构建时 set:html 内嵌）。
// 注入转义对齐追浪 view_security.inject_data_into_template：
//   </script> → <\/、U+2028/U+2029 转义，防止数据值逃逸 <script> 标签执行脚本。
// 运行：node site/scripts/render-price-ledger.mjs（已挂 npm run build 前置）。
import { readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');   // site/
const fragmentPath = resolve(root, 'src/data/pricing/price-ledger.fragment.html');
const ledgerPath = resolve(root, 'src/data/pricing/ledger.json');
const logoRegistryPath = resolve(root, 'src/data/platform-logos.json');
const outPath = resolve(root, 'src/data/pricing/price-ledger.rendered.html');

const fragment = readFileSync(fragmentPath, 'utf-8');
const DATA_MARKER = '<!-- GOAL_DATA -->';
if (!fragment.includes(DATA_MARKER)) {
  throw new Error('片段缺 GOAL_DATA 注入标记');
}

if (!existsSync(ledgerPath)) {
  // 无数据时不产渲染文件；pricing.astro 回退到提示卡
  if (existsSync(outPath)) rmSync(outPath);
  console.log('ledger.json 不存在，跳过价格台账渲染');
  process.exit(0);
}
const ledger = JSON.parse(readFileSync(ledgerPath, 'utf-8'));
const logoRegistry = JSON.parse(readFileSync(logoRegistryPath, 'utf-8'));
const normalize = (name) => name.normalize('NFKC').toLocaleLowerCase('en-US').replace(/[\s._/()（）-]+/g, '');
const logoLookup = new Map();
for (const platform of logoRegistry) {
  for (const name of [platform.id, platform.name, ...platform.aliases]) logoLookup.set(normalize(name), platform.file);
}
const providers = ledger.providers ?? [...new Set((ledger.prices ?? []).map((item) => item.provider))];
const providerLogos = Object.fromEntries(providers.flatMap((provider) => {
  const file = logoLookup.get(normalize(provider));
  return file ? [[provider, file]] : [];
}));

// T07-4A：注入 model identity catalog（selector options 来源）。
// 从当前 release 的 model-identities.json 读取，不从 ledger.prices 反推。
// 只含 catalog.models / catalog.families（pointer/non_model 已在 exporter 排除）。
let modelIdentities = { models: [], families: [] };
try {
  const manifestPath = resolve(root, '..', 'data', 'public', 'v1', 'manifest.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
  const catEntry = manifest.files.find((f) => f.path.endsWith('/model-identities.json'));
  if (catEntry) {
    const catPath = resolve(root, '..', 'data', 'public', 'v1', catEntry.path);
    modelIdentities = JSON.parse(readFileSync(catPath, 'utf-8'));
  }
} catch (e) {
  // catalog 缺失不阻塞 ledger 渲染——selector 会为空（构建期容错）
  console.warn('model-identities.json 不可读，selector 将为空:', e.message);
}

const renderedData = { ...ledger, provider_logos: providerLogos, modelIdentities };

const safeJson = JSON.stringify(renderedData)
  .replace(/<\//g, '<\\/')
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029');
const replacement = `<script id="goal-data" type="application/json">${safeJson}</script>`;
const html = fragment.replace(DATA_MARKER, replacement);

writeFileSync(outPath, html);
console.log(`价格台账已注入 → price-ledger.rendered.html（${ledger.prices?.length ?? 0} 条价格 / ${ledger.providers?.length ?? 0} 家）`);
