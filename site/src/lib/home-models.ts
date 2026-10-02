import { HOME_MODEL_GROUPS, HOME_MODEL_REVIEWED_AT } from '../config/home-model-selection.ts';
import { modelIndex } from './model-pages.ts';
import type { PriceRecord } from './release';
import type { HomeModelPick } from '../config/home-model-selection.ts';

export const quoteScenario = (p: PriceRecord) => JSON.stringify([p.providerId, p.sourceId, p.modelKey, p.currency, p.unitName, p.unitQuantity, p.region, p.billingMode, p.serviceTier, p.contextBand, p.timeCondition]);
/** A disclosed domestic standard scenario; never rank by amount or mix output conditions. */
export function selectHomeQuote(prices: PriceRecord[], providerId: string) {
  const preferredSource = ({ google: 'google-gemini-pricing', anthropic: 'anthropic-pricing' } as Record<string, string>)[providerId];
  const providerPrices = prices.filter(p => p.providerId === providerId && (!preferredSource || p.sourceId === preferredSource));
  const latestObserved = Math.max(...providerPrices.map(p => Date.parse(p.observedAt)));
  const eligible = providerPrices.filter(p => Date.parse(p.observedAt) === latestObserved && p.quality.state === 'fresh' && p.evidenceStatus === 'complete' && p.billingMode === 'realtime' && p.serviceTier === 'standard');
  const score = (p: PriceRecord): number[] => [p.region === 'cn' ? 0 : p.region === 'global' ? 1 : 2, !p.timeCondition ? 0 : p.timeCondition.period === 'peak' ? 1 : 2, Number(p.contextBand?.min ?? 0), Number(p.contextBand?.max ?? Number.MAX_SAFE_INTEGER)];
  const inputs = eligible.filter(p => p.component === 'input').sort((a, b) => {
    const av = score(a), bv = score(b);
    for (let i = 0; i < av.length; i++) if (av[i] !== bv[i]) return av[i]! - bv[i]!;
    return a.id.localeCompare(b.id);
  });
  const input = inputs[0];
  const same = input ? eligible.filter(p => quoteScenario(p) === quoteScenario(input)) : [];
  return { input, output: same.find(p => p.component === 'output'), cache: same.find(p => p.component === 'cache_read') };
}
export function homeModelGroups() {
  const index = modelIndex();
  return HOME_MODEL_GROUPS.map(group => ({ ...group, reviewedAt: HOME_MODEL_REVIEWED_AT, models: group.models.map((pick: HomeModelPick) => {
    const prices = index.prices.get(pick.modelId) ?? [];
    const quote = pick.holdQuoteReason ? { input: undefined, output: undefined, cache: undefined } : selectHomeQuote(prices, pick.providerId);
    const input = quote.input;
    const region = input?.region ? ({ cn: '中国内地', global: '全球', us: '美国', eu: '欧洲' } as Record<string,string>)[input.region] ?? input.region : '地区未单列';
    const condition = input ? [region, '实时', '标准档', input.contextBand ? `上下文 ${input.contextBand.min ?? 0}–${input.contextBand.max ?? '不限'} tokens` : null, input.timeCondition ? `时段 ${input.timeCondition.period === 'peak' ? '高峰' : input.timeCondition.period === 'off_peak' ? '非高峰' : input.timeCondition.period === 'promotional' ? '优惠期间' : input.timeCondition.period ?? '详见来源'}（${input.timeCondition.tz ?? '来源时区'}）${input.timeCondition.schedule ? ` · ${input.timeCondition.schedule}` : ''}` : null].filter(Boolean).join(' · ') : '';
    const conditionEn = input ? [input.region ?? 'Region not listed', 'Realtime', 'Standard tier', input.contextBand ? `Context ${input.contextBand.min ?? 0}–${input.contextBand.max ?? 'unbounded'} tokens` : null, input.timeCondition ? `${input.timeCondition.period ?? 'Time condition'} (${input.timeCondition.tz ?? 'source timezone'})${input.timeCondition.schedule ? ` · ${input.timeCondition.schedule}` : ''}` : null].filter(Boolean).join(' · ') : '';
    return { pick, ...quote, condition, conditionEn, modelHref: index.models.has(pick.modelId) ? `/model/${pick.modelId}/` : null,
      quoteStatus: pick.holdQuoteReason ?? (input ? '快照报价' : prices.length ? '证据或新鲜度待补齐' : '报价待补齐') };
  }) }));
}
