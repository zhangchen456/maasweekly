// 价格台账模板 → 可嵌入 /pricing 页的 scoped 片段。
// 输入：src/data/pricing/price-ledger.template.html（追浪原版结构，品牌已改）
// 输出：src/data/pricing/price-ledger.fragment.html
//
// 转换规则（构建期一次完成，片段被 pricing.astro set:html 内嵌）：
// 1. 抽取 <style> 内容，全部选择器加 .plw 前缀（:root → .plw，body → .plw，
//    @media 内规则同样处理），CSS 变量定义挂到 .plw 容器上自持，不污染站点全局
// 2. 抽取 body 内层：去 <main class="shell"> 包裹（Layout 已有容器）与 masthead（站点有导航），
//    保留 hero/explore/compare/notice/footer 内容 + toast + dialog
// 3. <script> 保留原样（选择器全部 getElementById，ID 唯一不冲突；唯一全局副作用
//    document.documentElement.dataset.theme 改为切 .plw 容器的 data-theme）
// 4. <!-- GOAL_DATA --> 标记保留，render-price-ledger.mjs 注入 ledger.json
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const src = readFileSync(resolve(root, 'src/data/pricing/price-ledger.template.html'), 'utf-8');

// ---- 1. 抽 style ----
const styleMatch = src.match(/<style>([\s\S]*?)<\/style>/);
if (!styleMatch) throw new Error('模板缺 <style>');
let css = styleMatch[1];

// 选择器 scope：容器级选择器（:root / :root[attr] / body / html）映射为 .plw / .plw[attr]，
// 其余加 .plw 前缀（保留 @media/@keyframes 嵌套结构）
function scopeCss(cssText) {
  let out = '';
  let i = 0;
  // 先剥离注释（避免卷进选择器导致整条规则失效）
  cssText = cssText.replace(/\/\*[\s\S]*?\*\//g, '');
  while (i < cssText.length) {
    const braceOpen = cssText.indexOf('{', i);
    if (braceOpen === -1) { out += cssText.slice(i); break; }
    const head = cssText.slice(i, braceOpen);
    // 找配对的闭括号（考虑嵌套）
    let depth = 1, j = braceOpen + 1;
    while (j < cssText.length && depth > 0) {
      if (cssText[j] === '{') depth++;
      else if (cssText[j] === '}') depth--;
      j++;
    }
    const body = cssText.slice(braceOpen + 1, j - 1);
    const headTrim = head.trim();
    if (headTrim.startsWith('@media') || headTrim.startsWith('@supports')) {
      out += head + scopeCss(body) + '}';
    } else if (headTrim.startsWith('@keyframes') || headTrim.startsWith('@font-face') || headTrim.startsWith('@')) {
      out += head + body + '}';  // 原样（keyframes 内是百分比选择器，frames 名冲突风险接受——站点无同名 enter 动画）
    } else {
      const scoped = head.split(',').map((s) => {
        let t = s.trim();
        if (!t) return t;
        // 容器级选择器保持容器本身：:root / :root[attr] / body / html → .plw / .plw[attr]
        t = t
          .replace(/^:root(\[[^\]]*\])?/, '.plw$1')
          .replace(/^(body|html)$/, '.plw');
        if (t === '.plw' || t.startsWith('.plw[')) return t;
        return `.plw ${t.startsWith(':') ? `.plw${t}` : t}`;
      }).join(', ');
      out += ` ${scoped}{${body}}`;
    }
    i = j;
  }
  return out;
}
css = scopeCss(css);
// 修正：:root[data-theme=light] 这类在 scopeCss 中会变成 .plw :root[data-theme=light]——改回容器级
css = css.replace(/\.plw :root/g, '.plw');

// ---- 2. 抽 body 内容（模板 body 自足：GOAL_DATA 标记与全部 script 都在其中）----
const bodyMatch = src.match(/<body>([\s\S]*?)<\/body>/);
if (!bodyMatch) throw new Error('模板缺 <body>');
let body = bodyMatch[1];
// 去 main 包裹
body = body.replace(/<\/?main[^>]*>/g, '');
// 去 masthead（站点有导航），但保留其三个功能控件（主题切换/汇率快捷/更新时间徽标）：
// 挪到 hero eyebrow 行右侧，避免 JS 因元素缺失崩溃
body = body.replace(
  /<header class="masthead[\s\S]*?<\/header>/,
  '');

// ---- 3. 去 script 全局主题副作用：documentElement → .plw 容器 ----
body = body.replaceAll(
  'document.documentElement.dataset.theme',
  "document.getElementById('price-ledger').dataset.theme");

// ---- 3b. masthead 的三个功能控件重植入 hero ----
// masthead 被删后 theme/currency-shortcut/updated 三个 ID 无宿主，JS 会崩。
// 以工具条形式插在 hero 第一列顶部（eyebrow 同行右对齐）。
const toolRow = `<div class="row between wrap" style="gap:10px"><span></span><div class="row" style="gap:8px"><button id="currency-shortcut" class="small" title="调整人民币估算汇率" style="font-size:10px;padding:5px 9px">¥ 人民币 · 汇率 7</button><span class="pill" style="font-size:10px"><i class="dot"></i><span id="updated">数据加载中</span></span><button id="theme" aria-label="切换深色外观" title="切换外观">◐</button></div></div>`;
// 插在 hero 第一个 div 的 eyebrow 之前
body = body.replace(/(<section class="hero[^>]*">\s*<div>\s*)<div class="eyebrow">/,
  `$1${toolRow}<div class="eyebrow" style="margin-top:10px">`);

// ---- 4. 拼片段：容器 div 包裹（CSS 变量与主题 data-theme 自持于容器）----
const fragment = `<!-- 价格台账片段（由 site/scripts/build-price-fragment.mjs 从 price-ledger.template.html 生成，勿手改） -->
<div id="price-ledger" class="plw" data-theme="light">
<style>${css}</style>
${body.trim()}
</div>
`;
writeFileSync(resolve(root, 'src/data/pricing/price-ledger.fragment.html'), fragment);
console.log(`price-ledger.fragment.html 已生成（${(fragment.length / 1024).toFixed(0)}KB）`);
