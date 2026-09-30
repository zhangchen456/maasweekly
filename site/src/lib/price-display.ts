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

export function priceCells(price: PriceRecord): string[] {
  return [
    providerLabels[price.providerId] ?? price.providerId,
    price.modelKey,
    componentLabels[price.component] ?? price.component,
    `${price.amount} ${price.currency} / ${price.unitQuantity.toLocaleString('en-US')} ${price.unitName}`,
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

