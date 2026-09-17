// Task 05 接入页/方法页/变更页测试（T01–T05、T13、T14；T15 自动部分）。
// 运行：node --experimental-strip-types tests/access-pages.test.mjs（需先 npm run build）
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const dist = path.join(siteRoot, 'dist');

const { PUBLIC_ACCESS, validatePublicAccessConfig } =
  await import('../src/config/public-access.ts');
const { loadVerifiedRelease } = await import('../src/lib/release.ts');

let failed = 0;
const check = (name, cond, detail = '') => {
  if (cond) console.log(`  ✓ ${name}`);
  else { failed++; console.error(`  ✗ ${name}${detail ? ' — ' + detail : ''}`); }
};
const read = (p) => fs.readFileSync(path.join(dist, p), 'utf-8');

console.log('[1] T01：配置门禁（含违规样本逐项拒）');
{
  check('当前配置零违规', validatePublicAccessConfig(PUBLIC_ACCESS).length === 0);
  const bad = [
    { ...PUBLIC_ACCESS, canonicalBaseUrl: '' },
    { ...PUBLIC_ACCESS, canonicalBaseUrl: 'http://daily.maas.click' },
    { ...PUBLIC_ACCESS, canonicalBaseUrl: 'https://localhost:3000' },
    { ...PUBLIC_ACCESS, canonicalBaseUrl: 'https://x.local' },
    { ...PUBLIC_ACCESS, canonicalBaseUrl: 'file:///Users/x' },
    { ...PUBLIC_ACCESS, canonicalBaseUrl: 'https://x/Users/y' },
    { ...PUBLIC_ACCESS, paths: { ...PUBLIC_ACCESS.paths, openapi: 'https://evil/x' } },
    { ...PUBLIC_ACCESS, surfaces: { ...PUBLIC_ACCESS.surfaces, rss: { ...PUBLIC_ACCESS.surfaces.rss, status: 'weird' } } },
    { ...PUBLIC_ACCESS, surfaces: { ...PUBLIC_ACCESS.surfaces, mcp: { ...PUBLIC_ACCESS.surfaces.mcp, status: 'unavailable', reason: '' } } },
  ];
  for (const b of bad) {
    check(`违规样本被拒（${b.canonicalBaseUrl !== PUBLIC_ACCESS.canonicalBaseUrl ? b.canonicalBaseUrl : '结构违规'}）`,
      validatePublicAccessConfig(b).length > 0);
  }
  // pending 是合法状态不失败
  check('pending 状态不触发门禁', validatePublicAccessConfig(PUBLIC_ACCESS).length === 0);
  // 客户端同名冲突
  const dup = { ...PUBLIC_ACCESS, pendingClients: [{ name: 'Claude Code', unblockCondition: 'x' }] };
  check('客户端同时出现在两边被拒', validatePublicAccessConfig(dup).length > 0);
}

console.log('[2] T01：漂移检测（openapi/skill-version/llms.txt ↔ config）');
{
  const openapi = JSON.parse(fs.readFileSync(path.join(siteRoot, 'public', 'openapi-v1.json'), 'utf-8'));
  check('openapi servers[0].url === canonical', openapi.servers[0].url === PUBLIC_ACCESS.canonicalBaseUrl);
  const sv = JSON.parse(fs.readFileSync(path.join(siteRoot, 'public', 'maas-skill', 'skill-version.json'), 'utf-8'));
  check('skill-version publicBaseUrl === canonical', sv.publicBaseUrl === PUBLIC_ACCESS.canonicalBaseUrl);
  check('skill-version mcpPath === config', sv.mcpPath === PUBLIC_ACCESS.paths.mcpEndpoint);
  const llms = read('llms.txt');
  const llmsUrls = [...llms.matchAll(/https?:\/\/[^\s)\]]+/g)].map((m) => m[0]);
  const expected = new Set([
    `${PUBLIC_ACCESS.canonicalBaseUrl}/agent/`,
    `${PUBLIC_ACCESS.canonicalBaseUrl}/method/`,
    `${PUBLIC_ACCESS.canonicalBaseUrl}/changelog/`,
    `${PUBLIC_ACCESS.canonicalBaseUrl}/openapi-v1.json`,
    `${PUBLIC_ACCESS.canonicalBaseUrl}/feed.xml`,
    `${PUBLIC_ACCESS.canonicalBaseUrl}/feed/weekly.xml`,
  ]);
  check('llms.txt URL 集与 config 推导一致',
    llmsUrls.length === expected.size && llmsUrls.every((u) => expected.has(u)),
    `实得 ${llmsUrls.length} 期望 ${expected.size}`);
  check('llms.txt 无实时数量', !/\d+\s*条|\d+\s*期/.test(llms));
  check('llms.txt 无客户端兼容宣称', !llms.includes('Claude Code') && !llms.includes('Codex'));
}

