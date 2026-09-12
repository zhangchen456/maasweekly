// Task 01 站点侧测试：详情页数量、链接、转义与状态输出（T10/T12 页面侧）。
// 运行：node tests/records.test.mjs（需先 cd site && npm run build）
import fs from 'node:fs';
import crypto from 'node:crypto';
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const siteRoot = path.resolve(__dirname, '..');
const dist = path.join(siteRoot, 'dist');

let failed = 0;
const check = (name, cond, detail = '') => {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failed++;
    console.error(`  ✗ ${name}${detail ? ' — ' + detail : ''}`);
  }
};

console.log('[1] record-index 与归档一致');
const idxPath = path.join(siteRoot, 'src/data/record-index.json');
const index = JSON.parse(fs.readFileSync(idxPath, 'utf-8'));
const recordsDir = path.resolve(siteRoot, '..', 'data', 'records');
const recordFiles = fs.readdirSync(recordsDir).filter((f) => f.startsWith('obs_') && f.endsWith('.json'));
check('索引条数 = 归档文件数', index.length === recordFiles.length,
  `index=${index.length} files=${recordFiles.length}`);

console.log('[2] 详情页构建完整性（T12 页面侧）');
const itemDir = path.join(dist, 'item');
const builtItems = fs.existsSync(itemDir)
  ? fs.readdirSync(itemDir).filter((d) => d.startsWith('obs_'))
  : [];
check('全部条目有详情页', builtItems.length === index.length,
  `built=${builtItems.length} index=${index.length}`);

// 索引中每个 permalink 都有对应页面
const missing = index.filter((r) => !builtItems.includes(r.id));
check('索引引用无悬空（全部 permalink 可达）', missing.length === 0,
  missing.slice(0, 3).map((r) => r.id).join(', '));

console.log('[3] 详情页内容检查');
let withCopy = 0, withPermalink = 0, withdrawnPages = 0;
for (const id of builtItems) {
  const html = fs.readFileSync(path.join(itemDir, id, 'index.html'), 'utf-8');
  if (html.includes('copy-btn') && html.includes('data-url=')) withCopy++;
  if (html.includes('/item/' + id)) withPermalink++;
  if (html.includes('已撤回')) withdrawnPages++;
}
check('全部详情页有复制按钮', withCopy === builtItems.length, `${withCopy}/${builtItems.length}`);
check('全部详情页含自身永久链接', withPermalink === builtItems.length);

console.log('[3b] T10 转义防护（恶意 fixture）');
// 用带特定恶意文本的 fixture 验证：文本被转义、不产生执行节点
const escFixture = 'EVIL<script>alert("xss-marker-9f3a")</script>END';
// 合法 ID（门禁校验 id 必须由 sourceId+date 派生）：内联同算法计算
const escId = 'obs_' + crypto.createHash('sha256')
  .update('["test-esc","2026-01-01"]').digest('hex');
const escRecord = {
  schemaVersion: 1, id: escId, sourceId: 'test-esc', date: '2026-01-01',
  recordType: 'source_observation', changeType: 'source_updated',
  revision: 1, status: 'active', platform: '测试平台', sourceType: 'pricing',
  sourceUrl: null, title: '转义测试', summary: escFixture,
  summaryOrigin: 'rule', observedAt: null, timePrecision: 'date',
  revisedAt: null, revisionReason: null, kind: 'substantive',
  diff: { pairs: [], added_lines: [escFixture], removed_lines: [escFixture],
          added_count: 1, removed_count: 1 },
  evidenceLevel: 'source_diff', diffCompleteness: 'unknown',
  provenance: {}, permalink: `/item/${escId}/`,
};
const escRecordsDir = path.resolve(siteRoot, '..', 'data', 'records');
const escRevDir = path.resolve(siteRoot, '..', 'data', 'record-revisions', escId);
const escRecordFile = path.join(escRecordsDir, escId + '.json');
const existed = fs.existsSync(escRecordFile);
fs.writeFileSync(escRecordFile, JSON.stringify(escRecord, null, 2));
fs.mkdirSync(escRevDir, { recursive: true });
fs.writeFileSync(path.join(escRevDir, '1.json'), JSON.stringify(escRecord, null, 2));
// 临时索引
const idxPath2 = path.join(siteRoot, 'src/data/record-index.json');
const idxBak = fs.readFileSync(idxPath2, 'utf-8');
const idxWithEsc = JSON.parse(idxBak);
idxWithEsc.push({ id: escId, date: '2026-01-01', platform: '测试平台',
  sourceId: 'test-esc', kind: 'substantive', status: 'active',
  title: '转义测试', permalink: `/item/${escId}/`, revision: 1 });
