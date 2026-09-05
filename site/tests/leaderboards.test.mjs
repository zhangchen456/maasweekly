// 榜单数据完整性测试：schema、排名单调、新鲜度、数值健全、vendor logo 命中。
// 运行：node site/tests/leaderboards.test.mjs（从任意 cwd）
import { logoFor } from '../src/lib/platforms.ts';
import { readFileSync, existsSync } from 'node:fs';
import assert from 'node:assert/strict';

const root = new URL('../../', import.meta.url);
const readBoard = (name) =>
  JSON.parse(readFileSync(new URL(`site/src/data/leaderboards/${name}.json`, root), 'utf-8'));

const MANUAL_BOARDS = ['lmarena', 'aa', 'superclue', 'swebench', 'terminal-bench'];
// C3 接入自动抓取后启用：['openrouter', 'openrouter_market_share', 'openrouter_session_cost', 'openrouter_apps']
const AUTO_BOARDS = [];
const SCORE_KEY = { lmarena: 'elo', aa: 'score', superclue: 'score', swebench: 'score', 'terminal-bench': 'score' };

// 榜单 vendor 中暂无官方 logo 的厂商（新增厂商进榜应尽量补映射/logo 而非扩此清单）
const EXEMPT_VENDORS = new Set([
  'Meta', 'NVIDIA', 'Qwen', '腾讯', '美团', '字节跳动', '阿里云',
  '百度千帆', 'Google Gemini API', 'Perplexity',
]);
assert.ok(EXEMPT_VENDORS.size <= 24, '豁免清单长度上限，防止无限膨胀');

const daysAgo = (dateStr) => (Date.now() - new Date(`${dateStr}T00:00:00Z`)) / 86400000;
const FRESHNESS_DAYS = { daily: 4, weekly: 10, monthly: 45, auto: 4, session_cost: 12 };

function checkBoard(name, board) {
  const label = `${name}.json`;
  assert.ok(board.source, `${label}: 缺 source`);
  assert.ok(board.source_url, `${label}: 缺 source_url`);
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(board.snapshot_date), `${label}: snapshot_date 格式`);
  assert.equal(typeof board.manual, 'boolean', `${label}: manual 必须是布尔`);
  if (board.manual) assert.ok(board.update_cycle, `${label}: 手工榜必须带 update_cycle`);

  const rows = board.top ?? board.shares ?? board.popular ?? [];
  assert.ok(rows.length >= 3, `${label}: top 条目过少`);
  let prevRank = 1;
  for (const row of rows) {
    assert.ok(row.rank >= prevRank, `${label}: rank 必须非降（${row.rank} < ${prevRank}）`);
    assert.ok(row.model || row.vendor || row.app_name, `${label}: 行缺少模型/厂商/应用名`);
    if (row.rank > prevRank) prevRank = row.rank;
  }
}

function checkFreshness(name, board) {
  const label = `${name}.json`;
  const key = name === 'openrouter_session_cost' ? 'session_cost'
    : AUTO_BOARDS.includes(name) ? 'auto'
    : board.update_cycle;
  const limit = FRESHNESS_DAYS[key] ?? 45;
  const age = daysAgo(board.snapshot_date);
  assert.ok(age <= limit, `${label}: 快照过期（${Math.floor(age)} 天 > ${limit} 天），请更新数据`);
  assert.ok(age >= -1, `${label}: snapshot_date 在未来？`);
}

function checkScores(name, board) {
  const label = `${name}.json`;
  for (const row of board.top ?? []) {
    if (row.elo != null) assert.ok(row.elo > 1000 && row.elo < 2000, `${label}: elo 异常 ${row.elo}`);
    if (row.score != null) assert.ok(row.score > 0 && row.score <= 100, `${label}: score 异常 ${row.score}`);
    if (row.tokens_t != null) assert.ok(row.tokens_t > 0, `${label}: tokens_t 异常`);
    if (row.change_pct != null) assert.ok(Math.abs(row.change_pct) <= 1000, `${label}: change_pct 越界 ${row.change_pct}`);
    if (row.share_pct != null) assert.ok(row.share_pct > 0 && row.share_pct < 100, `${label}: share_pct 异常 ${row.share_pct}`);
  }
  if (board.shares) {
    const total = board.shares.reduce((s, r) => s + r.share_pct, 0);
    assert.ok(total > 90 && total <= 100.5, `${label}: share_pct 合计 ${total.toFixed(1)} 超出容差`);
  }
}

function checkVendors(name, board) {
  const label = `${name}.json`;
  for (const row of board.top ?? board.shares ?? []) {
    if (!row.vendor) continue;
    if (logoFor(row.vendor)) continue;
    assert.ok(EXEMPT_VENDORS.has(row.vendor),
      `${label}: vendor "${row.vendor}" 无 logo 且不在豁免清单——请补 logo 注册表或 VENDOR_MAP 映射`);
  }
}

for (const name of [...MANUAL_BOARDS, ...AUTO_BOARDS]) {
  const board = readBoard(name);
  checkBoard(name, board);
  checkFreshness(name, board);
  checkScores(name, board);
  checkVendors(name, board);
  if (AUTO_BOARDS.includes(name)) assert.ok(board.as_of, `${name}.json: 自动榜必须带 as_of`);
}

// 手工榜豁免日期：aa/superclue 等 8 月快照已被本次更新覆盖，不再单独豁免。
// 但历史上 C1 提交时 openrouter.json（8-31）尚未接入自动抓取，跳过其检查：
const orFile = new URL('site/src/data/leaderboards/openrouter.json', root);
if (existsSync(orFile)) {
  // 现存 openrouter.json 为旧手工快照，C3 接管前不做 auto 断言，仅验证可解析
  JSON.parse(readFileSync(orFile, 'utf-8'));
}

console.log('Leaderboards: schema、排名、新鲜度、数值与 vendor 校验通过。');
