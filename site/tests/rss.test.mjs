// Task 05 RSS 测试（T06–T12、T16；T08 单元级）。
// 运行：node --experimental-strip-types tests/rss.test.mjs（需先 npm run build）
// fixture 全部 os.tmpdir()+mkdtemp，绝不写真实 data/。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { XMLParser } from 'fast-xml-parser';
import { createHash } from 'node:crypto';

const siteRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const dist = path.join(siteRoot, 'dist');

const { buildRss20, changesToFeedItems, weeklyToFeedItems, rfc2822Utc } =
  await import('../src/lib/feed-build.ts');
const { loadVerifiedRelease, defaultPublicReleaseDir } =
  await import('../src/lib/release.ts');
const { PUBLIC_ACCESS } = await import('../src/config/public-access.ts');

let failed = 0;
const check = (name, cond, detail = '') => {
  if (cond) console.log(`  ✓ ${name}`);
  else { failed++; console.error(`  ✗ ${name}${detail ? ' — ' + detail : ''}`); }
};

const parser = new XMLParser({ ignoreAttributes: false });

console.log('[0] 前置：dist feed 存在');
const feedPath = path.join(dist, 'feed.xml');
const weeklyPath = path.join(dist, 'feed', 'weekly.xml');
check('dist/feed.xml 存在', fs.existsSync(feedPath));
check('dist/feed/weekly.xml 存在', fs.existsSync(weeklyPath));

console.log('[1] T06：feed.xml 合规 RSS 2.0 + 100 条 + 顺序 + GUID + 链接实存');
{
  const doc = parser.parse(fs.readFileSync(feedPath, 'utf-8'));
  const items = doc.rss?.channel?.item ?? [];
  check('RSS 2.0 根', doc.rss?.['@_version'] === '2.0');
  check('channel 三要素', Boolean(doc.rss.channel.title && doc.rss.channel.link && doc.rss.channel.description));
  check(`条数 ≤ 100（实得 ${items.length}）`, items.length > 0 && items.length <= 100);
  const guids = items.map((i) => i.guid?.['#text'] ?? i.guid);
  check('GUID 唯一', new Set(guids).size === guids.length);
  check('GUID 全为稳定 record ID', guids.every((g) => /^(obs|price)_[0-9a-f]{64}$/.test(String(g))));
  check('GUID 不含 datasetVersion/构建日期', !guids.some((g) => String(g).includes('ds_')));
  // 顺序 = 重算期望（真实 release 独立重算）
  const release = loadVerifiedRelease(undefined, { select: ['changes'] });
  const expect = changesToFeedItems(release.changes, PUBLIC_ACCESS.canonicalBaseUrl, 100);
  check('顺序与公开排序一致', JSON.stringify(guids) === JSON.stringify(expect.map((e) => e.guid)));
  // 链接 dist 实存
  const missing = items.filter((i) =>
    !fs.existsSync(path.join(dist, 'item', String(i.guid?.['#text'] ?? i.guid), 'index.html')));
  check('全部链接的详情页在 dist 实存', missing.length === 0,
    `缺失 ${missing.length} 个（如 ${missing[0]?.guid?.['#text'] ?? missing[0]?.guid}）`);
  check('link 全为 canonical HTTPS', items.every((i) => String(i.link).startsWith('https://daily.maas.click/item/')));
}

console.log('[2] T07：weekly.xml ≤30 期 + GUID + 链接实存 + 倒序');
{
  const doc = parser.parse(fs.readFileSync(weeklyPath, 'utf-8'));
  const items = doc.rss?.channel?.item ?? [];
  check(`期数 ≤ 30（实得 ${items.length}）`, items.length > 0 && items.length <= 30);
  const guids = items.map((i) => i.guid?.['#text'] ?? i.guid);
  check('GUID 唯一且为日期 ID', new Set(guids).size === guids.length
    && guids.every((g) => /^\d{4}-\d{2}-\d{2}$/.test(String(g))));
  check('最新在前（倒序）', String(guids[0]) >= String(guids[guids.length - 1]));
  const missing = items.filter((i) =>
    !fs.existsSync(path.join(dist, 'weekly', String(i.guid?.['#text'] ?? i.guid), 'index.html')));
  check('周报链接 dist 实存', missing.length === 0);
  check('weekly 无 pubDate（日期精度不合成午夜）',
    !fs.readFileSync(weeklyPath, 'utf-8').includes('<pubDate>'));
}

