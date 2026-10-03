import type { Dataset } from './dataset.js';
import type { ProContent } from './pro-store.js';

/** Run at publication time against a release-validated dataset, never guessed names. */
export function validateEditorial(c: ProContent, ds: Dataset) {
  const catalog=ds.modelIdentities;
  if (c.models.some(id=>!catalog.models.some(m=>m.modelId===id)) || c.families.some(id=>!catalog.families.some(f=>f.familyId===id)) || c.providers.some(id=>!ds.status.providers.some(p=>p.providerId===id))) throw new Error('unregistered scope');
  const linkedModels=new Set<string>(), linkedFamilies=new Set<string>();
  for (const e of c.evidence) {
    const item=ds.itemsById.get(e.id), evidence=ds.evidenceById.get(e.id);
    if (!item && !evidence) throw new Error(`unresolved evidence: ${e.id}`);
    if (item?.status === 'withdrawn') throw new Error(`withdrawn source: ${e.id}`);
    const change=ds.changes.find(change=>change.id===e.id);
    if (change?.modelId) linkedModels.add(change.modelId);
    if (change?.familyId) linkedFamilies.add(change.familyId);
  }
  if (c.models.some(id=>!linkedModels.has(id)) || c.families.some(id=>!linkedFamilies.has(id))) throw new Error('model/family attribution requires explicit evidence linkage');
}
