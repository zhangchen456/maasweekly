import { loadVerifiedRelease } from './release.ts';
import { safeWebUrl } from './seo.ts';

// A build reads one verified snapshot; pages never query production while building.
let snapshot: ReturnType<typeof loadVerifiedRelease> | undefined;
export function modelRelease() {
  return snapshot ??= loadVerifiedRelease(undefined, {
    select: ['modelIdentities', 'prices', 'changes', 'evidence'],
  });
}

export { providerLabels, priceCells, priceHeaders } from './price-display.ts';

export function modelPage(modelId: string) {
  const release = modelRelease();
  const model = release.modelIdentities!.models.find(m => m.modelId === modelId);
  if (!model) throw new Error('[model] unknown catalog identity');
  const prices = release.prices!.filter(p => p.modelId === modelId);
  const fromDate = new Date(`${release.dataThrough}T00:00:00Z`);
  fromDate.setUTCDate(fromDate.getUTCDate() - 89);
  const toDate = new Date(`${release.dataThrough}T00:00:00Z`);
  toDate.setUTCDate(toDate.getUTCDate() + 1);
  const from = fromDate.toISOString().slice(0, 10);
  const to = toDate.toISOString().slice(0, 10);
  const changes = release.changes!.filter(c => c.modelId === modelId && c.status === 'active'
    && c.observationDate >= from && c.observationDate < to).slice(0, 10);
  const evidence = new Map(release.evidence!.map(e => [e.id, e]));
  const sources = [...new Set(prices.map(p => {
    const e = p.evidenceId ? evidence.get(p.evidenceId) : undefined;
    return safeWebUrl(e?.subpageUrl ?? e?.sourceUrl);
  }).filter((url): url is string => Boolean(url)))];
  const keys = [...new Set(prices.map(p => p.modelKey))].sort();
  return { model, prices, changes, sources, keys, from, to,
    dataThrough: release.dataThrough, datasetVersion: release.datasetVersion };
}

const featuredIds = ['deepseek:deepseek-v4-pro', 'alibaba:qwen-plus',
  'alibaba:qwen3-coder-plus', 'google:gemini-2.5-pro', 'zhipu:glm-5.2'];
export function featuredModels() {
  const release = modelRelease();
  return featuredIds.filter(id => release.modelIdentities!.models.some(m => m.modelId === id))
    .map(modelPage).filter(page => page.prices.length > 0
      && page.prices.every(p => p.quality.state === 'fresh' && p.evidenceStatus === 'complete'));
}