console.log('[3] T01：dist 扫描（无 localhost/file/本机路径/sudo）');
{
  const badPatterns = [/localhost/i, /127\.0\.0\.1/, /file:\/\//, /\/Users\//, /\/home\//];
  const files = [...fs.readdirSync(dist, { recursive: true })]
    .map((f) => path.join(dist, String(f)))
    .filter((f) => fs.existsSync(f) && fs.statSync(f).isFile()
      && /\.(html|xml|txt)$/.test(f));
  const offenders = [];
  for (const f of files) {
    const t = fs.readFileSync(f, 'utf-8');
    // sudo 只匹配命令调用形态（&&/|/行首后的 sudo cmd），排除「不使用 sudo」类说明
    if (/(^|[&|;]\s*|\n)sudo\s+\w/.test(t)) offenders.push(`sudo 调用: ${path.relative(dist, f)}`);
    for (const pat of badPatterns) {
      if (pat.test(t)) { offenders.push(`${pat}: ${path.relative(dist, f)}`); break; }
    }
  }
  check(`dist ${files.length} 个 html/xml/txt 无违规内容`, offenders.length === 0,
    offenders.slice(0, 5).join(' | '));
}

console.log('[4] T02/T03/T05：/agent/ 页面内容');
{
  const html = read('agent/index.html');
  // 四方式齐备
  for (const kw of ['Skill', 'MCP', 'RSS', 'REST API']) {
    check(`四卡含「${kw}」`, html.includes(kw));
  }
  // 数据快照声明
  check('观察快照声明', html.includes('观察快照'));
  check('无结果语义', html.includes('未记录到匹配项') || html.includes('不代表供应商实时官网'));
  // T03 客户端列表
  check('Claude Code 标为已验证', /已验证[:：]\s*Claude Code\s*2\.1\.259/.test(html));
  check('Codex 标为待验证', html.includes('待验证：Codex'));
  check('Codex 无「已支持」徽标', !/已支持[^<]*Codex|Codex[^<]*已支持/.test(html));
  // T05 示例一致性
  check('Skill 安装命令 --dir 占位符', html.includes('--dir &lt;你的技能目录&gt;') || html.includes('--dir <你的技能目录>'));
  check('MCP 配置 URL 来自 config', html.includes(`${PUBLIC_ACCESS.canonicalBaseUrl}/api/mcp`));
  check('REST base URL 正确', html.includes(`${PUBLIC_ACCESS.canonicalBaseUrl}/api/v1`));
  check('feed 双地址', html.includes('/feed.xml') && html.includes('/feed/weekly.xml'));
  // pending 卡含 Task 06 解除说明
  check('pending 卡含 Task 06 说明', html.includes('Task 06'));
  // 复验 P1-2：RSS 未部署必须显示 pending（不伪装已上线）
  check('RSS 卡显示待部署（未伪装已上线）',
    /RSS[\s\S]{0,400}?待部署/.test(html) && !/RSS[\s\S]{0,400}?已上线/.test(html));
  check('RSS 卡含真实状态原因（本地验证通过待部署）',
    /RSS[\s\S]{0,800}?生产 URL 待 Task 06/.test(html));
  // CopyBlock aria
  check('复制反馈 aria-live', html.includes('aria-live="polite"'));
  // 成功示例来自 release
  const release = loadVerifiedRelease();
  check('示例含 dataThrough', html.includes(release.dataThrough));
  check('示例含 datasetVersion 短码', html.includes(release.datasetVersion.slice(0, 12)));
  check('示例含 coverage count', html.includes(String(release.coverage.changes.count)));
}

console.log('[5] T13：/method/ 动态数字与时间语义');
{
  const html = read('method/index.html');
  const release = loadVerifiedRelease();
  check('含 dataThrough', html.includes(release.dataThrough));
  check('含 changes count', html.includes(String(release.coverage.changes.count)));
  check('含 prices facts', html.includes(String(release.coverage.prices.facts)));
  check('含 weekly count', html.includes(String(release.coverage.weekly.count)));
  // 不混入构建时间戳（build time 形如 2026-09-17T10:xx）
  check('无构建时间戳冒充数据时间', !/20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}/.test(html));
  // 八节关键词
  for (const kw of ['观察', '五种时间', '证据', 'LLM 摘要', '价格的条件', '衍生数据', '健康信号', '修订、撤回']) {
    check(`方法节「${kw}」存在`, html.includes(kw));
  }
}