fs.writeFileSync(idxPath2, JSON.stringify(idxWithEsc, null, 2));
let escBuilt = false, escEscaped = false, escNotExecuted = false;
try {
  execSync('npm run build', { cwd: siteRoot, stdio: 'pipe' });
  const escHtml = fs.readFileSync(path.join(dist, 'item', escId, 'index.html'), 'utf-8');
  escBuilt = true;
  // 恶意文本必须以转义形式出现（&lt;script&gt;），且原文 <script>alert( 存在于文本中
  escEscaped = escHtml.includes('&lt;script&gt;alert("xss-marker-9f3a")&lt;/script&gt;END')
    || escHtml.includes('EVIL&lt;script&gt;');
  // 不存在未转义的执行节点（script 标签后跟 alert）
  escNotExecuted = !/<script[^>]*>\s*alert\("xss-marker-9f3a"\)/.test(escHtml);
} finally {
  // 清理 fixture（含 dist 产物，避免污染下次运行）
  if (!existed) fs.rmSync(escRecordFile, { force: true });
  fs.rmSync(escRevDir, { recursive: true, force: true });
  fs.writeFileSync(idxPath2, idxBak);
  fs.rmSync(path.join(dist, 'item', escId), { recursive: true, force: true });
}
check('恶意 fixture 详情页可构建', escBuilt);
check('恶意文本被转义展示（&lt;script&gt;）', escEscaped);
check('无未转义执行节点', escNotExecuted);

console.log('[4] 索引独立周入口（T04 页面侧）');
const dailyDir = path.join(dist, 'daily');
const builtWeeks = fs.existsSync(dailyDir) ? fs.readdirSync(dailyDir) : [];
// 索引覆盖的周
const weekOf = (dateStr) => {
  const d = new Date(dateStr + 'T00:00:00Z');
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`;
};
const indexWeeks = [...new Set(index.map((r) => weekOf(r.date)))];
const missingWeeks = indexWeeks.filter((w) => !builtWeeks.includes(w));
check('索引涉及周都有周归档页', missingWeeks.length === 0,
  `缺: ${missingWeeks.join(', ')}（已有: ${builtWeeks.join(', ')}）`);

// 周归档页含来源记录链接
for (const w of indexWeeks) {
  const html = fs.readFileSync(path.join(dailyDir, w, 'index.html'), 'utf-8');
  check(`周归档 ${w} 含来源变化记录区块`, html.includes('来源变化记录'));
}

console.log('[5] withdrawn 页面保留内容（T05 页面侧，真实 fixture 断言）');
// 构造一个 withdrawn 条目：复制任一现有记录改为 withdrawn
{
  const sampleId = index.find((r) => r.status === 'active')?.id;
  if (sampleId) {
    const sampleFile = path.join(recordsDir, sampleId + '.json');
    const sample = JSON.parse(fs.readFileSync(sampleFile, 'utf-8'));
    const wdSourceId = 'test-wd';
    const wdDate = '2026-01-02';
    const wdId = 'obs_' + crypto.createHash('sha256')
      .update('["' + wdSourceId + '","' + wdDate + '"]').digest('hex');
    const wdRecord = { ...sample, id: wdId, sourceId: wdSourceId,
      date: wdDate, status: 'withdrawn', revision: 2,
      revisionReason: '重新计算后未识别到变化，撤回收录',
      permalink: '/item/' + wdId + '/' };
    const wdFile = path.join(recordsDir, wdId + '.json');
    const wdRevDir = path.resolve(siteRoot, '..', 'data', 'record-revisions', wdId);
    fs.writeFileSync(wdFile, JSON.stringify(wdRecord, null, 2));
    fs.mkdirSync(wdRevDir, { recursive: true });
    const r1 = { ...wdRecord, status: 'active', revision: 1 };
    fs.writeFileSync(path.join(wdRevDir, '1.json'), JSON.stringify(r1, null, 2));
    fs.writeFileSync(path.join(wdRevDir, '2.json'), JSON.stringify(wdRecord, null, 2));
    const idxBak2 = fs.readFileSync(idxPath, 'utf-8');
    const idxWd = JSON.parse(idxBak2);
    idxWd.push({ id: wdId, date: wdRecord.date, platform: wdRecord.platform,
      sourceId: wdRecord.sourceId, kind: wdRecord.kind, status: 'withdrawn',
      title: wdRecord.title, permalink: wdRecord.permalink, revision: 2 });
    fs.writeFileSync(idxPath, JSON.stringify(idxWd, null, 2));
    try {
      execSync('npm run build', { cwd: siteRoot, stdio: 'pipe' });
      const wdHtml = fs.readFileSync(path.join(dist, 'item', wdId, 'index.html'), 'utf-8');
      check('withdrawn 详情页可访问', wdHtml.includes('已撤回'));
      check('withdrawn 页保留内容（变化摘录仍在）', wdHtml.includes('变化摘录'));
      check('withdrawn 显示撤回原因', wdHtml.includes('重新计算后未识别到变化'));
      check('withdrawn 链接仍含永久链接', wdHtml.includes(wdId));
    } finally {
      fs.rmSync(wdFile, { force: true });
      fs.rmSync(wdRevDir, { recursive: true, force: true });
      fs.writeFileSync(idxPath, idxBak2);
      fs.rmSync(path.join(dist, 'item', wdId), { recursive: true, force: true });
    }
  }
}

console.log(failed === 0 ? '\n全部通过 ✓' : `\n${failed} 项失败 ✗`);
process.exit(failed === 0 ? 0 : 1);
