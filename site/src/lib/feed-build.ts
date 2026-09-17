/**
 * feed-build.ts：RSS 2.0 文档组装（纯函数，Task 05 M2）。
 *
 * 确定性（T08）：无 Date.now()/new Date()/Math.random()/process.cwd()
 * 进内容；固定缩进与元素顺序——同输入逐字节稳定。
 * 合同（docs/contracts/rss-v1.md）：GUID=稳定 record ID（isPermaLink=false）；
 * date 精度省略 pubDate（不合成午夜）；withdrawn 退出默认 feed；
 * channel 不含 lastBuildDate（数据时间只有日期精度）。
 */
import { sanitizeXmlText, escapeXml } from './feed-xml.ts';
import type { ChangeRecord, WeeklyRecord } from './release.ts';

export const TITLE_MAX_CP = 200;
export const DESC_MAX_CP = 600;
export const CHANGES_FEED_LIMIT = 100;
export const WEEKLY_FEED_LIMIT = 30;

export interface FeedItemInput {
  /** 稳定 ID，不含 datasetVersion/标题/排序/构建日期 */
  guid: string;
  title: string;
  /** canonical 绝对 URL */
  link: string;
  /** 纯文本（组装时转义） */
  description: string;
  /** null = 省略 <pubDate>（date 精度不合成午夜） */
  pubDateIso: string | null;
}

export interface RssChannel {
  title: string;
  link: string;
  description: string;
}

/** RFC 822/2822 日期，固定 UTC——只解析传入 ISO，绝不使用本地时区。 */
export function rfc2822Utc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(+d)) {
    throw new Error(`[feed] 非法时间: 只输出数据内的 ISO 时间`);
  }
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const p2 = (n: number) => String(n).padStart(2, '0');
  return `${days[d.getUTCDay()]}, ${p2(d.getUTCDate())} ${months[d.getUTCMonth()]} `
    + `${d.getUTCFullYear()} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:`
    + `${p2(d.getUTCSeconds())} GMT`;
}

/** 组装 RSS 2.0 文档（固定两空格缩进、固定元素顺序）。 */
export function buildRss20(channel: RssChannel, items: readonly FeedItemInput[]): string {
  const esc = escapeXml;
  const lines: string[] = [];
  lines.push('<?xml version="1.0" encoding="UTF-8"?>');
  lines.push('<rss version="2.0">');
  lines.push('  <channel>');
  lines.push(`    <title>${esc(channel.title)}</title>`);
  lines.push(`    <link>${esc(channel.link)}</link>`);
  lines.push(`    <description>${esc(channel.description)}</description>`);
  for (const it of items) {
    lines.push('    <item>');
    lines.push(`      <title>${esc(sanitizeXmlText(it.title, TITLE_MAX_CP))}</title>`);
    lines.push(`      <link>${esc(it.link)}</link>`);
    lines.push(`      <description>${esc(sanitizeXmlText(it.description, DESC_MAX_CP))}</description>`);
    lines.push(`      <guid isPermaLink="false">${esc(it.guid)}</guid>`);
    if (it.pubDateIso !== null) {
      lines.push(`      <pubDate>${rfc2822Utc(it.pubDateIso)}</pubDate>`);
    }
    lines.push('    </item>');
  }
  lines.push('  </channel>');
  lines.push('</rss>');
  return `${lines.join('\n')}\n`;
}

const CHANGE_TYPE_LABEL: Record<string, string> = {
  amount_changed: '金额变化',
  terms_changed: '条件变化',
  newly_observed: '首次观察',
  source_updated: '来源更新',
};

/**
 * 变化记录 → feed items（纯函数，排序内置）。
 * 规则：withdrawn 排除；observationDate 倒序 + id 升序；前 limit 条；
 * date 精度省略 pubDate；description 不编造摘要。
 */
export function changesToFeedItems(
  changes: readonly ChangeRecord[],
  canonicalBase: string,
  limit = CHANGES_FEED_LIMIT,
): FeedItemInput[] {
  const active = changes.filter((c) => c.status === 'active');
  const sorted = [...active].sort((a, b) =>
    b.observationDate.localeCompare(a.observationDate)
    || a.id.localeCompare(b.id));
  return sorted.slice(0, limit).map((c) => {
    const desc = describeChange(c);
    return {
      guid: c.id,
      title: c.title,
      link: `${canonicalBase}${c.links.permalink}`,
      description: desc,
      pubDateIso: c.timePrecision === 'datetime' && c.observedAt
        ? c.observedAt : null,
    };
  });
}

function describeChange(c: ChangeRecord): string {
  const parts: string[] = [];
  const label = CHANGE_TYPE_LABEL[c.changeType] ?? c.changeType;
  if (c.recordType === 'price_change' && c.price) {
    const p = c.price;
    const amount = p.afterAmount !== null
      ? (p.beforeAmount !== null
        ? `${p.beforeAmount} → ${p.afterAmount}`
        : `${p.afterAmount}（首次观察）`)
      : '见详情页';
    parts.push(`价格事实（${label}）：${p.model} ${p.component}，${amount} ${p.currency} / ${p.unitQuantity} ${p.unitName}。完整适用条件见详情页。`);
  } else if (c.summary) {
    parts.push(c.summary);
    if (c.summaryOrigin === 'llm') {
      parts.push('（摘要由 LLM 生成，可能不准确，请以证据与官方页面核验。）');
    }
  } else {
    parts.push(`来源页面观察更新（${c.providerId ?? '-'}），差异与证据见详情页。`);
  }
  const precision = c.timePrecision === 'datetime'
    ? `精确时间 ${c.observedAt}` : '日期精度';
  parts.push(`观察日期 ${c.observationDate}（${precision}）· 状态 ${c.status} · 修订 r${c.revision}`);
  return parts.join(' ');
}

/**
 * 周报 → feed items（纯函数）。weekly.json 是升序存放——必须显式倒序，
 * 取最近 limit 期。周报只有日期精度 → 全部省略 pubDate。
 */
export function weeklyToFeedItems(
  weekly: readonly WeeklyRecord[],
  canonicalBase: string,
  limit = WEEKLY_FEED_LIMIT,
): FeedItemInput[] {
  const sorted = [...weekly].sort((a, b) => b.date.localeCompare(a.date));
  return sorted.slice(0, limit).map((w) => {
    const headlines = (w.headline as { title?: string | null }[])
      .slice(0, 3)
      .map((h) => h.title)
      .filter((t): t is string => Boolean(t));
    const desc = [
      `第 ${w.date} 期正式周报${w.period ? ` · 覆盖 ${w.period}` : ''}。`,
      headlines.length > 0 ? `头条：${headlines.join('；')}` : '',
    ].filter(Boolean).join(' ');
    return {
      guid: w.id,
      title: w.title,
      link: `${canonicalBase}${w.url}`,
      description: desc,
      pubDateIso: null, // 周报只有日期精度，不合成午夜
    };
  });
}
