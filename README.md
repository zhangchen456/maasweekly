# MaaS Weekly

全球 MaaS 平台追踪站：周度报告 + 每日信源变化（热点每天更新），数据由自动抓取管线驱动。

当前数据与代码已分开部署：网页和 API 从现有服务器 PostgreSQL 与独立文件目录读取数据。日更/周更工作流独立发布数据，功能改动才构建代码包；不使用对象存储。实施与验证状态见 [运行记录](docs/architecture/data-code-runtime-2026-10-29.md)，操作入口见 [独立发布手册](docs/architecture/data-runtime-operations.md)。

线上地址：**https://daily.maas.click** （旧域名 `week.maas.click` / `mw.zhangchen456.xyz` 已 301 跳转到新域名）

部署：aliyun-099（47.237.135.97），Nginx + Node SSR/REST/MCP。当前发布使用不可变 release、manifest 校验与蓝绿槽位，根目录 `/srv/maasweekly/`；旧 `/var/www/maasweekly` 为 legacy 路径。客户端协议和恢复入口见 `ops/README.md`。

## 仓库结构

```
maasweekly/
├── site/                    # Astro SSR 页面、静态资产与手工配置
├── services/agent-api/       # Node 22 REST/MCP、网页运行时、账号与后台功能
├── pipeline/                # 采集、校验、数据库迁移与数据发布
├── data/model-registry/     # 手工模型身份定义（代码配置）
├── data/weekly/             # 手工周报稿件
├── agent-skill/maas-daily/   # Agent Skill 源
├── ops/                     # 独立 writer、固定 SSH 入口、蓝绿切换与恢复
└── .github/workflows/       # 日更/周更只发数据；release-deploy 只发代码
```

运行数据目录独立于 Git 和代码包；开发机已有的数据只是本地副本。服务器结构化输入保存在 `maas_data`，原始材料在 `/srv/maasweekly/shared/data-store/blobs`，公开只读文件在 `shared/public-data/v1`。

### 公开 API（Task 03，已发布）

`pipeline/scripts/export-database-data.py` 从固定数据库输入导出
版本化公开数据（服务器共享数据目录），`services/agent-api`（Node 22 + TS）
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
cd services/agent-api && npm ci && npm run build
PUBLIC_DATA_ROOT=/absolute/path/to/public/v1 npm start   # 127.0.0.1:8787
```

## 自动更新机制

### 每日（热点信息每天更新）

`daily-update.yml` 每天北京时间凌晨 05:00 执行：

1. `fetch_sources.py` 抓取全部信源（模型列表 / 定价 / 更新日志 / 博客）
2. 与最近一次快照逐行 diff，产出 `data/diff/YYYY-MM-DD.md|json`
3. `sync-diff-to-site.py` 聚合最近 14 天 diff 到 `site/src/data/daily_changes.json`
4. 摘要、榜单及投影生成，固定输入与修订写入数据库
5. 校验候选与网页后原子发布共享数据，网站自动读取新版本；不提交 Git、不构建网站

站点 `/changes` 页面按天展示每个平台的变化条目，点击展开新增/删除行。

### 每周（周报）

`weekly-update.yml` 每周一 09:00 抓取汇总素材。新周报写好后放入 `data/weekly/YYYY-MM-DD.md`，手动触发工作流选 `import` 或 `full` 模式，即导入数据库、验证并发布内容。只提交周报稿件也会走数据导入，不构建代码。

## 构建与本地开发

生产代码构建（干净提交，输出目录必须在仓库外且尚不存在）：

```bash
bash scripts/build-runtime-release.sh --output /absolute/path/to/new-runtime
```

本地完整页面预览需要单独恢复的测试数据/数据库，见 [运行手册](docs/architecture/data-runtime-operations.md)。下面是保留的历史静态调试链路，需要本地已有完整数据；新检出不自带生产归档。

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

以下仅为历史记录。当前生产发布使用 `.github/workflows/release-deploy.yml` 和 `scripts/build-runtime-release.sh`，遵守独立发布手册。

1. 新建 GitHub 仓库，推送本目录
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**
3. 改 `site/astro.config.mjs` 的 `site` 字段为实际域名（默认 `https://<user>.github.io/<repo>/` 需加 `base: '/<repo>/'`，若用自定义域名则不用）
4. Actions 里手动触发 `daily-update.yml` 验证全链路

## 数据说明

- 信源配置：`pipeline/config/maas_official_sources.json`
- 来源注册表：`pipeline/config/source_registry.json`（稳定 source_id ↔ 平台/类型/URL 别名）。**新增信源步骤**：先在 maas_official_sources.json 加信源 → 抓取产生 diff 后，如果 `archive-source-changes.py` 报"来源未映射"，在 source_registry.json 的 sources 数组补一条 `{source_id, display_name, source_type, url_aliases, primary_url}`——source_id 一旦分配不可更改，URL 变化只追加 url_aliases（国内 9 + 海外 7 平台，6 维度信源 + 行业数据源）
- diff 算法：按行集合对比，过滤 10 字符以下短行，噪声较多的页面（JS 渲染的 SPA）可能误报，后续可换 HTML 结构化 diff
- 手工周报稿件在 `data/weekly/`；正式内容及修订进入数据库，早期手写存档保存在仓库外备份。

## 账号与模型关注 v1

`/account/` 提供邮箱验证码登录、模型关注、近期变化与主动开启的每日邮件摘要；`/account/unsubscribe/` 支持免登录确认退订。用户数据保存在独立 SQLite，不进入公开 API 数据投影。邮件服务和持久库未配置时，账号页面明确展示未启用状态。

计划、开发配置、生产启用及验收：[账号与模型关注 v1](docs/product/account-watch-v1/README.md)。2026-10-03 已启用生产邮件登录与定时任务，验收见该目录的生产上线记录。
