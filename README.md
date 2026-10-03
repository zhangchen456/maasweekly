# MaaS Weekly

全球 MaaS 平台追踪站：周度报告 + 每日信源变化（热点每天更新），数据由自动抓取管线驱动。

架构改造：[2026-10 执行任务清单](docs/architecture/refactoring-2026-10/README.md)（8 项本地改造及逐项回归已完成；[交付与验收入口](docs/architecture/refactoring-2026-10/delivery-index.md)。生产未发布，远端存储暂缓）。

线上地址：**https://daily.maas.click** （旧域名 `week.maas.click` / `mw.zhangchen456.xyz` 已 301 跳转到新域名）

部署：aliyun-099（47.237.135.97），Nginx 静态站 + Node REST/MCP。当前发布使用不可变 release、manifest 校验与蓝绿槽位，根目录 `/srv/maasweekly/`；旧 `/var/www/maasweekly` 为 legacy 路径。客户端协议和恢复入口见 `ops/README.md`。

## 仓库结构

```
maasweekly/
├── site/                    # Astro v7 静态站点（随统一 release 发布）
│   ├── src/content/weekly/      # 周报 Markdown（带 frontmatter）
│   ├── src/content/weekly-structured/  # 周报结构化 JSON（extract-structured.py 生成）
│   ├── src/content/platforms/   # 平台信源 JSON（split-sources.py 生成）
│   ├── src/data/               # 榜单/定价/每日变化等数据源
│   └── src/pages/changes.astro # 每日动态页（消费 data/diff）
├── pipeline/                # 数据管线
│   ├── scripts/fetch_sources.py        # 每日抓取 16 平台 + 行业信源，快照 + diff
│   ├── scripts/sync-diff-to-site.py    # 聚合 diff JSON 到站点数据源
│   └── config/maas_official_sources.json  # 信源配置（67 个 URL）
├── data/                    # 抓取产物与历史数据（git 跟踪）
│   ├── snapshots/YYYY-MM-DD/    # 每日原始快照
│   ├── diff/YYYY-MM-DD.md|json  # 每日变化报告（人读 + 机读）
│   ├── records/obs_*.json       # 来源变化条目持久归档（稳定 ID，/item/ 详情页数据源）
│   └── record-revisions/        # 条目历史版本（每修订一版，不可覆盖）
│   ├── price-{facts,evidence,records,runs}/  # 价格事实/证据/事件归档（Task 02，内容寻址）
│   ├── public/v1/               # 公开数据 release（Task 03，export-public-data.py 产出）
│   ├── weekly/                  # 周报源文件
│   ├── daily/                   # 早期每日追踪报告（7 月前）
│   └── weekly-archive-early/    # 更早期手写周报存档
├── services/agent-api/       # REST API v1 + MCP /api/mcp（Task 03/04，Node 22 + TS；本地 127.0.0.1:8787，生产蓝绿 8788/8789）
├── agent-skill/maas-daily/   # Agent Skill 源（Task 04：SKILL.md 路由 + references）
└── .github/workflows/       # 自动化
    ├── daily-update.yml     # 每天凌晨 05:00 抓取 + 构建 + 部署
    └── weekly-update.yml    # 每周一 09:00 抓取汇总 + 周报导入 + 部署
```

### 公开 API（Task 03，已发布）

`pipeline/scripts/export-public-data.py` 把 Task 01/02 归档与正式周报投影为
版本化公开数据（`data/public/v1/`），`services/agent-api`（Node 22 + TS）
提供匿名只读 REST API：`/api/v1/changes | prices | items/{id} |
evidence/{id} | weekly | weekly/{id} | models | status`，支持筛选、cursor 固定版本
翻页、ETag/304、Problem JSON。合同：`docs/contracts/public-api-v1.md`；
OpenAPI：`site/public/openapi-v1.json`。

### Agent 接入 / RSS / 方法说明（Task 05，已发布）

- `/agent/`：Skill/MCP/RSS/REST 四种接入方式、可复制配置、验证问题与真实状态
- `/feed.xml`（最近 100 条变化）与 `/feed/weekly.xml`（最近 30 期周报）RSS 2.0
- `/method/`：数据方法说明；`/changelog/`：接口变更记录；`/llms.txt`：机器入口
- 唯一配置来源 `site/src/config/public-access.ts`（域名/端点/状态/客户端验证）
- 合同：`docs/contracts/rss-v1.md`

