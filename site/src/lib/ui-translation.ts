import { uiEnglish } from './ui-en';
import { localizedRoute } from './locale-routes';
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const segments = Object.keys(uiEnglish).filter(k => k.length >= 2).sort((a,b) => b.length-a.length);
const pattern = new RegExp(segments.map(escape).join('|'), 'g');
export function englishUi(text: string): string {
  const trim = text.trim();
  const weekTitle = trim.match(/^(\d{4}-W\d{2}) 周归档 — MaaS Daily$/);
  if (weekTitle) return `${weekTitle[1]} Weekly archive — MaaS Daily`;
  const weekDescription = trim.match(/^([\d-]+) ~ ([\d-]+) MaaS 平台每日动态归档：(\d+) 个实质变化$/);
  if (weekDescription) return `MaaS daily update archive for ${weekDescription[1]}–${weekDescription[2]}: ${weekDescription[3]} substantive changes`;
  const changeCount = trim.match(/^(\d+) 项变化$/);
  if (changeCount) return `${changeCount[1]} changes`;
  const ledgerCount = trim.match(/^价格台账变化 (\d+) 条$/);
  if (ledgerCount) return `Pricing ledger changes: ${ledgerCount[1]}`;
  const recordCount = trim.match(/^来源变化记录（(\d+) 条）$/);
  if (recordCount) return `Source change records (${recordCount[1]})`;
  const noHighlights = trim.match(/^当日无要点（(\d+) 个信源有变化）$/);
  if (noHighlights) return `No highlights today (${noHighlights[1]} sources changed)`;
  const shortDate = trim.match(/^(\d{1,2})月(\d{1,2})日$/);
  if (shortDate) return text.replace(trim, `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][Number(shortDate[1])-1]} ${Number(shortDate[2])}`);
  const weekday = { '星期一':'Mon','星期二':'Tue','星期三':'Wed','星期四':'Thu','星期五':'Fri','星期六':'Sat','星期日':'Sun','周一':'Mon','周二':'Tue','周三':'Wed','周四':'Thu','周五':'Fri','周六':'Sat','周日':'Sun' } as Record<string,string>;
  if (weekday[trim]) return text.replace(trim, weekday[trim]);
  const addedLines = trim.match(/^新增 (\d+) 行$/);
  if (addedLines) return `${addedLines[1]} lines added`;
  const removedLines = trim.match(/^删除 (\d+) 行$/);
  if (removedLines) return `${removedLines[1]} lines removed`;
  const paired = trim.match(/^变更 (\d+) 处（旧 → 新）$/);
  if (paired) return `${paired[1]} changes (before → after)`;
  const sources = trim.match(/^(\d+) 项来源$/);
  if (sources) return `${sources[1]} sources`;
  const archive = trim.match(/^每日动态按周聚合归档，以及 (\d+) 期深度周报。$/);
  if (archive) return `Daily updates grouped by week, plus ${archive[1]} in-depth reports.`;
  const reports = trim.match(/^共 (\d+) 期完整周报，按日期倒序。$/);
  if (reports) return `${reports[1]} complete reports, newest first.`;
  const stats = trim.match(/^(\d+) 项变化 · (\d+) 发布 · (\d+) 调价$/);
  if (stats) return `${stats[1]} changes · ${stats[2]} releases · ${stats[3]} price changes`;
  const price = trim.match(/^每((?:\d|百万).+)$/);
  if (price) return `per ${englishUi(price[1])}`;
  const highlight = trim.match(/^第 (\d+) 条：(.*)$/);
  if (highlight) return `Highlight ${highlight[1]}: ${englishUi(highlight[2])}`;
  const pending = trim.match(/^本周串讲将在周末数据收齐后生成。当前已积累 (\d+) 条要点。$/);
  if (pending) return `The weekly recap will be generated when the week is complete. ${pending[1]} highlights collected so far.`;
  const deepReports = trim.match(/^共 (\d+) 期完整周报，深度分析与趋势洞察。$/);
  if (deepReports) return `${deepReports[1]} in-depth reports with analysis and trends.`;
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
    if (token.startsWith('<')) return token.replace(/\b(href|title|placeholder|aria-label|aria-roledescription|alt)="([^"]*)"/g, (_m, key, value) => `${key}="${encode(key === 'href' ? englishHref(decode(value)) : englishUi(decode(value)))}"`);
    const next = englishUi(decode(token));
    return next === decode(token) ? token : encode(next);
  });
}
