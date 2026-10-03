import { AccountError } from './account-store.js';

// Only product preferences are accepted; never accept arbitrary account identifiers.
const text = (v: unknown, max = 200) => typeof v === 'string' && v.length <= max;
const number = (v: unknown, min: number, max: number) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
const strings = (v: unknown, max: number) => Array.isArray(v) && v.length <= max && v.every(x => text(x));
export function validateAccountState(key: unknown, value: unknown): { key: string; value: unknown } {
  if (typeof key !== 'string' || !value || typeof value !== 'object' || Array.isArray(value) || JSON.stringify(value).length > 6000) throw new AccountError(400, 'invalid_state', '保存的数据格式不正确');
  const v = value as Record<string, unknown>;
  const keys = (allowed: string[]) => Object.keys(v).every(k => allowed.includes(k));
  let valid = false;
  if (key === 'appearance') valid = keys(['theme']) && typeof v.theme === 'string' && ['light', 'dark'].includes(v.theme);
  if (key === 'homePrices') valid = keys(['currency', 'fx']) && typeof v.currency === 'string' && ['CNY', 'USD'].includes(v.currency) && (v.fx === null || number(v.fx, .01, 1000));
  if (key === 'explore') valid = keys(['followed', 'query', 'platform', 'type', 'onlyFollowing']) && strings(v.followed, 50) && text(v.query) && text(v.platform) && text(v.type, 40) && typeof v.onlyFollowing === 'boolean';
  if (key === 'priceWorkspace') valid = keys(['provider', 'query', 'sort', 'modelId', 'familyId', 'selected', 'variants', 'component', 'input', 'output', 'fx'])
    && text(v.provider) && text(v.query) && typeof v.sort === 'string' && ['name', 'input', 'output'].includes(v.sort)
    && (v.modelId === null || text(v.modelId)) && (v.familyId === null || text(v.familyId))
    && strings(v.selected, 5) && typeof v.component === 'string' && ['input', 'output', 'total', 'cache_read', 'cache_write'].includes(v.component)
    && number(v.input, 0, 1000000) && number(v.output, 0, 1000000) && (v.fx === null || number(v.fx, .01, 1000))
    && Array.isArray(v.variants) && v.variants.length <= 5 && v.variants.every(x => Array.isArray(x) && x.length === 2 && text(x[0]) && text(x[1], 1500));
  if (!valid) throw new AccountError(400, 'invalid_state', '保存的数据格式不正确');
  return { key, value };
}
