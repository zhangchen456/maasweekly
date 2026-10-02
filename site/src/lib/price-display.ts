import type { PriceRecord } from './release.ts';

export const providerLabels: Record<string, string> = {
  openai: 'OpenAI', anthropic: 'Anthropic', google: 'Google', deepseek: 'DeepSeek',
  alibaba: '阿里百炼', volcengine: '火山引擎', zhipu: '智谱', kimi: 'Kimi',
  baidu: '百度', xai: 'xAI', mistral: 'Mistral', cohere: 'Cohere',
  minimax: 'MiniMax', siliconflow: 'SiliconFlow', tencent: '腾讯', xfyun: '讯飞',
};
export const componentLabels: Record<string, string> = {
  input: '输入', output: '输出', cache_read: '缓存读取',
  cache_write: '缓存写入', cache_write_5m: '缓存写入（5 分钟）', cache_write_1h: '缓存写入（1 小时）',
};
const modeLabels: Record<string, string> = { realtime: '实时', batch: '批处理' };
const qualityLabels: Record<string, string> = { fresh: '最近抓取成功', stale: '更新失败，沿用旧数据', unknown: '更新状态未知' };
const evidenceLabels: Record<string, string> = { complete: '证据完整', partial: '证据不完整', unavailable: '证据不可用' };

export function priceUnit(quantity: number, name: string): string {
  return quantity === 1000000 && /^tokens?$/i.test(name) ? '百万 token' : `${quantity.toLocaleString('en-US')} ${name}`;
}

export function priceCells(price: PriceRecord): string[] {
  return [
    providerLabels[price.providerId] ?? price.providerId,
    price.modelKey,
    componentLabels[price.component] ?? price.component,
    `${price.amount} ${price.currency} / ${priceUnit(price.unitQuantity, price.unitName)}`,
    price.region,
    `${modeLabels[price.billingMode] ?? price.billingMode} / ${price.serviceTier}`,
    price.contextBand ? JSON.stringify(price.contextBand) : '来源未单列',
    price.timeCondition ? JSON.stringify(price.timeCondition) : '来源未单列',
    price.effectiveAt ?? '来源未注明',
    price.observedAt,
    [qualityLabels[price.quality.state] ?? price.quality.state, price.quality.reason,
      price.quality.lastSuccessAt ? `最近成功：${price.quality.lastSuccessAt}` : null,
      evidenceLabels[price.evidenceStatus] ?? price.evidenceStatus].filter(Boolean).join('；'),
  ];
}
export const priceHeaders = ['平台', 'API 模型名', '计费项', '价格 / 原始单位', '地区',
  '计费方式 / 服务档位', '上下文条件（原值）', '时间条件（原值）', '官方生效时间', '观察时间', '数据与证据状态'];


export const englishProviderLabels: Record<string, string> = { ...providerLabels,
  alibaba: 'Alibaba Cloud Model Studio', volcengine: 'Volcengine', zhipu: 'Zhipu AI',
  baidu: 'Baidu', tencent: 'Tencent', xfyun: 'iFlytek' };
export const englishPriceHeaders = ['Platform', 'API model name', 'Billing component', 'Price / original unit', 'Region',
  'Billing mode / service tier', 'Context condition (source value)', 'Time condition (source value)',
  'Official effective time', 'Observed at', 'Data and evidence status'];
const englishComponents: Record<string, string> = { input: 'Input', output: 'Output', cache_read: 'Cache read',
    cache_write: 'Cache write', cache_write_5m: 'Cache write (5 minutes)', cache_write_1h: 'Cache write (1 hour)' };
const englishQuality: Record<string, string> = { fresh: 'Latest fetch succeeded', stale: 'Update failed; previous data retained', unknown: 'Update status unknown' };
const englishEvidence: Record<string, string> = { complete: 'Complete evidence', partial: 'Partial evidence', unavailable: 'Evidence unavailable' };

export function englishPriceCells(price: PriceRecord): string[] {
  const reason = price.quality.reason === '门禁全拒（0 条），疑似结构漂移'
    ? 'Validation rejected all records (0 accepted); possible source structure change'
    : price.quality.reason;
  return [englishProviderLabels[price.providerId] ?? price.providerId, price.modelKey,
    englishComponents[price.component] ?? price.component,
    `${price.amount} ${price.currency} / ${price.unitQuantity.toLocaleString('en-US')} ${price.unitName}`,
    price.region, `${price.billingMode} / ${price.serviceTier}`,
    price.contextBand ? JSON.stringify(price.contextBand) : 'Not separately specified by source',
    price.timeCondition ? JSON.stringify(price.timeCondition) : 'Not separately specified by source',
    price.effectiveAt ?? 'Not stated by source', price.observedAt,
    [englishQuality[price.quality.state] ?? price.quality.state, reason,
      price.quality.lastSuccessAt ? `Last success: ${price.quality.lastSuccessAt}` : null,
      englishEvidence[price.evidenceStatus] ?? price.evidenceStatus].filter(Boolean).join('; ')];
}
