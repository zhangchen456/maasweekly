// 模型价格台账渲染：ledger.json 注入 price-ledger 模板 → public/prices/index.html
// 运行：node site/scripts/render-price-ledger.mjs（astro build 前跑；build 时 public/ 直出静态文件）
// 注入转义逻辑对齐追浪 view_security.inject_data_into_template：
//   </script> → <\/、U+2028/U+2029 转义，防止数据值逃逸 <script> 标签执行脚本。
import { readFileSync, writeFileSync, mkdirSync, existsSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');   // site/
const templatePath = resolve(root, 'src/data/pricing/price-ledger.template.html');
const ledgerPath = resolve(root, 'src/data/pricing/ledger.json');
const outDir = resolve(root, 'public/prices');
const outPath = resolve(outDir, 'index.html');

const template = readFileSync(templatePath, 'utf-8');
if (!existsSync(ledgerPath)) {
  // 无数据时清掉旧产物，不渲染空页
  if (existsSync(outPath)) rmSync(outPath);
  console.log('ledger.json 不存在，跳过价格页渲染');
  process.exit(0);
}
const ledger = JSON.parse(readFileSync(ledgerPath, 'utf-8'));

const DATA_MARKER = '<!-- GOAL_DATA -->';
if (!template.includes(DATA_MARKER)) {
  throw new Error('模板缺 GOAL_DATA 注入标记');
}

const safeJson = JSON.stringify(ledger)
  .replace(/<\//g, '<\\/')
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029');
const replacement = `<script id="goal-data" type="application/json">${safeJson}</script>`;
const html = template.replace(DATA_MARKER, replacement,);

mkdirSync(outDir, { recursive: true });
writeFileSync(outPath, html);
console.log(`价格台账已渲染 → public/prices/index.html（${ledger.prices?.length ?? 0} 条价格 / ${ledger.providers?.length ?? 0} 家）`);
