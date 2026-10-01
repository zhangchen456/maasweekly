import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Dataset } from '../dataset.js';
import { ReleaseFixture } from './fixture.js';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const site = await import(path.join(repo, 'site/src/lib/release.ts'));
const version = 'ds_' + '1'.repeat(64);
test('site and API reject identical malformed manifests, hashes, references and catalogs', () => {
  const fx = new ReleaseFixture(mkdtempSync(path.join(tmpdir(), 'ar03-contract-')));
  const reset = () => fx.writeRelease(version, { changes: [{ id: 'test', observationDate: '2026-09-01' }] });
  const manifestPath = path.join(fx.root, 'manifest.json');
  const mutateManifest = (fn: (m: any) => void) => { const m = JSON.parse(readFileSync(manifestPath, 'utf8')); fn(m); writeFileSync(manifestPath, JSON.stringify(m)); };
  const mutateCollection = (name: string, value: unknown) => {
    const relative = `releases/${version}/${name}.json`; const data = Buffer.from(JSON.stringify(value)); writeFileSync(path.join(fx.root, relative), data);
    mutateManifest(m => { const entry = m.files.find((f: any) => f.path === relative); entry.bytes = data.length; entry.sha256 = createHash('sha256').update(data).digest('hex'); });
  };
  try {
    reset(); assert.equal(Dataset.load(fx.root).version, site.loadVerifiedRelease(fx.root).datasetVersion);
    const bad = [
      () => mutateManifest(m => { m.schemaVersion = '9'; }),
      () => mutateManifest(m => { m.files.push(m.files[0]); }),
      () => mutateManifest(m => { m.files[0].path = `releases/${version}/../changes.json`; }),
      () => mutateManifest(m => { m.files[0].path = 'releases/ds_' + '2'.repeat(64) + '/changes.json'; }),
      () => mutateManifest(m => { m.files = m.files.filter((f: any) => !f.path.endsWith('model-identities.json')); }),
      () => writeFileSync(path.join(fx.root, `releases/${version}/prices.json`), '["tampered"]'),
      () => mutateCollection('items', []),
      () => mutateCollection('model-identities', { models: [{ modelId: 'test:model', modelName: 'Test', familyId: 'test:family', familyName: 'Missing' }], families: [] }),
    ];
    for (const breakRelease of bad) {
      reset(); breakRelease();
      assert.throws(() => Dataset.load(fx.root)); assert.throws(() => site.loadVerifiedRelease(fx.root));
    }
  } finally { fx.cleanup(); }
});
