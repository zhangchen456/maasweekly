// 价格台账数据完整性测试：schema、八家齐全、数值非负、新鲜度、partial 上限。
// 运行：node site/tests/pricing.test.mjs（从任意 cwd）
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

const root = new URL('../../', import.meta.url);
const ledger = JSON.parse(
  readFileSync(new URL('site/src/data/pricing/ledger.json', root), 'utf-8'));

// meta
assert.ok(ledger.meta, '缺 meta');
assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(String(ledger.meta.artifact_version)), 'artifact_version 须为日期');
assert.equal(typeof ledger.meta.published_at, 'number', 'published_at 须为 epoch 秒');
const ageDays = (Date.now() / 1000 - ledger.meta.published_at) / 86400;
assert.ok(ageDays <= 4, `数据过期（${ageDays.toFixed(1)} 天前），抓取链路可能中断`);

// providers：八家（partial 时允许缺，但 failed_sources 必须显式声明）
const EXPECTED = ['anthropic', 'deepseek', 'doubao', 'glm', 'google', 'kimi', 'openai', 'qwen'];
const failed = new Set(ledger.meta.failed_sources || []);
for (const p of EXPECTED) {
  if (!ledger.providers.includes(p)) {
    assert.ok(failed.has(`${p}:pricing`),
      `${p} 缺失且未声明 failed（providers=${ledger.providers}）`);
  }
}
assert.ok(ledger.providers.length >= 6, `可用厂商过少: ${ledger.providers.length}`);

// prices
assert.ok(Array.isArray(ledger.prices) && ledger.prices.length >= 50, 'prices 条目过少');
const COMPONENTS = new Set(['input', 'output', 'cache_read', 'cache_write']);
for (const p of ledger.prices) {
  assert.ok(p.provider && EXPECTED.includes(p.provider), `未知 provider: ${p.provider}`);
  assert.ok(p.model, '缺 model');
  assert.ok(COMPONENTS.has(p.component), `未知 component: ${p.component}`);
  assert.ok(['USD', 'CNY'].includes(p.currency), `未知币种: ${p.currency}`);
  if (p.amount != null) {
    const n = Number(p.amount);
    assert.ok(Number.isFinite(n) && n >= 0, `金额非法: ${p.provider}/${p.model} ${p.amount}`);
    assert.ok(!/[eE]/.test(p.amount), `金额含指数（浮点混入）: ${p.amount}`);
  }
}

// 汇率快照
assert.ok(ledger.fx_snapshot?.rates?.CNY, 'fx_snapshot 缺 CNY 汇率');
assert.ok(ledger.default_currency, '缺 default_currency');

console.log(`Pricing ledger: ${ledger.providers.length} 家 / ${ledger.prices.length} 条价格 / ${new Set(ledger.prices.map((p) => p.model)).size} 模型，校验通过。`);
