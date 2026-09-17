/**
 * GET /feed/weekly.xml：最近正式周报 RSS（Task 05 §6.1）。
 * 只含 site/src/content/weekly 正式周报（滚动摘要不进此 feed）。
 */
import type { APIRoute } from 'astro';
import { PUBLIC_ACCESS, validatePublicAccessConfig } from '../../config/public-access';
import { loadVerifiedRelease } from '../../lib/release';
import { buildRss20, weeklyToFeedItems } from '../../lib/feed-build';

export const GET: APIRoute = () => {
  const violations = validatePublicAccessConfig(PUBLIC_ACCESS);
  if (violations.length > 0) {
    throw new Error(`[feed] 公开配置校验失败（构建中止）: ${violations.join('；')}`);
  }
  const release = loadVerifiedRelease(undefined, { select: ['weekly'] });
  const items = weeklyToFeedItems(
    release.weekly!, PUBLIC_ACCESS.canonicalBaseUrl);
  const xml = buildRss20(
    {
      title: 'MaaS Daily — 周度报告',
      link: PUBLIC_ACCESS.canonicalBaseUrl,
      description: `MaaS 平台周度追踪正式周报，数据截至 ${release.dataThrough}`
        + `（${release.datasetVersion.slice(0, 12)}…）。`
        + `详情页与 API 是最新状态的权威来源。`,
    },
    items,
  );
  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
};
