import { loadVerifiedRelease } from './release.ts';
import { safeWebUrl } from './seo.ts';

// A build reads one verified snapshot; pages never query production while building.
let snapshot: ReturnType<typeof loadVerifiedRelease> | undefined;
export function modelRelease() {
  return snapshot ??= loadVerifiedRelease(undefined, {
    select: ['modelIdentities', 'prices', 'changes', 'evidence', 'weekly'],
  });
}

export { providerLabels, priceCells, priceHeaders } from './price-display.ts';

type Release = ReturnType<typeof modelRelease>;
type Model = NonNullable<Release['modelIdentities']>['models'][number];
type Price = NonNullable<Release['prices']>[number];
type Change = NonNullable<Release['changes']>[number];

let index: ReturnType<typeof createModelIndex> | undefined;
/** One pass per verified build snapshot; preserve release ordering within each model. */
export function createModelIndex(release: Release) {
  const fromDate = new Date(`${release.dataThrough}T00:00:00Z`);
  fromDate.setUTCDate(fromDate.getUTCDate() - 89);
  const toDate = new Date(`${release.dataThrough}T00:00:00Z`);
  toDate.setUTCDate(toDate.getUTCDate() + 1);
  const from = fromDate.toISOString().slice(0, 10);
  const to = toDate.toISOString().slice(0, 10);
  const models = new Map<string, Model>(release.modelIdentities!.models.map(m => [m.modelId, m]));
  const prices = new Map<string, Price[]>();
  const changes = new Map<string, Change[]>();
  const evidence = new Map(release.evidence!.map(e => [e.id, e]));
  for (const price of release.prices!) {
    if (!price.modelId) continue;
    const rows = prices.get(price.modelId) ?? [];
    rows.push(price); prices.set(price.modelId, rows);
  }
  for (const change of release.changes!) {
    if (!change.modelId || change.status !== 'active' || change.observationDate < from || change.observationDate >= to) continue;
    const rows = changes.get(change.modelId) ?? [];
    if (rows.length < 10) rows.push(change);
    changes.set(change.modelId, rows);
  }
  return { models, prices, changes, evidence, from, to };
}
export function modelIndex() { return index ??= createModelIndex(modelRelease()); }

export function modelPage(modelId: string) {
  const release = modelRelease();
  const { models, prices: priceIndex, changes: changeIndex, evidence, from, to } = modelIndex();
  const model = models.get(modelId);
  if (!model) throw new Error('[model] unknown catalog identity');
  const prices = priceIndex.get(modelId) ?? [];
  const changes = changeIndex.get(modelId) ?? [];
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
  return featuredIds.filter(id => modelIndex().models.has(id))
    .map(modelPage).filter(page => page.prices.length > 0
      && page.prices.every(p => p.quality.state === 'fresh' && p.evidenceStatus === 'complete'));
}