console.log('[3] T10（真实数据半项）：时间精度混合');
{
  const raw = fs.readFileSync(feedPath, 'utf-8');
  const doc = parser.parse(raw);
  const items = doc.rss.channel.item;
  const withDate = items.filter((i) => i.pubDate);
  const withoutDate = items.filter((i) => !i.pubDate);
  check('存在混合形态（有/无 pubDate 并存）', withDate.length > 0 && withoutDate.length > 0,
    `有 ${withDate.length} 无 ${withoutDate.length}`);
  check('pubDate 全为 RFC822 UTC（GMT 结尾）',
    withDate.every((i) => / GMT$/.test(String(i.pubDate))));
  check('无 pubDate 条目的描述含日期精度说明',
    withoutDate.every((i) => String(i.description).includes('日期精度')));
  check('channel 无 lastBuildDate（不用构建时间冒充）', !raw.includes('lastBuildDate'));
}

console.log('[4] T09：修订保 GUID / withdrawn 退出（单元 fixture）');
{
  const base = 'https://daily.maas.click';
  const rec = {
    id: 'obs_' + 'a'.repeat(64), revision: 1, status: 'active',
    recordType: 'source_observation', providerId: 'openai',
    observedAt: null, observationDate: '2026-09-15', timePrecision: 'date',
    title: '原标题', summary: '原摘要', summaryOrigin: 'rule',
    changeType: 'source_updated',
    links: { permalink: '/item/x/' },
  };
  const v1 = changesToFeedItems([rec], base);
  const v2 = changesToFeedItems([{ ...rec, title: '新标题', summary: '新摘要', revision: 2 }], base);
  check('修订后 GUID 不变', v1[0].guid === v2[0].guid);
  check('修订后内容更新', v2[0].title === '新标题' && v2[0].description.includes('新摘要'));
  const wd = changesToFeedItems([{ ...rec, status: 'withdrawn' }], base);
  check('withdrawn 退出默认 feed', wd.length === 0);
}

console.log('[5] T10（单元）：date/datetime 混合');
{
  const mk = (id, precision, observedAt) => ({
    id, revision: 1, status: 'active', recordType: 'price_change',
    providerId: 'openai', observedAt, observationDate: '2026-09-15',
    timePrecision: precision, title: 't', summary: null, summaryOrigin: null,
    changeType: 'newly_observed',
    price: { model: 'm', component: 'input', currency: 'USD',
             beforeAmount: null, afterAmount: '1.000000',
             unitQuantity: 1000000, unitName: 'token' },
    links: { permalink: `/item/${id}/` },
  });
  const items = changesToFeedItems([
    mk('price_' + '1'.repeat(64), 'datetime', '2026-09-15T10:00:00Z'),
    mk('price_' + '2'.repeat(64), 'date', null),
  ], 'https://daily.maas.click');
  check('datetime → pubDateIso 有值', items[0].pubDateIso === '2026-09-15T10:00:00Z');
  check('date → pubDateIso null（不合成午夜）', items[1].pubDateIso === null);
  check('rfc2822Utc 固定 UTC（+08:00 → UTC 同时区换算）', rfc2822Utc('2026-09-15T23:59:59+08:00') === 'Tue, 15 Sep 2026 15:59:59 GMT');
}

