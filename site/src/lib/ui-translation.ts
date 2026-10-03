import { uiEnglish } from './ui-en';
import { localizedRoute } from './locale-routes';
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const segments = Object.keys(uiEnglish).filter(k => k.length >= 2).sort((a,b) => b.length-a.length);
const pattern = new RegExp(segments.map(escape).join('|'), 'g');
export function englishUi(text: string): string {
  const trim = text.trim();
  const archive = trim.match(/^每日动态按周聚合归档，以及 (\d+) 期深度周报。$/);
  if (archive) return `Daily updates grouped by week, plus ${archive[1]} in-depth reports.`;
  const reports = trim.match(/^共 (\d+) 期完整周报，按日期倒序。$/);
  if (reports) return `${reports[1]} complete reports, newest first.`;
  const stats = trim.match(/^(\d+) 项变化 · (\d+) 发布 · (\d+) 调价$/);
  if (stats) return `${stats[1]} changes · ${stats[2]} releases · ${stats[3]} price changes`;
  const price = trim.match(/^每((?:\d|百万).+)$/);
  if (price) return `per ${englishUi(price[1])}`;
  const direct = uiEnglish[trim];
  if (direct) return text.replace(trim, direct);
  const coverage = trim.match(/^截至 ([\d-]+)，本数据集覆盖 ([\d-]+) 至 ([\d-]+)\s*共 (\d+) 条变化记录、(\d+) 条价格事实、(\d+) 条证据、(\d+) 期正式周报。以下是这些数字的产生方法与边界。$/);
  if (coverage) { const [,date,from,to,changes,prices,evidence,reports] = coverage; return `Data through ${date}: ${changes} changes from ${from} to ${to}, ${prices} pricing facts, ${evidence} evidence records and ${reports} published reports. Here is how these figures are produced and what they cover.`; }
  return text.replace(pattern, key => uiEnglish[key])
    .replace(/^(\s*)每\s+/, '$1per ')
    .replace(/(\d+)\s*个模型/g, '$1 models')
    .replace(/(\d+)\s*项信号/g, '$1 signals')
    .replace(/(\d+)\s*条变化/g, '$1 changes');
}
export function englishHref(href: string): string {
  if (!href.startsWith('/') || href.startsWith('//')) return href;
  const match = href.match(/^([^?#]*)([?#].*)?$/)!;
  return (localizedRoute(match[1], 'en') ?? match[1]) + (match[2] ?? '');
}
const decode = (s: string) => s.replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;|&#x27;/g, "'");
const encode = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export function englishHtml(html: string): string {
  // Do not translate executable code, structured data or quoted original evidence.
  return html.replace(/<(script|style|pre|code|blockquote)\b[^>]*>[\s\S]*?<\/\1\s*>|<[^>]+>|[^<]+/gi, token => {
    if (/^<(script|style|pre|code|blockquote)\b/i.test(token)) return token;
    if (token.startsWith('<')) return token.replace(/\b(href|title|placeholder|aria-label|alt)="([^"]*)"/g, (_m, key, value) => `${key}="${encode(key === 'href' ? englishHref(decode(value)) : englishUi(decode(value)))}"`);
    const next = englishUi(decode(token));
    return next === decode(token) ? token : encode(next);
  });
}
