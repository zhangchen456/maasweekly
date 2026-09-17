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