console.log('[6] T11：注入攻击（XML/HTML/控制字符/超长）');
{
  const evil = {
    id: 'obs_' + 'e'.repeat(64), revision: 1, status: 'active',
    recordType: 'source_observation', providerId: 'openai',
    observedAt: null, observationDate: '2026-09-15', timePrecision: 'date',
    title: `</title><script>alert("xss-marker")</script>]]>\x01\x02${'T'.repeat(10000)}`,
    summary: 'A'.repeat(10000), summaryOrigin: 'rule',
    changeType: 'source_updated', links: { permalink: '/item/x/' },
  };
  const items = changesToFeedItems([evil], 'https://daily.maas.click');
  const xml = buildRss20({ title: 't', link: 'https://x.example', description: 'd' }, items);
  // 可重新解析
  let reparsed = null;
  try { reparsed = parser.parse(xml); } catch { /* */ }
  check('注入后 feed 仍可解析', reparsed !== null);
  check('无未转义 <script>', !xml.includes('<script>alert'));
  check('控制字符被剥离', !/[\x01\x02]/.test(xml));
  // 截断发生在 buildRss20 组装层（XML 内的 title/description）——解析回来看
  const rawItems = reparsed?.rss?.channel?.item ?? [];
  const one = Array.isArray(rawItems) ? rawItems[0] : rawItems;
  const titleInXml = one?.title ?? '';
  const descInXml = one?.description ?? '';
  check('超长截断（XML 内 title ≤ 200 码点+省略号）',
    Array.from(titleInXml).length <= 201 && titleInXml.endsWith('…'));
  check('超长 description 截断', Array.from(descInXml).length <= 601);
  // 构建错误不泄露原文与路径（非法时间场景）
  let errMsg = '';
  try { rfc2822Utc('not-a-date'); } catch (e) { errMsg = e.message; }
  check('错误信息不含本机路径', !errMsg.includes('/Users/') && !errMsg.includes('/home/'));
}

console.log('[7] T08（单元级）：确定性');
{
  const release = loadVerifiedRelease(undefined, { select: ['changes', 'weekly'] });
  const a = buildRss20({ title: 't', link: 'https://x.example', description: 'd' },
    changesToFeedItems(release.changes, 'https://daily.maas.click'));
  const b = buildRss20({ title: 't', link: 'https://x.example', description: 'd' },
    changesToFeedItems(release.changes, 'https://daily.maas.click'));
  check('同输入双调用逐字节相同', Buffer.compare(Buffer.from(a), Buffer.from(b)) === 0);
  const src = fs.readFileSync(path.join(siteRoot, 'src', 'lib', 'feed-build.ts'), 'utf-8')
    .split('\n').filter((l) => !l.trim().startsWith('*') && !l.trim().startsWith('//')).join('\n');
  check('生成器源码（非注释）无 Date.now/Math.random',
    !src.includes('Date.now') && !src.includes('Math.random'));
}

