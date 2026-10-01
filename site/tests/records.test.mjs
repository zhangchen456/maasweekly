// Task 01 站点侧测试：详情页数量、链接、转义与状态输出（T10/T12 页面侧）。
// 运行：node tests/records.test.mjs（需先 cd site && npm run build）
import fs from 'node:fs';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
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

console.log('[0] 测试残留检测');
// 防泄漏门禁：test-esc/test-wd fixture 曾因 cleanup 中断泄漏进真实归档
// （2026-09-16 被 git add data/ 提交，人工清除）。开始前先断言归档干净，
// 残留存在时直接失败——不允许在污染状态下继续跑构建。
const leakDir = path.resolve(siteRoot, '..', 'data', 'records');
const recordsReal = fs.readdirSync(leakDir).filter((f) => f.startsWith('obs_'));
const leaked = recordsReal.filter((f) => {
  const c = fs.readFileSync(path.join(leakDir, f), 'utf-8');
  return c.includes('"test-esc"') || c.includes('"test-wd"');
});
check('真实归档无测试 fixture 残留', leaked.length === 0,
  `残留: ${leaked.join(', ')}（请删除并重建 site/src/data/record-index.json）`);
if (leaked.length > 0) {
  console.error('检测到测试残留，中止（防止污染继续扩散）');
  process.exit(1);
}

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

console.log('[3b/5] 临时输入与输出：转义及撤回 fixture');
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'maas-record-pages-'));
const tempSite = path.join(tempRoot, 'site');
const realIndexHash = crypto.createHash('sha256').update(fs.readFileSync(idxPath)).digest('hex');
const formalItemsBefore = fs.readdirSync(itemDir).sort();
try {
  // Separate cwd preserves the production relative-path contract. No fixture
  // source/index/output is ever written into the real checkout.
  const excluded = new Set(['node_modules', 'dist', '.astro', 'public']);
  fs.cpSync(siteRoot, tempSite, { recursive: true, filter: source => {
    const relative = path.relative(siteRoot, source);
    return !excluded.has(relative.split(path.sep)[0]) && !path.basename(source).startsWith('.env');
  } });
  fs.symlinkSync(path.join(siteRoot, 'node_modules'), path.join(tempSite, 'node_modules'), 'dir');
  fs.symlinkSync(path.join(siteRoot, 'public'), path.join(tempSite, 'public'), 'dir');
  const realData = path.resolve(siteRoot, '..', 'data'), tempData = path.join(tempRoot, 'data');
  fs.mkdirSync(tempData);
  for (const entry of fs.readdirSync(realData)) {
    const source = path.join(realData, entry), target = path.join(tempData, entry);
    if (['records', 'record-revisions'].includes(entry)) fs.cpSync(source, target, { recursive: true });
    else fs.symlinkSync(source, target);
  }
  const fixtureIndex = [...index];
  const writeFixture = (record, revisions) => {
    fs.writeFileSync(path.join(tempData, 'records', record.id + '.json'), JSON.stringify(record));
    const revisionDir = path.join(tempData, 'record-revisions', record.id);
    fs.mkdirSync(revisionDir, { recursive: true });
    for (const revision of revisions) fs.writeFileSync(path.join(revisionDir, revision.revision + '.json'), JSON.stringify(revision));
    fixtureIndex.push({ id: record.id, date: record.date, platform: record.platform,
      sourceId: record.sourceId, kind: record.kind, status: record.status,
      title: record.title, permalink: record.permalink, revision: record.revision });
  };
  const escFixture = 'EVIL<script>alert("xss-marker-9f3a")</script>END';
  const escId = 'obs_' + crypto.createHash('sha256').update('["test-esc","2026-01-01"]').digest('hex');
  const escRecord = {
    schemaVersion: 1, id: escId, sourceId: 'test-esc', date: '2026-01-01',
    recordType: 'source_observation', changeType: 'source_updated', revision: 1,
    status: 'active', platform: '测试平台', sourceType: 'pricing', sourceUrl: null,
    title: '转义测试', summary: escFixture, summaryOrigin: 'rule', observedAt: null,
    timePrecision: 'date', revisedAt: null, revisionReason: null, kind: 'substantive',
    diff: { pairs: [], added_lines: [escFixture], removed_lines: [escFixture], added_count: 1, removed_count: 1 },
    evidenceLevel: 'source_diff', diffCompleteness: 'unknown', provenance: {}, permalink: `/item/${escId}/`,
  };
  writeFixture(escRecord, [escRecord]);
  const sampleId = index.find(r => r.status === 'active')?.id;
  if (!sampleId) throw new Error('withdrawn fixture requires an active record');
  const sample = JSON.parse(fs.readFileSync(path.join(recordsDir, sampleId + '.json'), 'utf8'));
  const wdId = 'obs_' + crypto.createHash('sha256').update('["test-wd","2026-01-02"]').digest('hex');
  const wdRecord = { ...sample, id: wdId, sourceId: 'test-wd', date: '2026-01-02',
    status: 'withdrawn', revision: 2, revisionReason: '重新计算后未识别到变化，撤回收录', permalink: `/item/${wdId}/` };
  writeFixture(wdRecord, [{ ...wdRecord, status: 'active', revision: 1 }, wdRecord]);
  fs.writeFileSync(path.join(tempSite, 'src/data/record-index.json'), JSON.stringify(fixtureIndex));
  // Runtime fixture build intentionally skips prebuild generation: committed
  // production projections remain intact, while only isolated archive inputs vary.
  execFileSync(process.execPath, [path.join(tempSite, 'node_modules/.bin/astro'), 'build'],
    { cwd: tempSite, encoding: 'utf8', stdio: 'pipe', maxBuffer: 64 * 1024 * 1024 });
  const tempDist = path.join(tempSite, 'dist');
  const escHtml = fs.readFileSync(path.join(tempDist, 'item', escId, 'index.html'), 'utf8');
  check('恶意 fixture 详情页可构建', !!escHtml);
  check('恶意文本被转义展示（&lt;script&gt;）', escHtml.includes('EVIL&lt;script&gt;'));
  check('无未转义执行节点', !/<script[^>]*>\s*alert\("xss-marker-9f3a"\)/.test(escHtml));
  const wdHtml = fs.readFileSync(path.join(tempDist, 'item', wdId, 'index.html'), 'utf8');
  check('withdrawn 详情页可访问', wdHtml.includes('已撤回'));
  check('withdrawn 页保留内容（变化摘录仍在）', wdHtml.includes('变化摘录'));
  check('withdrawn 显示撤回原因', wdHtml.includes('重新计算后未识别到变化'));
  check('withdrawn 链接仍含永久链接', wdHtml.includes(wdId));
  check('正式 dist 没有 fixture 页面', !fs.existsSync(path.join(itemDir, escId)) && !fs.existsSync(path.join(itemDir, wdId)));
} catch (error) {
  // Preserve useful build diagnostics in the suite log, never claim a missing
  // page as a successful test. The runner owns failure-log retention.
  if (error.stdout) console.error(error.stdout.toString().slice(-12000));
  if (error.stderr) console.error(error.stderr.toString().slice(-12000));
  throw error;
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
  check('正式索引字节保持不变', crypto.createHash('sha256').update(fs.readFileSync(idxPath)).digest('hex') === realIndexHash);
  check('正式详情页集合保持不变', JSON.stringify(fs.readdirSync(itemDir).sort()) === JSON.stringify(formalItemsBefore));
}

console.log(failed === 0 ? '\n全部通过 ✓' : `\n${failed} 项失败 ✗`);
process.exit(failed === 0 ? 0 : 1);