### MCP 与 Agent Skill（Task 04，已发布）

同一服务提供 MCP 端点 `POST /api/mcp`（官方 SDK 1.30，stateless，五个
`maas_get_*` 只读工具，与 REST 同数据同版本）。Agent Skill 包发布在
`/maas-skill/`（manifest + install.sh；源在 `agent-skill/maas-daily/`，
构建 `python3 site/scripts/build-skill-package.py`）。合同：
`docs/contracts/mcp-v1.md`。本地跑：

```bash
python3 pipeline/scripts/export-public-data.py
cd services/agent-api && npm ci && npm run build && npm start   # 127.0.0.1:8787
```

## 自动更新机制

### 每日（热点信息每天更新）

`daily-update.yml` 每天北京时间凌晨 05:00 执行：

1. `fetch_sources.py` 抓取全部信源（模型列表 / 定价 / 更新日志 / 博客）
2. 与最近一次快照逐行 diff，产出 `data/diff/YYYY-MM-DD.md|json`
3. `sync-diff-to-site.py` 聚合最近 14 天 diff 到 `site/src/data/daily_changes.json`
4. 摘要、榜单及公开投影生成；数据先提交到仓库
5. 从精确提交执行统一测试、构建与 release 发布（蓝绿激活 + 四入口验证）

站点 `/changes` 页面按天展示每个平台的变化条目，点击展开新增/删除行。

### 每周（周报）

`weekly-update.yml` 每周一 09:00 抓取汇总素材。新周报写好后放入 `data/weekly/YYYY-MM-DD.md`，手动触发工作流选 `import` 或 `full` 模式，即导入站点（`import-weekly.py` + `extract-structured.py`）并部署。

## 本地开发

```bash
cd site
npm install
npm run dev      # http://localhost:4321/
npm run build    # 构建到 dist/

# 手动跑一次抓取（调试）
python3 pipeline/scripts/fetch_sources.py --platform 火山方舟   # 单平台
python3 pipeline/scripts/fetch_sources.py --max-sources 5      # 限量
python3 pipeline/scripts/sync-diff-to-site.py                  # 同步到站点（含来源条目归档）

# 来源变化条目归档（独立入口，可在临时目录测试）
python3 pipeline/scripts/archive-source-changes.py             # 回填全部合法日期（幂等）
python3 pipeline/scripts/archive-source-changes.py --check     # 只校验不写入
```

## 历史 GitHub Pages 初始化方式

以下为早期部署说明，不是当前生产发布入口；当前发布使用 `ops/deploy-release.sh` 与 `ops/verify-release.sh`，遵守 `ops/README.md` 的发布协议。

1. 新建 GitHub 仓库，推送本目录
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**
3. 改 `site/astro.config.mjs` 的 `site` 字段为实际域名（默认 `https://<user>.github.io/<repo>/` 需加 `base: '/<repo>/'`，若用自定义域名则不用）
4. Actions 里手动触发 `daily-update.yml` 验证全链路

## 数据说明

- 信源配置：`pipeline/config/maas_official_sources.json`
- 来源注册表：`pipeline/config/source_registry.json`（稳定 source_id ↔ 平台/类型/URL 别名）。**新增信源步骤**：先在 maas_official_sources.json 加信源 → 抓取产生 diff 后，如果 `archive-source-changes.py` 报"来源未映射"，在 source_registry.json 的 sources 数组补一条 `{source_id, display_name, source_type, url_aliases, primary_url}`——source_id 一旦分配不可更改，URL 变化只追加 url_aliases（国内 9 + 海外 7 平台，6 维度信源 + 行业数据源）
- diff 算法：按行集合对比，过滤 10 字符以下短行，噪声较多的页面（JS 渲染的 SPA）可能误报，后续可换 HTML 结构化 diff
- 历史周报：53 期（2025-10 ~ 2026-09），完整存于 `data/weekly/` 与 `data/weekly-archive-early/`

## 账号与模型关注 v1（本地实现，待生产启用）

`/account/` 提供邮箱验证码登录、模型关注、近期变化与主动开启的每日邮件摘要；`/account/unsubscribe/` 支持免登录确认退订。用户数据保存在独立 SQLite，不进入公开 API 数据投影。邮件服务和持久库未配置时，账号页面明确展示未启用状态。

计划、开发配置、生产启用候选及验收：[账号与模型关注 v1](docs/product/account-watch-v1/README.md)。生产发信与定时任务尚未启用。
