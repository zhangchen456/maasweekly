import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
export function writePublicFixture(root, version, overrides = {}) {
  const collections = { changes: [{ id: 'fixture-change', observationDate: '2026-09-01', evidenceIds: [] }],
    items: [{ id: 'fixture-change' }], prices: [{ id: 'fixture-price', providerId: 'test', modelKey: 'test', component: 'input', factKey: 'test', evidenceId: null }],
    evidence: [], weekly: [], status: { providers: ['test'] }, 'model-identities': { models: [], families: [] }, ...overrides };
  const files = []; fs.mkdirSync(path.join(root, 'releases', version), { recursive: true });
  for (const [name, value] of Object.entries(collections)) {
    const relative = `releases/${version}/${name}.json`; const data = Buffer.from(JSON.stringify(value));
    fs.writeFileSync(path.join(root, relative), data);
    files.push({ path: relative, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex') });
  }
  return { schemaVersion: '1.0', datasetVersion: version, generatedAt: '2026-09-01T00:00:00Z', dataThrough: '2026-09-01', coverage: {}, retainedVersions: [], files };
}