console.log('[8] T16 + 复验 P1-1：release 校验链（6 类反例）');
{
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 't05-rss-'));
  const VER = 'ds_' + '1'.repeat(64);
  const mkRelease = (mutate) => {
    // 基础合法迷你 release；mutate(manifest 对象, releaseDir) 做定向破坏
    const dir = fs.mkdtempSync(path.join(tmp, 'rel-'));
    const rel = path.join(dir, 'releases', VER);
    fs.mkdirSync(rel, { recursive: true });
    const changes = JSON.stringify([]);
    fs.writeFileSync(path.join(rel, 'changes.json'), changes);
    const sha = createHash('sha256').update(changes).digest('hex');
    const manifest = {
      schemaVersion: '1.0', datasetVersion: VER,
      dataThrough: '2026-09-16', coverage: {},
      files: [{ path: `releases/${VER}/changes.json`, sha256: sha, bytes: changes.length }],
    };
    mutate?.(manifest, rel, dir);
    fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(manifest));
    return dir;
  };
  const tryLoad = (dir, select = ['changes']) => {
    try { loadVerifiedRelease(dir, { select }); return { ok: true }; }
    catch (e) { return { ok: false, msg: e.message }; }
  };
  try {
    // 8a 目录缺失
    check('目录缺失 → throw', !tryLoad(path.join(tmp, 'no-such')).ok);
    // 8b 合法基线（正确 hash）——正常加载
    const good = tryLoad(mkRelease());
    check('合法迷你 release 通过', good.ok);
    // P1-1 反例 1：changes.json 在磁盘存在，但从 manifest.files 删除
    const r1 = tryLoad(mkRelease((m) => { m.files = []; }));
    check('清单删除后 select 文件 → 拒（防 TAMPERED 绕过）',
      !r1.ok && r1.msg.includes('不在 manifest 清单'),
      `实得: ${r1.ok ? '通过(漏洞!)' : r1.msg.slice(0, 50)}`);
    // P1-1 反例 2：manifest 条目重复
    const r2 = tryLoad(mkRelease((m) => {
      m.files.push({ ...m.files[0] });
    }));
    check('清单条目重复 → 拒', !r2.ok && r2.msg.includes('重复'));
    // P1-1 反例 3：../ 路径逃逸
    const r3 = tryLoad(mkRelease((m) => {
      m.files[0].path = `releases/${VER}/../../evil.json`;
    }));
    check('../ 路径逃逸 → 拒', !r3.ok && (r3.msg.includes('越界') || r3.msg.includes('逃逸')));
    // P1-1 反例 4：其他 datasetVersion 路径（版本错位）
    const other = 'ds_' + '2'.repeat(64);
    const r4 = tryLoad(mkRelease((m) => {
      m.files[0].path = `releases/${other}/changes.json`;
    }));
    check('其他版本目录 → 拒（版本错位）', !r4.ok && r4.msg.includes('越界'));
    // P1-1 反例 5：bytes 篡改
    const r5 = tryLoad(mkRelease((m) => { m.files[0].bytes = 999; }));
    check('bytes 篡改 → 拒', !r5.ok && r5.msg.includes('bytes'));
    // P1-1 反例 6：hash 篡改
    const r6 = tryLoad(mkRelease((m) => { m.files[0].sha256 = '0'.repeat(64); }));
    check('sha256 篡改 → 拒', !r6.ok && r6.msg.includes('sha256'));
    // P1-1 补充：datasetVersion 格式非法
    const r7 = tryLoad(mkRelease((m) => { m.datasetVersion = 'ds_bad'; }));
    check('datasetVersion 格式非法 → 拒', !r7.ok && r7.msg.includes('datasetVersion'));
    // P1-1 补充：weekly 正常加载（双集合）
    const dir = mkRelease();
    const rel = path.join(dir, 'releases', VER);
    const weekly = JSON.stringify([]);
    fs.writeFileSync(path.join(rel, 'weekly.json'), weekly);
    const m = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf-8'));
    m.files.push({ path: `releases/${VER}/weekly.json`,
      sha256: createHash('sha256').update(weekly).digest('hex'), bytes: weekly.length });
    fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(m));
    const both = tryLoad(dir, ['changes', 'weekly']);
    check('合法 changes+weekly 双集合加载', both.ok);
    // 错误信息不泄露绝对路径（全部反例）
    const msgs = [r1, r2, r3, r4, r5, r6, r7].map((r) => r.msg).join(' ');
    check('所有错误不泄露本机路径', !msgs.includes('/Users/') && !msgs.includes(tmp));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

console.log('[9] T12：链接遍历（feed + 页面 + llms.txt）');
{
  const urls = new Set();
  for (const f of [feedPath, weeklyPath]) {
    const doc = parser.parse(fs.readFileSync(f, 'utf-8'));
    for (const i of doc.rss.channel.item ?? []) urls.add(String(i.link));
  }
  const llms = path.join(dist, 'llms.txt');
  if (fs.existsSync(llms)) {
    for (const m of fs.readFileSync(llms, 'utf-8').matchAll(/https?:\/\/[^\s)\]]+/g)) {
      urls.add(m[0]);
    }
  }
  const external = [...urls].filter((u) => !u.startsWith('https://daily.maas.click'));
  check('外部 URL 全为 canonical HTTPS', external.length === 0, String(external.slice(0, 3)));
  const internal = [...urls].filter((u) => u.startsWith('https://daily.maas.click'));
  const missing = internal.filter((u) => {
    const p = new URL(u).pathname.replace(/\/$/, '');
    return !fs.existsSync(path.join(dist, p, 'index.html'))
      && !fs.existsSync(path.join(dist, p));
  });
  check('内部链接 dist 实存', missing.length === 0, `缺失: ${missing.slice(0, 3)}`);
}

console.log(failed === 0 ? '\n全部通过 ✓' : `\n${failed} 项失败 ✗`);
process.exit(failed === 0 ? 0 : 1);
