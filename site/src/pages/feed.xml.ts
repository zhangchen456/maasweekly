/**
 * GET /feed.xml：最近有效变化 RSS（Task 05 §6.1）。
 * 静态构建产出 dist/feed.xml；Content-Type 等响应头由生产服务器决定
 * （本地静态文件可解析不等于线上缓存生效——见 rss-v1.md §6.4）。
 */
import type { APIRoute } from 'astro';
import { PUBLIC_ACCESS, validatePublicAccessConfig } from '../config/public-access';
import { loadVerifiedRelease } from '../lib/release';
import { buildRss20, changesToFeedItems } from '../lib/feed-build';

export const GET: APIRoute = () => {
  const violations = validatePublicAccessConfig(PUBLIC_ACCESS);
  if (violations.length > 0) {
    throw new Error(`[feed] 公开配置校验失败（构建中止）: ${violations.join('；')}`);
  }
  const release = loadVerifiedRelease(undefined, { select: ['changes'] });
  const items = changesToFeedItems(
    release.changes!, PUBLIC_ACCESS.canonicalBaseUrl);
  const xml = buildRss20(
    {
      title: 'MaaS Daily — 最近变化',
      link: PUBLIC_ACCESS.canonicalBaseUrl,
      description: `MaaS 平台变化观察快照，数据截至 ${release.dataThrough}`
        + `（${release.datasetVersion.slice(0, 12)}…）。本 feed 为静态投影，`
        + `详情页与 API 是修订与撤回的权威状态。`,
    },
    items,
  );
  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
};
