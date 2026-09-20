/**
 * changelog.ts：人工维护的公开接口变更记录（Task 05 §8）。
 *
 * 规则：只写真实状态；不倒填发布日期（date=null 表示尚未发布，
 * 页面渲染「随首次生产部署确定」）；只有确定的停止日期与迁移路径
 * 才能写 Deprecation/Sunset——不为「完整」编虚构公告。
 */

export interface ChangelogEntry {
  /** null = 尚未正式发布（本地/待部署阶段） */
  date: string | null;
  title: string;
  areas: Array<{
    area: 'rest' | 'mcp' | 'skill' | 'rss' | 'web';
    status: 'available' | 'pending' | 'planned';
    note: string;
  }>;
  breaking: false;
}

export const CHANGELOG: ChangelogEntry[] = [
  {
    date: '2026-09-20',
    title: 'Agent 接口公开可用（GA）：REST / MCP / Skill / RSS 上线',
    areas: [
      {
        area: 'web',
        status: 'available',
        note: '站点与全部入口页（/agent/ /method/ /changelog/）随 release rl_31c918e04d 发布',
      },
      {
        area: 'rest',
        status: 'available',
        note: 'GET /api/v1/*（changes/prices/items/{id}/evidence/{id}/weekly/status）生产可用；四入口 online verify 通过，datasetVersion 与站点一致',
      },
      {
        area: 'mcp',
        status: 'available',
        note: 'POST /api/mcp（Streamable HTTP，五工具 maas_get_*）生产可用；Claude Code 新会话真实调用验收通过（含无结果语义）。Codex 兼容验证仍阻断（无真实 OpenAI 认证环境，未以 curl 冒充）',
      },
      {
        area: 'skill',
        status: 'available',
        note: 'Skill 包 1.0.0（/maas-skill/install.sh）生产可用；公网真实安装验收通过（manifest 校验、引用地址一致）',
      },
      {
        area: 'rss',
        status: 'available',
        note: '/feed.xml（≤100 条）与 /feed/weekly.xml（≤30 期）生产可用；真实订阅器验收通过（pubDate 精度语义、ETag/304）',
      },
    ],
    breaking: false,
  },
  {
    date: null,
    title: '公开接口初始状态（v1）',
    areas: [
      {
        area: 'web',
        status: 'available',
        note: '站点、条目/证据/价格详情页与 /agent/ /method/ /changelog/ 入口',
      },
      {
        area: 'rss',
        status: 'pending',
        note: '/feed.xml（≤100 条有效变化）与 /feed/weekly.xml（≤30 期正式周报）本地构建与解析验证通过；生产 URL 与缓存响应头随 Task 06 部署',
      },
      {
        area: 'skill',
        status: 'pending',
        note: 'Skill 包 1.0.0 可下载安装；数据查询依赖 REST 生产路由，随 Task 06 生效',
      },
      {
        area: 'mcp',
        status: 'pending',
        note: 'POST /api/mcp 本地实现完成，Claude Code 2.1.259 验证通过；生产路由随 Task 06 生效。Codex 兼容验证待 OpenAI 认证环境',
      },
      {
        area: 'rest',
        status: 'pending',
        note: 'REST API v1（OpenAPI 见 /openapi-v1.json）本地实现与测试完成；生产 /api/v1/* 随 Task 06 生效',
      },
    ],
    breaking: false,
  },
];
