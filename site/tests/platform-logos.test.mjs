import { logoFor } from '../src/lib/platforms.ts';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
const root = new URL('../../', import.meta.url);
const read = (path) => JSON.parse(readFileSync(new URL(path, root)));
const config = read('pipeline/config/maas_official_sources.json');
const registry = read('site/src/data/platform-logos.json');
for (const platform of [...config.platforms, ...config.industry_sources]) assert.ok(logoFor(platform.name), platform.name);
for (const platform of registry) {
  for (const alias of [platform.id, platform.name, ...platform.aliases]) assert.equal(logoFor(alias), platform.file);
  const file = new URL(`site/public${platform.file}`, root);
  assert.ok(existsSync(file));
  assert.equal(createHash('sha256').update(readFileSync(file)).digest('hex'), platform.sha256);
}
for (const day of read('site/src/data/daily_changes.json').days) {
  for (const item of [...day.changed, ...(day.highlights || [])]) assert.ok(logoFor(item.platform), item.platform);
}
assert.equal(logoFor(' OPEN AI '), logoFor('OpenAI'));
assert.notEqual(logoFor('Gemini'), logoFor('Vertex AI'));
assert.equal(logoFor('unknown-platform'), undefined);
console.log('Logo registry: platforms, aliases, daily data and file hashes passed.');

for (const file of readdirSync(new URL('site/src/data/leaderboards/', root)).filter(f=>f.endsWith('.json'))) {
  const visit = (value) => {
    if (Array.isArray(value)) return value.forEach(visit);
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (['vendor','app_name','harness'].includes(key) && typeof child === 'string') assert.ok(logoFor(child), `${file}: missing logo for ${child}`);
      else if (typeof child === 'object') visit(child);
    }
  };
  visit(read(`site/src/data/leaderboards/${file}`));
}
console.log('All leaderboard vendors and applications have local logo mappings.');
