import { uiEnglish } from './ui-en';
import supplemental from '../data/ui-translations-en.json' with { type: 'json' };
import { decodeHTML } from 'entities';
import { localizedHref } from './locale-routes';
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
export function createUiTranslator(texts: Record<string,string>) {
const catalog: Record<string, string> = { ...uiEnglish, ...texts };
const segments = Object.keys(catalog).filter(k => k.length >= 2).sort((a,b) => b.length-a.length);
const pattern = new RegExp(segments.map(escape).join('|'), 'g');
return function englishUi(text: string): string {
  if (!/[\u3400-\u9fff]/.test(text)) return text;
  const trim = text.trim();
  const exact = catalog[trim];
  if (exact) return text.replace(trim, exact);
  const copyLabel = trim.match(/^(.*)（可全选复制）$/);
  if (copyLabel) return `${englishUi(copyLabel[1])} (select all to copy)`;
  // Handle variable counters before individual words can break their grammar.
  const counter = trim.match(/^(\d+(?: \/ \d+)?)\s*(项信号|条记录|个模型|条变化)$/);
  if (counter) return text.replace(trim, `${counter[1]} ${{'项信号':'signals','条记录':'records','个模型':'models','条变化':'changes'}[counter[2]]}`);
  const recentCount = trim.match(/^(\d+)\s*[项条]变化\s*·\s*最近\s+([\d.]+)$/);
  if (recentCount) return `${recentCount[1]} changes · latest ${recentCount[2]}`;
  const truncatedCount = trim.match(/^…共\s*(\d+)\s*条，仅列前\s*(\d+)。$/);
  if (truncatedCount) return `… ${truncatedCount[1]} records; showing the first ${truncatedCount[2]}.`;
  const evidenceCount = trim.match(/^引用此证据的价格事实（(\d+) 条）$/);
  if (evidenceCount) return `Pricing facts citing this evidence (${evidenceCount[1]})`;
  const revisionCount = trim.match(/^修订历史（(\d+) 版）$/);
  if (revisionCount) return `Revision history (${revisionCount[1]} versions)`;
  const datedWeekday = trim.match(/^((?:\d{4}-\d{2}-\d{2})|(?:\d{2}\.\d{2}))\s+周([日一二三四五六])$/);
  if (datedWeekday) return `${datedWeekday[1]} ${['Sun','Mon','Tue','Wed','Thu','Fri','Sat']['日一二三四五六'.indexOf(datedWeekday[2])]}`;
  const fullDate = trim.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日$/);
  if (fullDate) return `${fullDate[1]}-${fullDate[2].padStart(2,'0')}-${fullDate[3].padStart(2,'0')}`;
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
  return text.replace(pattern, key => catalog[key])
    .replace(/\s至\s/g, ' to ')
    .replace(/(\d[\d,.]*)\s*元(?=\s|$|[）)])/g, '$1 CNY')
    .replace(/^(\s*)每\s+/, '$1per ')
    .replace(/(\d+)\s*个模型/g, '$1 models')
    .replace(/(\d+)\s*项信号/g, '$1 signals')
    .replace(/(\d+)\s*条变化/g, '$1 changes');
};
}
export const englishUi = createUiTranslator(supplemental.texts);
export function englishHref(href: string): string {
  return localizedHref(href,'en');
}
const decode = decodeHTML;
const encode = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export function englishHtml(html: string, translateText: (text:string)=>string = englishUi): string {
  // Do not translate executable code, structured data or quoted original evidence.
  const stack: { tag: string; protected: boolean }[] = [];
  const translateTag = (tag: string) => tag.replace(/\b(href|title|placeholder|aria-label|aria-roledescription|alt)="([^"]*)"/g, (_m, key, value) => `${key}="${encode(key === 'href' ? englishHref(decode(value)) : translateText(decode(value)))}"`);
  return html.replace(/<(script|style|pre|code|blockquote)\b[^>]*>[\s\S]*?<\/\1\s*>|<!--[\s\S]*?-->|<[^>]+>|[^<]+/gi, token => {
    if (/^<(script|style)\b/i.test(token)) return token;
    if (/^<(pre|code|blockquote)\b/i.test(token)) return stack.at(-1)?.protected || /^<[^>]*\bdata-original-language(?:\s|=|>)/i.test(token) ? token : token.replace(/^<[^>]+>/, translateTag);
    if (token.startsWith('<')) {
      const end = token.match(/^<\/([\w-]+)/);
      if (end) { if (stack.at(-1)?.tag === end[1].toLowerCase()) stack.pop(); return token; }
      const start = token.match(/^<([\w-]+)/);
      if (!start) return token;
      const protectedNode = !!stack.at(-1)?.protected || /\bdata-original-language(?:\s|=|>)/i.test(token);
      if (!/^(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)$/i.test(start[1]) && !/\/\s*>$/.test(token)) stack.push({tag:start[1].toLowerCase(),protected:protectedNode});
      if (protectedNode) return token;
      return translateTag(token);
    }
    if (stack.at(-1)?.protected) return token;
    const next = translateText(decode(token));
    return next === decode(token) ? token : encode(next);
  });
}
