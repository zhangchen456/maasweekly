/**
 * public-access.ts：公开接入的唯一配置来源（Task 05 §4）。
 *
 * 站点域名、端点路径、四种接入方式状态、已验证/待验证客户端、合同版本
 * 全部集中于此——页面、feed、llms.txt 测试都从这里推导，不得在多个
 * 页面手写可能分叉的域名或版本。
 *
 * 构建门禁：validatePublicAccessConfig 拒绝 localhost、file://、本机
 * 绝对路径、空生产域名和未知状态值进入公开产物（T01）；pending 是
 * 真实产品状态，不导致构建失败。
 */

export type AccessStatus = 'available' | 'pending' | 'unavailable';

export const SITE_CANONICAL = 'https://daily.maas.click';

export interface SurfaceDef {
  status: AccessStatus;
  /** 面向用户的一句话原因；pending/unavailable 必填（含解除动作） */
  reason: string;
  /** 本地是否已完成实现+验证（与线上 status 独立的双层状态） */
  locallyVerified: boolean;
  contractVersion: string;
}

export interface VerifiedClient {
  name: string;
  version: string;
  verifiedAt: string;
  transport: string;
  surface: 'mcp' | 'skill' | 'rest';
}

export const PUBLIC_ACCESS = {
  canonicalBaseUrl: SITE_CANONICAL,
  paths: {
    agent: '/agent/',
    method: '/method/',
    changelog: '/changelog/',
    apiBase: '/api/v1',
    openapi: '/openapi-v1.json',
    mcpEndpoint: '/api/mcp',
    skillManifest: '/maas-skill/manifest.json',
    skillInstaller: '/maas-skill/install.sh',
    feedChanges: '/feed.xml',
    feedWeekly: '/feed/weekly.xml',
  },
  surfaces: {
    rss: {
      status: 'pending',
      locallyVerified: true,
      reason: 'feed 本地构建与标准解析器验证通过；生产 URL 待 Task 06 部署并完成真实阅读器验收后可用',
      contractVersion: 'rss-v1',
    },
    skill: {
      status: 'pending',
      locallyVerified: true,
      reason: 'Skill 包 1.0.0 已可下载安装；数据查询依赖 REST 生产路由，随 Task 06 部署后可用',
      contractVersion: 'skill-v1（包版本 1.0.0）',
    },
    mcp: {
      status: 'pending',
      locallyVerified: true,
      reason: '本地 Claude Code 真实验证通过；生产 /api/mcp 由 Task 06 部署',
      contractVersion: 'mcp-v1',
    },
    rest: {
      status: 'pending',
      locallyVerified: true,
      reason: '本地实现与测试完成；生产 /api/v1/* 由 Task 06 部署',
      contractVersion: 'rest-v1',
    },
  },
  verifiedClients: [
    {
      name: 'Claude Code',
      version: '2.1.259',
      verifiedAt: '2026-09-16',
      transport: 'MCP Streamable HTTP（headless 验证）',
      surface: 'mcp',
    },
  ],
  pendingClients: [
    {
      name: 'Codex',
      unblockCondition: '需具备 OpenAI 认证环境后完成真实客户端工具发现与查询（Task 04 T18 遗留，Task 06 前阻断）',
    },
  ],
} as const;

/** 构建门禁：返回违规清单（空 = 通过）。页面/feed frontmatter 调用，非空即 throw。 */
export function validatePublicAccessConfig(
  cfg: typeof PUBLIC_ACCESS,
): string[] {
  const v: string[] = [];
  const base: string = cfg.canonicalBaseUrl;
  if (!base) v.push('canonicalBaseUrl 为空');
  if (!base.startsWith('https://')) v.push(`canonicalBaseUrl 非 HTTPS: ${base}`);
  if (base.includes('://localhost') || /:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])/i.test(base)) {
    v.push(`canonicalBaseUrl 含本机地址: ${base}`);
  }
  if (/\.local($|:|\/)/i.test(base)) v.push(`canonicalBaseUrl 含 .local 域: ${base}`);
  if (base.startsWith('file://')) v.push('canonicalBaseUrl 是 file URL');
  if (/\/(Users|home)\//.test(base)) v.push('canonicalBaseUrl 含本机绝对路径');
  for (const [key, p] of Object.entries(cfg.paths)) {
    if (!p.startsWith('/') || p.includes('..') || /^[a-z]+:\/\//i.test(p)) {
      v.push(`paths.${key} 非仓库相对路径: ${p}`);
    }
  }
  const VALID_STATUS = ['available', 'pending', 'unavailable'];
  for (const [key, s] of Object.entries(cfg.surfaces)) {
    if (!VALID_STATUS.includes(s.status)) {
      v.push(`surfaces.${key}.status 未知值: ${String(s.status)}`);
    }
    if (s.status !== 'available' && !s.reason) {
      v.push(`surfaces.${key} 非 available 但缺 reason`);
    }
  }
  const verifiedNames = new Set(cfg.verifiedClients.map((c) => c.name));
  for (const c of cfg.verifiedClients) {
    if (!c.name || !c.version || !c.verifiedAt) {
      v.push(`verifiedClients 项缺字段: ${c.name}`);
    }
  }
  for (const c of cfg.pendingClients) {
    if (!c.name || !c.unblockCondition) {
      v.push(`pendingClients 项缺字段: ${c.name}`);
    }
    if (verifiedNames.has(c.name)) {
      v.push(`客户端同时出现在 verified 与 pending: ${c.name}`);
    }
  }
  return v;
}
