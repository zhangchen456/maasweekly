// Operational freshness/coverage advisories. Stale optional data must not freeze publication.
// Use --strict for a dedicated monitor; release regressions use the default advisory mode.
import {readFileSync, readdirSync} from 'node:fs';
const data = new URL('../src/data/', import.meta.url);
const read = path => JSON.parse(readFileSync(new URL(path, data), 'utf8'));
const issues = [];
const now = Date.now();
const limits = {daily:4, weekly:10, monthly:45, auto:4, session_cost:12, manual:45};
for (const file of readdirSync(new URL('leaderboards/', data)).filter(f => f.endsWith('.json'))) {
 const board = read(`leaderboards/${file}`);
 const limit = file === 'openrouter_session_cost.json' ? limits.session_cost : board.manual ? limits[board.update_cycle] ?? 45 : limits.auto;
 const age = (now - Date.parse(`${board.snapshot_date}T00:00:00Z`)) / 86400000;
 if (!Number.isFinite(age) || age < -1 || age > limit) issues.push(`${file}: snapshot ${board.snapshot_date}, age ${age.toFixed(1)} days, limit ${limit}`);
}
const ledger = read('pricing/ledger.json');
const age = (now / 1000 - ledger.meta.published_at) / 86400;
if (!Number.isFinite(age) || age < -1 || age > 4) issues.push(`pricing ledger: age ${age.toFixed(1)} days, limit 4`);
if (ledger.providers.length < 6) issues.push(`pricing coverage: ${ledger.providers.length} providers, expected at least 6`);
if (ledger.prices.length < 50) issues.push(`pricing coverage: ${ledger.prices.length} records, expected at least 50`);
for (const issue of issues) {
 if (process.env.GITHUB_ACTIONS === 'true') console.log(`::warning title=Data health::${issue.replaceAll('%','%25').replaceAll('\r','%0D').replaceAll('\n','%0A')}`);
 else console.warn(`Data health warning: ${issue}`);
}
console.log(`Data health: ${issues.length} advisories (content/schema regressions remain blocking)`);
if (process.argv.includes('--strict') && issues.length) process.exitCode = 1;