console.log('[6] T14：/changelog/ 真实性');
{
  const html = read('changelog/index.html');
  check('首条记录存在', html.includes('公开接口初始状态'));
  check('不倒填日期（待部署措辞）', html.includes('随首次生产部署确定'));
  check('v1 兼容规则', html.includes('破坏性变更') && html.includes('v2'));
  // 页面明示「无任何 Sunset 计划」——否定句合法；断言不存在「将于/计划于 X 停用」式公告
  check('无虚构停用公告（Sunset/Deprecation 无日期型预告）',
    !/(Sunset|Deprecation)[^<]{0,30}(将于|于 20\d\d|by 20\d\d)/.test(html));
  check('五 area 齐备', ['REST API', 'MCP', 'Skill', 'RSS', '网页'].every((a) => html.includes(a)));
}

console.log('[7] T12：页面内链 dist 实存');
{
  for (const page of ['agent', 'method', 'changelog']) {
    const html = read(`${page}/index.html`);
    const hrefs = [...html.matchAll(/href="([^"]+)"/g)].map((m) => m[1])
      .filter((h) => h.startsWith('/'));
    const missing = hrefs.filter((h) => {
      if (h.startsWith('/api/') || h.startsWith('/maas-skill/')) return false; // 端点/包文件
      const p = h.replace(/\/$/, '');
      return !fs.existsSync(path.join(dist, p, 'index.html'))
        && !fs.existsSync(path.join(dist, `${p}.json`))
        && !fs.existsSync(path.join(dist, h));
    });
    check(`${page} 内部链接实存`, missing.length === 0, `缺失 ${missing.slice(0, 3)}`);
  }
}

console.log('[8] T15/T22（自动部分）：CSS 与焦点');
{
  const html = read('agent/index.html');
  // Astro 5 把 scoped style 抽离为外链 CSS——从 <link rel="stylesheet"> 读
  const cssLinks = [...html.matchAll(/href="(\/_astro\/[^"]+\.css)"/g)].map((m) => m[1]);
  const css = cssLinks.map((h) => {
    const p = path.join(dist, h);
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf-8') : '';
  }).join('\n');
  check('抽离 CSS 存在', css.length > 0, `外链: ${cssLinks.join(',')}`);
  check('代码块 overflow-x 处理', css.includes('overflow-x'));
  check('焦点样式 focus-visible', css.includes('focus-visible'));
  // M6 改为纵向段落 + 首屏状态汇总 + 锚点导航；不再用 grid minmax（T21/T22）
  check('首屏四状态汇总', html.includes('status-row') && html.includes('status-pill'));
  check('入口导航（四锚点）', html.includes('nav-pills') && html.includes('aria-label="接入方式导航"'));
  check('方式选择段存在', html.includes('选哪种方式'));
  for (const anchor of ['method-skill', 'method-mcp', 'method-rss', 'method-rest']) {
    check(`锚点 #${anchor}`, html.includes(`id="${anchor}"`) && html.includes(`href="#${anchor}"`));
  }
  check('锚点偏移（防固定导航遮挡）', css.includes('scroll-margin-top'));
  check('复制按钮为原生 button', html.includes('data-copy-btn'));
  check('五个 MCP 工具名', ['maas_get_changes', 'maas_get_prices', 'maas_get_item', 'maas_get_evidence', 'maas_get_weekly']
    .every((t) => html.includes(t)));
  check('六类 REST 端点', ['/status', '/changes', '/prices', '/item', '/evidence', '/weekly']
    .every((p) => html.includes(`/api/v1${p}`)));
  // 手动部分（320/375/768/桌面/键盘）记录在 task-06-result.md
}

console.log(failed === 0 ? '\n全部通过 ✓' : `\n${failed} 项失败 ✗`);
process.exit(failed === 0 ? 0 : 1);
