import { readPageProjection, readPageJson } from './page-data';
import { modelRelease } from './model-pages';
import { homeModelGroups } from './home-models';
import type { PriceRecord } from './release';
export interface HighlightItem {text:string;type:string}
export interface PlatformHighlight {platform:string;logo_summary:string;items:HighlightItem[]}
export interface SourceSignal {platform:string;source_type:string;url:string;kind:string;added_count:number;removed_count:number;added_lines:string[];removed_lines:string[];pairs:{before:string;after:string}[];signal_preview?:string;permalink?:string;llm_summary?:string}
interface PriceChange {provider:string;model:string;component:string;previous?:string;current:string;currency:string;id?:string;evidence_url?:string}
interface DailyProjection {updated_at?:string;days:{date:string;changed:SourceSignal[];highlights?:PlatformHighlight[];price_changes?:PriceChange[]}[]}
interface WeekProjection {week:string;start:string;end:string;highlights:{platform:string;text:string;type:string}[];totals:{substantive:number;releases:number;pricings:number;sunsets:number};story?:{sections?:{title:string;body:string}[];story?:string;theme?:string}}
// 模型 ID / 关键实体高亮（返回段数组，模板内渲染为 code.ent）
export function highlightEntities(line: string) {
  const re = /([A-Za-z][\w.\-]*\/[\w.\-]+|(?<![A-Za-z])[a-z][a-z0-9]*(?:-[a-z0-9.]+){1,8}(?![A-Za-z])|[A-Z][a-zA-Z]*\s?\d+(?:\.\d+)*(?:\s?(?:Flash|Pro|Max|Astra|Terra|Luna))?)/g;
  const out: { text: string; hl?: boolean }[] = [];
  let last = 0;
  for (const m of line.matchAll(re)) {
    const idx = m.index ?? 0;
    if (m[0].length < 4 || /^\d/.test(m[0])) { continue; }
    if (idx > last) out.push({ text: line.slice(last, idx) });
    out.push({ text: m[0], hl: true });
    last = idx + m[0].length;
  }
  if (last < line.length) out.push({ text: line.slice(last) });
  return out.length ? out : [{ text: line }];
}

export const fmtWeekRange = (w: WeekProjection) => {
  const f = (d: string) => { const [, m, dd] = d.split('-'); return `${+m}.${+dd}`; };
  return `${f(w.start)} — ${f(w.end)}`;
};


export function homePage() {

const data = readPageProjection<DailyProjection>('daily_changes.json');
const today = data.days[0];
const weeks = readPageProjection<WeekProjection[]>('weekly-digest.json');
const currentWeek = weeks[0];
const pastWeeks = weeks.slice(1);

// ===== 今日数据拆分 =====
const substantive = today?.changed?.filter((c) => c.kind === 'substantive') || [];
const highlights = today?.highlights || []; // v3: [{platform, logo_summary, items:[{text,type}]}]

// 要点按平台分组（已经是 v3 结构）
// 有要点或实质变化的平台集合（信号明细按平台分组展示）
const platformsInSignals: Record<string, SourceSignal[]> = {};
for (const c of substantive) {
  (platformsInSignals[c.platform] ||= []).push(c);
}
// 平台排序：有 highlights 的平台在前，其余按实质变化数
const platformOrder = [...new Set([...highlights.map((h) => h.platform), ...Object.keys(platformsInSignals)])];

const TYPE_LABEL: Record<string, string> = {
  model_list: '模型列表', pricing: '定价', changelog: '更新日志', blog: '博客',
  api_docs: 'API 文档', github: 'GitHub', model_marketplace: '模型广场', industry: '行业数据',
};
const HL_TYPE: Record<string, { label: string; cls: string }> = {
  release: { label: '发布', cls: 't-release' },
  pricing: { label: '调价', cls: 't-pricing' },
  sunset: { label: '下线', cls: 't-sunset' },
  other: { label: '动态', cls: 't-other' },
};
const typeLabel = (t: string) => TYPE_LABEL[t] || t;

// 日期格式化：2026-09-04 -> 2026.09.04 / 9.4
const dateLong = today?.date?.replace(/-/g, '.') || '';
const dateShort = today?.date ? (() => { const [, m, d] = today.date.split('-'); return `${+m}.${+d}`; })() : '';
const weekday = today?.date ? '周' + '日一二三四五六'[new Date(today.date + 'T12:00:00+08:00').getUTCDay()] : '';

// 周故事：v4 优先 sections（[{title, body}]），回退旧纯文本 story 段落
const storySections: { title: string; body: string }[] = currentWeek?.story?.sections || [];
const storyParas = (currentWeek?.story?.story || '').split('\n').filter((p: string) => p.trim());
// 当日价格变化事件（fetch-prices.py 产出，八家官方定价页结构化 diff）
const priceChanges = today?.price_changes || [];
// 周要点按平台统计（v3 展平后已存 weekly-digest 的 highlights）
const weekHighlightCount = currentWeek?.highlights?.length || 0;
return { data, today, currentWeek, pastWeeks, substantive, highlights, platformsInSignals, platformOrder, HL_TYPE, typeLabel, dateLong, dateShort, weekday, storySections, storyParas, priceChanges, weekHighlightCount };
}

export function homeOverview(highlights:PlatformHighlight[], updatedAt?:string) {
const ledger = readPageJson<{fx_snapshot:{rates:{CNY:number};as_of:string}}>('derived/pricing/ledger.json')!;
const fxRate = Number(ledger.fx_snapshot.rates.CNY);
const displayAmount = (p: PriceRecord | undefined) => p && ['USD','CNY'].includes(p.currency) ? new Intl.NumberFormat('zh-CN',{maximumSignificantDigits:6}).format(Number(p.amount) * (p.currency === 'USD' ? fxRate : 1)) : p?.amount ?? '—';

const updateLabel = updatedAt;
const labels: Record<string,string> = {sunset:'服务下线',pricing:'价格变化',release:'新模型发布',other:'平台更新'};
const all = highlights.flatMap((h) => h.items.map((item) => ({...item,platform:h.platform,headline:h.logo_summary})));
const picks: (HighlightItem & {platform:string;headline:string})[] = [];
for (const type of ['sunset','pricing','release']) {
  const item=all.find((i)=>i.type===type && !picks.some(p=>p.platform===i.platform));
  if(item) picks.push(item);
}
for(const item of all) if(picks.length<3 && !picks.some(p=>p.platform===item.platform)) picks.push(item);
const modelGroups=homeModelGroups();
const quote=(p: PriceRecord | undefined)=>p?`${p.amount} ${p.currency}`:'未单列';
const release=modelRelease();
return {ledger,fxRate,displayAmount,updateLabel,labels,picks,modelGroups,quote,release};
}
