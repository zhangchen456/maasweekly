import type { PublicRelease, PriceRecord } from './release.ts';
import type { ModelIdentityCatalog } from '../../../packages/public-contract/entities.ts';
type ComparisonRow = {availability: NonNullable<ModelIdentityCatalog['availabilities']>[number]; platformName: string; input: PriceRecord | undefined; output: PriceRecord | undefined; cache: PriceRecord | undefined};

const scenario = (p: PriceRecord) => JSON.stringify([p.currency, p.unitQuantity, p.unitName,
  p.region, p.billingMode, p.serviceTier, p.contextBand, p.timeCondition]);
/** Prices only pair within one platform, observation and billing scenario. No price ranking. */
export function crossPlatformGroups(release: PublicRelease) {
  const catalog = release.modelIdentities;
  if (!catalog) return [];
  const platforms = new Map((catalog.platforms ?? []).map(p => [p.platformId, p.displayName]));
  const developers = new Map((catalog.developers ?? []).map(d => [d.developerId, d.displayName]));
  return (catalog.upstreamModels ?? []).map(model => {
    const availability = (catalog.availabilities ?? []).filter(a => a.upstreamModelId === model.upstreamModelId);
    const rows = availability.flatMap<ComparisonRow>(a => {
      const prices = (release.prices ?? []).filter(p => p.availabilityId === a.availabilityId);
      const latest = Math.max(...prices.map(p => Date.parse(p.observedAt)));
      const eligible = prices.filter(p => Date.parse(p.observedAt) === latest && p.quality.state === 'fresh'
        && p.evidenceStatus === 'complete' && p.billingMode === 'realtime' && p.serviceTier === 'standard');
      const inputs = eligible.filter(p => p.component === 'input').sort((a,b) =>
        a.region.localeCompare(b.region) || Number(a.contextBand?.min ?? 0) - Number(b.contextBand?.min ?? 0) || a.id.localeCompare(b.id));
      const base = { availability: a, platformName: platforms.get(a.platformId) ?? a.platformId };
      if (!inputs.length) return [{...base, input: undefined, output: undefined, cache: undefined}];
      return inputs.map(input => {
        const matching = eligible.filter(p => scenario(p) === scenario(input));
        return {...base, input, output: matching.find(p => p.component === 'output'), cache: matching.find(p => p.component === 'cache_read')};
      });
    });
    return {model, developerName: developers.get(model.developerId) ?? model.developerId, rows};
  });
}
