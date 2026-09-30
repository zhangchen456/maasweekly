# T08-0 Analytics / SEO / GEO Observability — Inventory

日期：2026-09-30。状态：**调查完成（不编码）**。

前置：Task 01–07-5 已完成稳定条目、价格证据、公开数据投影、REST API v1、MCP、
Agent Skill、RSS、生产发布与跨平台 ontology 设计。T08-0 只进行仓库调查、架构
分析与技术方案冻结，不实现任何 Analytics 功能。

本文档所有判断均建立在当前 `main` 分支代码、部署脚本、Nginx 配置、数据 Pipeline、
GitHub Actions 和现有生产架构基础上。如文档与实际代码存在冲突，以代码为准。

---

## 1. Current Frontend

### 1.1 技术栈

| 维度 | 实际值 | 证据 |
|---|---|---|
| 框架 | Astro v7.2.10 | `site/package.json:17` `"astro": "^7.2.10"` |
| 构建工具 | Astro 内置（Vite based） | `site/package.json:10` build 脚本末尾 `astro build` |
| 模板引擎 | Astro `.astro` 单文件组件 | `site/src/pages/*.astro` |
| 渲染模式 | **SSG（静态站点生成）** | `site/astro.config.mjs` 无 `output: 'server'` 或 adapter |
| 其他依赖 | `marked` ^18.0.11 | `site/package.json:18` |
| devDep | `fast-xml-parser`、`jsdom`（测试用） | `site/package.json:22-23` |
| API 后端 | Node.js 22 + TypeScript，独立服务 | `services/agent-api/src/server.ts` |

### 1.2 页面生成方式

**全部页面为 SSG**。Astro 默认模式即静态生成，无 SSR/adapter 配置。
`astro build` 产出纯静态文件到 `site/dist/`，部署到 nginx 静态 root。

动态路由页使用 `getStaticPaths()` 在构建时预生成所有路径：

| 路由文件 | getStaticPaths 数据源 | 生成页面数 |
|---|---|---|
| `site/src/pages/model/[modelId].astro` | `loadVerifiedRelease({select:['modelIdentities']})` catalog | 107 |
| `site/src/pages/item/[id].astro` | `data/records/` + `data/price-records/` 目录 | 按 ID 数量 |
| `site/src/pages/daily/[week].astro` | `site/src/data/weekly-digest.json` + `record-index.json` | 按 ISO 周数 |
| `site/src/pages/evidence/[id].astro` | `data/price-evidence/` 目录 | 按 evidence 数量 |
| `site/src/pages/weekly/[id].astro` | Astro content collection | 按周报数 |

部分页面（changes、model detail）采用"静态壳 + 客户端 fetch REST API"混合模式：
构建时只注入 catalog 与 API base URL，运行时客户端 `fetch()` 加载分页数据。

### 1.3 页面导航机制

- **顶部导航栏**（全局 Layout 内硬编码链接）：`site/src/layouts/Layout.astro:37-45`
  - 今日 `/`、榜单 `/leaderboards`、价格 `/pricing`、变化 `/changes`、信源 `/sources`、归档 `/weekly`、接入 `/agent`
- **底部 footer**：关于 `/about`、接入 `/agent`、方法 `/method`、变更 `/changelog`、RSS `/feed.xml`
- **无客户端路由库**：所有导航为原生 `<a href>` 链接，浏览器全页跳转
- changes 页面用 `history.pushState` 同步 URL 筛选状态（`?modelId=` 等），但不做客户端路由

### 1.4 JavaScript 入口

Astro 项目无单一 JS 入口；JS 以两种方式存在：

1. **Layout 内联脚本**（`is:inline`，全局）：`site/src/layouts/Layout.astro`
   - 主题初始化（line 21-29，读 localStorage 设置 data-theme）
   - 主题切换按钮 + reveal 动画 IntersectionObserver（line 66-84）
2. **页面级内联脚本**（`is:inline`，各页面内）
3. **外部 TS 脚本**（通过 `<script src>` 引入）
   - `site/src/scripts/explore.ts` — 首页筛选/搜索/关注（由 `index.astro` 引入）
   - `site/src/scripts/leaderboards.ts` — 榜单页交互

### 1.5 公共 Layout / HTML Template

**唯一全局 Layout**：`site/src/layouts/Layout.astro`

包含完整 HTML 骨架（`<!doctype html>` → `<html>` → `<head>` → `<body>`）、
全局 CSS 变量与主题系统（深色/浅色，line 86-261）、顶栏导航、footer、`<slot />`。

所有页面通过 `import Layout from '../layouts/Layout.astro'` 引入。
**无第二个 layout 文件。**

可复用组件：
- `site/src/components/CopyBlock.astro` — 复制代码块
- `site/src/components/ReportBody.astro` — 周报正文渲染
- `site/src/components/leaderboards/BoardSection.astro` — 榜单分区
- `site/src/components/leaderboards/RankTable.astro` — 榜单表格

### 1.6 统一插入 Analytics Script 的位置

**当前不存在任何 analytics 脚本。**

如果需要添加 analytics，唯一合适的统一插入点是
`site/src/layouts/Layout.astro` 的 `<head>` 标签内（line 14-20 区域）。
由于所有页面都使用这个 Layout，在 `<head>` 中插入 `<script>` 标签即可覆盖全部页面。

当前 `<head>` 内容（line 14-30）：
- meta charset / viewport / description / generator
- favicon
- `<title>`
- 一个 `is:inline` 的主题初始化 script

### 1.7 当前路由结构

全部路由（17 个路由文件）：

| 页面 | URL Pattern | 文件 | 生成方式 | 数据来源 | 执行 JS | 适合 browser analytics |
|---|---|---|---|---|---|---|
| 首页 | `/` | `index.astro` | SSG | `daily_changes.json` + `weekly-digest.json` + content collection | 是（explore.ts 筛选） | 是 |
| 榜单 | `/leaderboards` | `leaderboards.astro` | SSG | `src/data/leaderboards/*.json`（9 个榜单） | 是（交互） | 是 |
| 价格 | `/pricing` | `pricing.astro` | SSG（含预渲染 HTML 片段） | `src/data/pricing/*.json` + `price-ledger.rendered.html` | 是（计算器） | 是 |
| 变化 | `/changes` | `changes.astro` | SSG 壳 + 客户端 fetch | 运行时 `/api/v1/changes` | 必须 | 是 |
| 信源 | `/sources` | `sources.astro` | SSG | content collection + `industry_sources.json` | 否 | 是 |
| 接入 | `/agent` | `agent.astro` | SSG | `PUBLIC_ACCESS` config + release | 是（复制） | 是 |
| 关于 | `/about` | `about.astro` | SSG | 无（硬编码） | 否 | 是 |
| 方法 | `/method` | `method.astro` | SSG | `loadVerifiedRelease()` | 否 | 是 |
| 变更记录 | `/changelog` | `changelog.astro` | SSG | `src/data/changelog.ts` | 否 | 是 |
| 归档索引 | `/weekly/` | `weekly/index.astro` | SSG | `weekly-digest.json` + content collection | 否 | 是 |
| 周报详情 | `/weekly/[id]` | `weekly/[id].astro` | SSG（getStaticPaths） | content collection | 否 | 是 |
| 周归档 | `/daily/[week]` | `daily/[week].astro` | SSG（getStaticPaths） | `weekly-digest.json` + `record-index.json` | 否 | 是 |
| 模型详情 | `/model/[modelId]` | `model/[modelId].astro` | SSG（getStaticPaths） | catalog（构建时）+ `/api/v1/`（运行时 fetch） | 必须 | 是 |
| 条目详情 | `/item/[id]` | `item/[id].astro` | SSG（getStaticPaths） | `data/records/*.json` + `data/price-records/*.json` | 是（复制链接） | 是 |
| 证据详情 | `/evidence/[id]` | `evidence/[id].astro` | SSG（getStaticPaths） | `data/price-evidence/*.json` | 否 | 是 |
| 变化 RSS | `/feed.xml` | `feed.xml.ts` | SSG endpoint | `loadVerifiedRelease(changes)` | 否 | 否（RSS 阅读器） |
| 周报 RSS | `/feed/weekly.xml` | `feed/weekly.xml.ts` | SSG endpoint | `loadVerifiedRelease(weekly)` | 否 | 否（RSS 阅读器） |

`site/public/` 下的静态文件：
- `/openapi-v1.json` — OpenAPI 规范
- `/maas-skill/` — Skill 包（install.sh, manifest.json, SKILL.md 等）
- `/llms.txt` — LLM 可读摘要
- `/logos/` — 平台 logo 图片
- `/changes.html` — 独立 changes 页面

### 1.8 model detail 页面生成方式

文件：`site/src/pages/model/[modelId].astro`

- **生成方式**：SSG，构建时 `getStaticPaths()` 从 `loadVerifiedRelease()` 的 `modelIdentities` catalog 生成所有模型页面（line 14-23）
- **URL Pattern**：`/model/{modelId}/`（如 `/model/openai:gpt-5.6-luna/`）
- **数据来源**：
  - 构建时：catalog 提供模型身份信息（`modelId`、`modelName`、`familyId`、`familyName`）
  - 运行时：客户端 `fetch()` 调用 `/api/v1/changes?modelId=` 和 `/api/v1/prices?modelId=` 获取变化与价格（line 78-156）
- **是否执行 JS**：是。内联 `<script is:inline>` 在浏览器中执行 fetch 请求渲染"最近变化"和"当前价格"区域
- **是否适合 browser analytics**：适合。HTML 由 SSG 预渲染，页面有实际内容（model identity）

### 1.9 changes / prices / leaderboard 页面生成方式

**changes 页面**（`site/src/pages/changes.astro`）
- SSG 静态壳 + 客户端 JS 完全接管数据加载
- URL Pattern：`/changes`（带 query params：`?modelId=`、`?familyId=`、`?q=`、`?type=`）
- 构建时仅注入 catalog（模型/系列下拉选项）和 API base URL；运行时 `fetch('/api/v1/changes?...')` 分页加载
- 无 JS 时页面只有空壳

**prices（价格台账）页面**（`site/src/pages/pricing.astro`）
- 纯 SSG，所有数据在构建时注入
- 数据来源：`src/data/pricing/ledger.json`、`gpu.json`、`chips.json` + 预渲染 HTML 片段（`price-ledger.rendered.html`，由 `scripts/build-price-fragment.mjs` + `render-price-ledger.mjs` 在 build 前生成）

**leaderboard 页面**（`site/src/pages/leaderboards.astro`）
- 纯 SSG，构建时读取 `src/data/leaderboards/` 下 9 个 JSON 文件渲染
- `leaderboards.ts` 提供交互（切换榜单 tab、搜索筛选、排序），核心表格内容为静态 HTML

### 1.10 skill / feed / agent 实现方式

**Skill**：不是前端代码，是静态文件包，放在 `site/public/maas-skill/`。
- 文件：`install.sh`、`manifest.json`、`SKILL.md`、`README.md`、`LICENSE`、`skill-version.json`
- 构建：`site/scripts/build-skill-package.py` 在 build 前打包
- URL Pattern：`/maas-skill/install.sh`、`/maas-skill/manifest.json` 等
- 不执行 JS，纯静态文件下载

**Feed（RSS）**：Astro endpoint（`.ts` 文件导出 `GET` 函数），构建时静态输出 XML
- `site/src/pages/feed.xml.ts` — 变化 RSS，最近 100 条变化
- `site/src/pages/feed/weekly.xml.ts` — 周报 RSS，最近 30 期
- 数据来源：`loadVerifiedRelease()` 读取公开 release 数据
- URL Pattern：`/feed.xml`、`/feed/weekly.xml`
- 不执行 JS，纯 XML 静态文件；不适合 browser analytics（RSS 阅读器访问）

**Agent（接入页）**：静态 SSG 页面（`site/src/pages/agent.astro`），展示四种接入方式（Skill / MCP / RSS / REST）的配置说明和复制块

### 1.11 /admin 路由或管理页面体系

**不存在任何 /admin 路由或管理页面体系。**

- `site/src/pages/` 下无 `admin` 目录或 `admin.astro` 文件
- `services/agent-api/src/` 中无 admin 路由；API 是纯匿名只读服务，无鉴权中间件
- 整个仓库无 `admin` 命名的业务文件

---

## 2. Current Data Pipeline

### 2.1 数据分层结构

仓库根 `data/` 目录分为以下层级：

| 层级 | 目录 | 内容 | 产出脚本 |
|---|---|---|---|
| raw（原始抓取） | `data/snapshots/YYYY-MM-DD/` | 每日信源页面快照（.md） | `pipeline/scripts/fetch_sources.py` |
| raw（diff 报告） | `data/diff/YYYY-MM-DD.md` + `.json` | 每日 diff（人读 + 机读） | 同上 |
| normalized（归档） | `data/records/obs_*.json` | Task 01 信源观察归档记录（稳定 ID = sha256 hash） | `sync-diff-to-site.py` |
| normalized（修订） | `data/record-revisions/<id>/N.json` | 记录修订历史 | 同上 |
| normalized（价格） | `data/price-records/price_*.json` | Task 02 价格变化记录 | `fetch-prices.py` |
| normalized（价格修订） | `data/price-record-revisions/price_*/` | 价格记录修订历史 | 同上 |
| normalized（事实） | `data/price-facts/versions/pfv_*.json` | 价格事实版本 | `fetch-prices.py` |
| normalized（证据） | `data/price-evidence/ev_*.json` | 证据摘录 | `fetch-prices.py` |
| registry | `data/model-registry/models.json` | 模型身份注册表（138 model） | T07 系列 |
| 人工编辑 | `data/daily/YYYY-MM-DD.md` | 人工/Agent 编辑的每日动态 | 手动 |
| 人工编辑 | `data/weekly/YYYY-MM-DD.md` | 人工/Agent 编辑的周报 Markdown | 手动 |
| generated（公开投影） | `data/public/v1/` | 公开数据投影根目录（release 形态） | `export-public-data.py` |

### 2.2 generated（公开投影）结构

`data/public/v1/`：
- `manifest.json` — 顶层 manifest（含 datasetVersion、dataThrough、coverage、retainedVersions）
- `releases/ds_<64hex>/` — 每个 datasetVersion 一个子目录，含 8 个文件：
  - `changes.json`、`items.json`、`prices.json`、`evidence.json`、`weekly.json`、`status.json`、`model-identities.json`
  - `manifest.json` — per-release manifest（含 files hash/bytes/coverage）

站点中间数据（prebuild 产物，tracked）：
- `site/src/data/daily_changes.json` — 每日明细（最近 60 天）
- `site/src/data/weekly-digest.json` — 按 ISO 周聚合的归档索引
- `site/src/data/record-index.json` — 可重建的归档索引
- `site/src/data/pricing/ledger.json` — 价格台账
- `site/src/data/pricing/ledger_history/YYYY-MM-DD.json` — 每日台账快照
- `site/src/data/pricing/price-ledger.fragment.html` + `rendered.html` — 预渲染 HTML 片段
- `site/src/data/leaderboards/*.json` — 榜单数据
- `site/public/maas-skill/` — Skill 包产物

### 2.3 哪些数据进入 release

Release 包含三个 scope（证据：`pipeline/scripts/release_manifest.py:35-36`）：

- **content scope**：`site/`（Astro 构建产物 site/dist）+ `data/public/v1/`（公开数据投影）+ `agent-api/{dist,package.json,package-lock.json}`
- **runtime scope**：`agent-api/node_modules/`（完整性校验但不参与身份比对）

release 目录结构（以 `dist-release/rl_<sha10>_<ds12>/` 为例）：
```
rl_<sha10>_<ds12>/
├── metadata/
│   ├── release-manifest.json   # 完整 manifest（含 files 列表 + sha256 + bytes + scope）
│   ├── checksums.sha256         # 全文件 checksum 清单
│   └── versions.json            # 人读摘要（releaseId/gitCommit/datasetVersion/dataThrough/contracts）
├── site/                        # Astro 构建产物（HTML/CSS/图片/feed/skill/openapi）
├── data/public/v1/              # 公开数据投影（manifest + releases/ds_*/）
└── agent-api/
    ├── dist/                    # 编译后的 agent-api（server.js/dataset.js/query.js 等）
    ├── package.json + package-lock.json
    └── node_modules/            # 生产依赖（runtime scope）
```

关键代码路径：`scripts/build-release.sh:84-97` 组装 release 目录。

### 2.4 manifest 如何生成

两层 manifest：

**A. 公开数据 manifest**（`data/public/v1/manifest.json`）
- 由 `pipeline/scripts/export-public-data.py` 的 `publish()` 函数生成
- 两阶段发布：临时目录写盘 → hash/bytes 复核 → 原子 rename → 写 manifest
- manifest 包含：schemaVersion、datasetVersion、generatedAt、dataThrough、coverage、files（含 path/sha256/bytes）、retainedVersions
- 每个 release 子目录也有自己的 `manifest.json`
- 保留策略：当前版本 + 7 自然日内 + 至少上一版

**B. Release manifest**（`metadata/release-manifest.json`）
- 由 `pipeline/scripts/release_manifest.py` 的 `build_manifest()` 函数生成
- 遍历 release 目录所有文件，计算 sha256 + bytes，分 scope（content / runtime）
- 从产物读取 contracts 版本（OpenAPI / skill / publicData）
- 生成三个文件：`release-manifest.json`、`checksums.sha256`、`versions.json`
- 由 `scripts/build-release.sh:100-106` 调用

### 2.5 datasetVersion 如何生成

由 `pipeline/public_export/canonical.py` 的 `compute_dataset_version()` 函数生成：
1. 对 7 个公开集合（changes/items/prices/evidence/weekly/status/modelIdentities）分别计算 `collection_digest`（实体按规范串排序后拼接的 sha256）
2. 将 schemaVersion + dataThrough + 各集合摘要组成 payload
3. `datasetVersion = "ds_" + sha256(canonical_json(payload))`

特性：同输入重建得到相同版本（幂等）；任一实体变化产生新版本；排除 generatedAt 等不稳定字段。

### 2.6 dataThrough 如何生成

由 `pipeline/public_export/canonical.py` 的 `compute_data_through()` 函数生成：
- 语义：全部观察日期（上海日历日）的最大值
- changes: `observationDate`（已是上海日历日）
- prices: `observedAt`（ISO UTC）转上海日历日（+8 无夏令时）
- weekly: `date`（发布日期）
- 这是数据推导值（非墙钟），进 datasetVersion 不破坏稳定性

### 2.7 API 如何读取数据

**Agent-API（Node.js HTTP 服务）**
- 源码：`services/agent-api/src/`
- 启动入口：`server.ts`，默认绑定 127.0.0.1:8787（生产由 nginx 反向代理做 TLS）
- `DATA_ROOT` = `process.env.PUBLIC_DATA_ROOT` ?? `<repo>/data/public/v1`
- 每 30 秒轮询 manifest 热重载，也支持 SIGHUP
- 数据加载：`dataset.ts` 的 `Dataset.load()`：读取 `manifest.json` → 按 manifest.files 条目逐文件加载：路径安全校验 → bytes 校验 → sha256 校验 → JSON.parse
- `DatasetHolder` 管理 current + retained 版本，重载是原子引用替换
- 查询：`query.ts`，keyset 分页（cursor base64url 规范 JSON，HMAC-SHA256 签名）
- REST 路由 8 个、MCP 工具 5 个

### 2.8 UI 如何读取数据

**构建时（Astro SSG）**：
- `site/src/lib/release.ts` 的 `loadVerifiedRelease()` 函数读取 `data/public/v1/manifest.json`，校验 datasetVersion 格式 + manifest 文件路径合法性 + 逐文件 bytes + sha256 校验后才 JSON.parse
- 各页面直接 import 并调用
- 站点中间数据（`site/src/data/*.json`）由 `pipeline/scripts/sync-diff-to-site.py` 等脚本产出，Astro 构建时直接 import

**运行时（客户端 JS）**：
- `site/src/scripts/explore.ts` — 变化页面交互
- `site/src/scripts/leaderboards.ts` — 榜单交互
- changes 和 model detail 页面内联 `fetch()` 调用 `/api/v1/` 端点

### 2.9 pipeline 如何更新

Pipeline 脚本位于 `pipeline/scripts/`，核心流程：
1. `fetch_sources.py` — 信源抓取 → `data/snapshots/` + `data/diff/`
2. `sync-diff-to-site.py` — diff 聚合 → `site/src/data/daily_changes.json` + `weekly-digest.json` + Task 01 归档到 `data/records/` + 修订到 `data/record-revisions/`
3. `fetch-prices.py` — 价格抓取 → 价格记录 + price_changes 挂到 daily_changes
4. `llm-digest.py` — LLM 提炼"今日要点" → highlights 挂到 daily_changes
5. `fetch-leaderboards.py` — 榜单数据 → `site/src/data/leaderboards/`
6. `export-public-data.py` — 公开数据投影 → `data/public/v1/`（含 datasetVersion 计算）

### 2.10 daily-update 如何工作

文件：`.github/workflows/daily-update.yml`
触发：每天 UTC 21:00（北京时间 05:00）定时 + 手动触发（支持 `skip_fetch` 跳过抓取）

流程（9 步）：
1. Checkout main + Setup Python 3.12 + Node 22 + Playwright
2. Fetch sources — `fetch_sources.py`（可跳过）
3. Sync diff to site — `sync-diff-to-site.py`
4. Fetch prices — `fetch-prices.py`（continue-on-error）
5. Pricing extractors regression
6. LLM digest — `llm-digest.py`（continue-on-error）
7. Re-sync with highlights（幂等补齐）
8. Fetch leaderboards（continue-on-error）+ Fetch article images（continue-on-error）
9. Prebuild site artifacts — build-price-fragment / render-price-ledger / build-skill-package
10. Export public data — `export-public-data.py` + `--check`
11. Commit new data — `git add data/ site/src/data/ site/public/maas-skill/ site/public/logos/` → commit → push
12. Deploy — Setup SSH key → `ops/deploy-release.sh --commit "$(git rev-parse HEAD)"`（MAAS_DEPLOY_MODE=release）
13. Online verify — `ops/verify-release.sh --online --expect-release "$RID"`
14. Health check — 如果 fetch-prices 全部失败（退出码 2）置红 run
15. Notify failure — 创建/追加 GitHub Issue

并发控制：`concurrency.group: daily-update`，`cancel-in-progress: false`

### 2.11 production release 如何激活

**构建链**（`scripts/build-release.sh`）6 步：
0. preflight — 工作区干净 + commit 校验（HEAD == 声明 commit）
1. 公开投影 — `export-public-data.py` + `--check`
2. 全量回归 — `scripts/run-all-tests.sh`
3. tracked diff 复查 — 确认构建无未解释的 tracked 改动
4. agent-api 生产包 — 完整编译 → 裁剪为生产依赖
5. 组装 release — site/dist + data/public/v1 + agent-api → `dist-release/rl_<sha10>_<ds12>/`
6. manifest — `release_manifest.py build`

**部署链**（`ops/deploy-release.sh`）：
- 通道选择：`MAAS_DEPLOY_MODE` 环境变量 > `ops/deploy-mode` 文件 > 默认 legacy
- 仓库文件永久保持 legacy，release 通道由 CI 环境变量注入
- release 通道：上传 incoming → SSH 调用 `maasweekly-activate <rid>` 激活 → 公网冒烟

**服务器端激活**（`ops/server/maasweekly-activate`，root via sudoers）蓝绿切换完整事务：
1. 起候选服务（非公开槽位）+ 冒烟
2. 快照三个 nginx include 旧状态
3. 写候选 nginx include（agent-upstream + site-root + agent-routes）
4. `nginx -t` 校验
5. `nginx -s reload`
6. 原子指针交换（`current` symlink）
7. 切换后入口冒烟
8. 记录槽位映射 + 停旧槽

当前 manifest 实际值（`data/public/v1/manifest.json`）：
- datasetVersion: `ds_03c2bf0b968d9fc4c53da8571a833e70ca2b3c95081aa0450ddfc4e5ecdd7e55`
- dataThrough: `2026-09-29`
- coverage: changes 6892（2026-09-04 至 2026-09-29）、prices facts 1431、evidence 10924、weekly 23
- retainedVersions: 10

---

## 3. Current Deployment

### 3.1 release 目录结构

见 §2.3。

### 3.2 current / symlink / include 的真实实现

**current 符号链接**（`ops/server/maasweekly-activate`）：
- `current_release()`：`readlink "$ROOT/current" | sed 's|^releases/||'`
- `swap_pointer()`：原子交换，`ln -sfn` + `mv -T`（GNU 优先，BSD 退化）
- 同时维护 `previous` 符号链接指向旧版本（回滚保险）

**三个动态 nginx include**（由激活器事务维护）：
- `/srv/maasweekly/shared/nginx/agent-upstream.inc` — http ctx，upstream 槽位端口（blue 8788 / green 8789）
- `/srv/maasweekly/shared/nginx/site-root.inc` — server ctx，root 指向当前 release site
- `/srv/maasweekly/shared/nginx/agent-routes.inc` — server ctx，REST/MCP/RSS/Skill locations

三 include 事务性：事务前快照 → 候选三份全部就位 → nginx -t → reload → 指针切换 → 入口冒烟；任一步失败全有或全无恢复。

### 3.3 site root

两套并存：
- **legacy 通道**：`/var/www/maasweekly`（rsync 直写）
- **release 通道**：`/srv/maasweekly/releases/<rid>/site`（由 `site-root.inc` 动态指向）
- **首发兼容态**：`site-root.inc` 初始值为 `root /var/www/maasweekly;`，首次激活才指向 release 目录

### 3.4 agent-api

- 构建：`scripts/build-release.sh:65-81`（完整编译 TS → 裁剪为生产依赖）
- 启动 wrapper：`/usr/local/bin/maas-agent-run`，执行 `exec /usr/bin/node "${MAAS_RELEASE_DIR}/agent-api/dist/server.js"`
- systemd 模板：`ops/maas-agent@.service`（`maas-agent@blue` 8788 / `maas-agent@green` 8789）
- 槽位 env 由激活器写入 `shared/slots/<slot>.env`
- 绑定 127.0.0.1，永不监听公网；TLS 由 nginx 终结

### 3.5 systemd unit

路径：`ops/maas-agent@.service`
- `Type=simple`，`User=maasagent`，`Group=maasagent`
- `EnvironmentFile=/srv/maasweekly/shared/agent.env` + `EnvironmentFile=-/srv/maasweekly/shared/slots/%i.env`
- `ExecStart=/usr/local/bin/maas-agent-run`
- `Restart=on-failure`，`RestartSec=2`，`TimeoutStartSec=20`
- 安全硬化：`NoNewPrivileges`、`PrivateTmp`、`ProtectSystem=strict`、`ProtectHome`、`ReadWritePaths=/srv/maasweekly/shared/state`、`ProtectKernelTunables/Modules/ControlGroups`、`RestrictNamespaces/SUIDSGID`、`LockPersonality`、`LimitNOFILE=8192`
- 不用 `MemoryDenyWriteExecute`（V8 JIT 需要 RWX 内存页）
- `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`

### 3.6 nginx include

两个稳定配置（install-production.sh 安装，不随 release 变化）：
- `/etc/nginx/conf.d/maasweekly-agent.conf` ← `ops/nginx/maasweekly-agent-http.conf`
  - http ctx：两个 limit_req_zone（REST 2r/s + MCP 1r/s）+ `include /srv/maasweekly/shared/nginx/agent-upstream.inc`
- `/etc/nginx/snippets/maasweekly-agent.conf` ← `ops/nginx/maasweekly-agent-server.conf`
  - server ctx：`include /srv/maasweekly/shared/nginx/agent-routes.inc`

三个动态 include（激活器事务维护，见 §3.2）。

agent-routes.inc 的 location 内容（maasweekly-activate:196-250）：
- `/api/v1/` — limit_req api_anon burst=10，proxy_pass agent_api，GET/HEAD/OPTIONS only
- `= /api/mcp` — limit_req mcp_anon burst=5，256k body，POST/GET/HEAD/DELETE/PUT，no-store
- `= /feed.xml` — types {} 清空 + application/rss+xml，30 分钟缓存，ETag
- `= /feed/weekly.xml` — 同上
- `/maas-skill/` — 5 分钟缓存，try_files

**主 HTTPS 配置** `/etc/nginx/snippets/maasweekly-https.conf` 在服务器侧，**不在仓库内**。仓库改造仅替换 root 和追加 agent snippet include。

### 3.7 rollback

`ops/rollback-release.sh` + `maasweekly-activate:577-608`
- 命令：`ops/rollback-release.sh <rid> --reason "<原因>"`（必须留原因）
- 服务器侧规则：目标 release 必须覆盖当前 datasetVersion（防数据回退丢公开 ID）
- 复用 `switch_service_tx` 蓝绿切换事务
- rollback 失败时：目标 release 保留原位（`keep_release`），只恢复指针/include/服务
- 记录 `activations.log`：`rollback $rid reason="..."`

### 3.8 online verify

`ops/verify-release.sh` 四入口验收：
1. 服务器 current：经受限 shell 的固定 status 动作取 `current` / `datasetVersion` / `dataThrough` / `gitCommit`
2. REST：`/api/v1/status` + `/api/v1/changes?limit=10` 的 datasetVersion 必须与服务器一致
3. MCP：initialize 返回 serverInfo；tools/list 包含五工具；真实 tools/call 返回正确 datasetVersion
4. RSS：两个 feed content-type=application/rss+xml + ETag + 304
5. Skill：manifest.json 结构合法 + install.sh 可达

任一不通过 → exit 1（CI 红色）。

### 3.9 permission / ACL

双消费者分树模型（无 ACL、不改 nginx 全局用户、不用 world-readable）：
`ops/server/maasweekly-activate:416-475` `prepare_release_runtime_permissions()`

| 路径 | 属主 | 权限 |
|---|---|---|
| `<rid>/` | root:root | 0711（仅 traverse） |
| `<rid>/site/` | root:www-data | dirs 0750 / files 0640 |
| `<rid>/agent-api/` | root:maasagent | dirs 0750 / files 0640 / 可执行 0750 |
| `<rid>/data/` | root:maasagent | dirs 0750 / files 0640 |
| `<rid>/metadata/` | root:root | root 自用 |

消费者：nginx worker(www-data) 读 site/；agent-api(maasagent) 读 agent-api/ + data/。
符号链接逃逸复核（绝对路径符号链接 → 拒绝）。

其他权限：
- sudoers 单行 NOPASSWD：`maasdeploy ALL=(root) NOPASSWD: /usr/local/sbin/maasweekly-activate`
- agent.env：root:maasagent 0740
- maasweekly-activate：root:root 0750

### 3.10 production secrets

- **CURSOR_SECRET**（cursor MAC 密钥）：`ops/install-production.sh:96` 在服务器现场用 `openssl rand -hex 32` 生成，写入 `/srv/maasweekly/shared/agent.env`（root:maasagent 0740），不入仓库
- **DEPLOY_SSH_KEY**：GitHub Actions secret，forced-command key（authorized_keys 前缀 `command="...deploy-shell",no-pty,no-agent-forwarding,no-port-forwarding,no-X11-forwarding`）
- **LLM_API_KEY / OPENROUTER_API_KEY**：GitHub Actions secrets，通过 `env:` 注入，不落盘仓库
- **GH_TOKEN**：使用 `github.token`
- **.gitignore** 排除 `.env` 和 `.env.*`
- **MCP_ALLOWED_ORIGINS**：env 变量，默认空，生产值在服务器 agent.env 中

红线（ops/README.md:102-103）：不把 secret 写进 systemd unit、命令行、Actions 参数或日志；CURSOR_SECRET 只存在于服务器 `shared/agent.env`。

### 3.11 Analytics 新增数据文件、API 或 Dashboard 应进入现有 release 模型还是独立部署

**结论：进入现有 release 模型。**

理由：
1. 现有 release 通道已是成熟、可校验、可回滚的统一发布机制（build → manifest → 上传 → 激活 → verify），Analytics 产物（聚合数据、Dashboard 静态页）没有理由另起一套发布链
2. Analytics Dashboard 若为 `/admin/analytics` 静态页，自然进入 `site/dist/`，随 release 一起发布
3. Analytics 聚合数据若为 JSON，自然进入 `data/public/v1/` 或独立 `data/analytics/` 子目录，随 release 一起发布
4. 独立部署会引入第二套发布/回滚/权限模型，增加运维复杂度且违背"单一 release"原则
5. 现有 release 模型已支持 content scope 扩展（release_manifest.py 按目录遍历），无需改造

**例外**：若 Analytics 后端（如 Umami/Plausible）是独立服务（非静态产物），则该服务本身独立部署（类似 agent-api），但其聚合产物仍进入 release。见 architecture 文档 §3 技术选型。

---

## 4. Current Nginx / Access Log

### 4.1 access_log 是否启用

**仓库内没有任何 `access_log` 指令。** 对 ops/、.github/、docs/、services/ 全量 grep `access_log|log_format|error_log|/var/log/nginx|logrotate` 返回零结果。

这意味着：
- 本项目仓库**不管理 access_log 配置**
- access_log 行为由服务器上预先存在的 nginx 全局配置决定（`/etc/nginx/nginx.conf` 的 http 块默认配置）
- 项目只通过两个稳定 conf（conf.d + snippets）和三个动态 include 注入路由/限流/upstream，不碰 log 指令
- 服务器 nginx 1.28.3 (Ubuntu) 默认配置通常写入 `/var/log/nginx/access.log`，但本项目仓库不对此做任何声明或覆盖

### 4.2 log_format

仓库内无 `log_format` 指令。使用 nginx/Ubuntu 默认的 combined 格式（或服务器管理员配置的自定义格式），本项目不干预。

### 4.3 日志路径 / rotation / retention

仓库内不声明日志路径、rotation、retention 配置。由服务器 OS 层面的 logrotate（通常 `/etc/logrotate.d/nginx`）管理，不在本项目仓库范围内。

release 目录有 retention（`retention_cleanup()`：7 天 + retainedVersions 保护），但这是 release 目录清理，不是日志 retention。

### 4.4 User-Agent / Referrer / request path / remote IP

仓库内 nginx 配置不含 `log_format` 指令，不显式记录或排除这些字段。如果服务器使用默认 combined 格式，以下字段会被记录：
- `$http_user_agent`（User-Agent）
- `$http_referer`（Referer）
- `$request`（含 method + path + protocol）
- `$remote_addr`（remote IP）

本项目不干预。

### 4.5 是否经过 CDN / reverse proxy

**架构上是 nginx 直接面对公网，无 CDN 前置**：
- DNS 直接解析到服务器 IP：`daily.maas.click → 47.237.135.97`
- TLS 证书由 certbot 在服务器本地管理
- nginx 1.28.3 监听 443，80 端口统一 301 → 443
- 无 Cloudflare/CloudFront/Aliyun CDN 的任何配置痕迹
- `deploy-release.sh:102` 注释提到"CDN/浏览器缓存容忍窗口"，但这只是冒烟重试的防御性设计，不代表有 CDN 前置

### 4.6 是否可以识别真实 client IP

**仓库内无 `set_real_ip_from`、`real_ip_header`、`X-Forwarded-For` 处理。**

原因：架构上 nginx 直接面对公网，`$remote_addr` 就是真实客户端 IP，不需要 realip 模块处理。

代理回环方面：
- nginx proxy_pass 到 `127.0.0.1:<port>`
- 只设置 `proxy_set_header Host $host` 和 `proxy_set_header X-Request-Id $request_id`
- **不设置 `X-Forwarded-For` / `X-Real-IP`** — agent-api 不需要客户端 IP（它是数据 API，不做 IP 级鉴权/分析）
- 限流基于 `$binary_remote_addr`（maasweekly-agent-http.conf:14,17），在 nginx 层直接取

### 4.7 当前是否有 bot filtering

**无。** 仓库内 nginx 配置不含任何 bot filtering 指令（无 `if $http_user_agent`、无 map 匹配 bot UA、无 deny by UA）。REST/MCP 路由用 `limit_req` 做匿名限流（2r/s REST + 1r/s MCP），但不区分 bot/human。

### 4.8 当前是否有 analytics 相关日志处理

**无。** 仓库内不含任何 analytics 集成：
- 无 Matomo/Umami/Plausible/Google Analytics 的脚本注入
- 无 analytics 日志处理/导出配置
- 无 pageview tracking
- agent-api (Node) 只用 console.log 输出启动/热重载/关闭日志到 stdout（被 systemd journal 捕获），不做请求级 access log

### 4.9 T08-5 GEO Crawler Observability 能否直接建立在现有 Nginx access log 上

**不能直接建立。** 缺少以下条件：

1. **access_log 配置不在仓库内**：主站 nginx 全局配置（`/etc/nginx/nginx.conf` / `maasweekly-https.conf`）在服务器侧，仓库不可审计、不可版本化、不可随 release 管理
2. **log_format 不可控**：依赖服务器默认 combined 格式，无法保证 UA/Referer/IP 字段的记录格式稳定
3. **无 log 轮转/retention 声明**：无法保证历史日志可回溯
4. **无日志导出管道**：日志在服务器 `/var/log/nginx/`，无机制将其导入 Analytics Dataset
5. **无 AI Crawler Registry**：无已知 AI crawler UA 模式库可匹配

若要建立 T08-5，需要（见 architecture 文档 §8）：
- 在仓库内声明 analytics 专用的 `log_format`（含 UA/Referer/Path/IP）并纳入 nginx 配置管理
- 建立 AI Crawler Registry（需官方 evidence）
- 建立日志导出管道（服务器 → Analytics Dataset）

**本任务不修改 Nginx。**

---

## 5. Current Analytics / Telemetry

### 5.1 搜索结果

全仓搜索以下关键词，确认**当前不存在任何 analytics / telemetry / tracking 实现**：

| 关键词 | 源代码命中 | 判定 |
|---|---|---|
| analytics / telemetry / gtag / plausible / umami / matomo / posthog / google analytics / segment | 零 | 无任何 analytics SDK、追踪脚本、pageview 上报 |
| referrer / utm_ / visitor | 零 | 无 UTM 解析、无 visitor ID |
| pageview / page_view | 零 | 无页面浏览追踪 |
| tracking | 仅 CSS 字体排版语义（letter-spacing） | 与用户追踪无关 |
| session | 仅 AI 行业数据内容（Claude Managed Agents session、OpenAI session billing、leaderboard session_cost） | 与用户会话追踪无关 |

数据文件中出现的 "Analytics API" / "Conversion Tracking" 是上游厂商的变化记录数据内容（如 Claude Enterprise Analytics API），**不是本站功能**。

前端 fetch 调用全部指向**第一方 API**（`apiBase` = `/api/v1`），无任何第三方域名的请求。

### 5.2 防遥测守护测试

`tests/test_skill_package.py:376` 有一个 `test_no_sudo_no_telemetry` 测试，断言 Skill 安装脚本不调用 sudo 且不做遥测上报（检查 curl 无 POST/--data）。这是一个**防止引入遥测**的守护测试，反向证明项目有意不包含遥测。

### 5.3 结论

当前仓库**零 analytics、零 telemetry、零 tracking、零 UTM、零 visitor ID、零 pageview**。
不存在重复建设的风险。

---

## 6. Current Privacy / Security

### 6.1 CSP（Content-Security-Policy）

**不存在。** 仓库内的 nginx 配置和 Astro Layout 中均无 CSP header 设置。nginx `add_header` 指令仅用于 `Cache-Control`。

### 6.2 Cookie

**零 Cookie。** `site/src/` 全部源代码中无 `document.cookie`、`setCookie`、`cookieParser`。agent-api 服务端 CORS 配置明确注释"匿名，无 credentials"，`Access-Control-Allow-Origin: *` 且不设 `Allow-Credentials`。

### 6.3 LocalStorage

仅两处，均为纯本地 UI 偏好，无任何追踪或外传：
- `site/src/layouts/Layout.astro:23,71` — 存取 `maas-theme`（深/浅色主题偏好）
- `site/src/scripts/explore.ts:11,68` — 存取 `maas-followed`（用户关注的平台列表）

两处均有 try/catch 保护，localStorage 不可用时静默降级。

### 6.4 Privacy Policy

**不存在。** 全仓无 `privacy.md`、`privacy.html` 文件，也无"隐私政策"/"Privacy Policy"字样的页面。`site/public/llms.txt:14` 提到"许可条款待产品确认后在此更新"，说明法律文件尚未建立。

### 6.5 robots.txt

**不存在。** `site/public/` 目录下无 `robots.txt` 文件，全仓搜索确认无此文件。

### 6.6 security headers

**均不存在。** nginx 配置中无以下任何 header：
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Strict-Transport-Security` (HSTS)
- `Referrer-Policy`
- `Permissions-Policy`
- `Content-Security-Policy`

nginx 的 `add_header` 仅用于 Cache-Control。主 HTTPS 配置文件 `maasweekly-https.conf` 不在仓库中，可能由服务器管理员单独维护，但从 install-production.sh 的改造逻辑看，该文件原本只有 `root` 指令，仓库改造仅替换 root 和追加 agent snippet include，未添加 security headers。

### 6.7 third-party script 限制

- Layout.astro 的 `<head>` 中**无任何第三方 script/iframe/CDN 引用**
- 全站 CSS 为内联（`Layout.astro` 的 `<style is:global>`），无外部字体/CDN
- 前端 JS 仅引用第一方 API（`/api/v1`）和内联脚本
- agent-api 的 CORS 设置为 `Access-Control-Allow-Origin: *`（匿名只读公开数据），不涉及 credentials

### 6.8 IP 日志策略

- **nginx 层**：`ops/nginx/maasweekly-agent-http.conf:14,17` 使用 `$binary_remote_addr` 建立限流 zone，但这是用于限流而非持久化 IP 日志
- **应用层**：`services/agent-api/src/http.ts` 和 `mcp.ts` 中**不记录客户端 IP**。请求处理只生成 `requestId`（UUID），不提取或存储 `req.socket.remoteAddress` 或 `x-forwarded-for`
- **nginx access log**：仓库内配置未显式设置 `access_log off` 或自定义 log format，将使用 nginx 默认 access log（通常记录 IP）。这是服务器级配置，不在仓库中
- 无明确的 IP 日志保留/脱敏策略文档

### 6.9 production secret 管理

见 §3.10。Secret 管理总体设计良好：无硬编码 secret，生产 secret 在服务器现场生成或存 GitHub Actions secrets，仓库中仅含占位符和变量名。

### 6.10 Cookie-less Analytics 是否可行

**可行。** 当前架构天然适合 cookie-less analytics：
- 零 cookie、CORS 匿名无 credentials
- 已有 `test_no_sudo_no_telemetry` 守护测试防止引入遥测
- 纯 SSG + 第一方 API，无第三方脚本
- 若采用 Umami/Plausible 等 cookie-less 方案，与现有架构无冲突

见 architecture 文档 §3-§4 技术选型与 visitor/session 策略。

---

## 7. Relevant Code Paths

| 用途 | 路径 |
|---|---|
| 全局 HTML head 模板（Analytics 唯一插入点） | `site/src/layouts/Layout.astro` |
| Astro 配置 | `site/astro.config.mjs` |
| 站点域名/接入配置 | `site/src/config/public-access.ts` |
| 构建脚本 | `site/package.json:10` build 脚本 |
| build-release.sh（生产构建入口） | `scripts/build-release.sh` |
| deploy-release.sh（部署入口） | `ops/deploy-release.sh` |
| verify-release.sh（验收） | `ops/verify-release.sh` |
| rollback-release.sh（回滚） | `ops/rollback-release.sh` |
| lib-release.sh（公共库） | `ops/lib-release.sh` |
| install-production.sh（服务器安装） | `ops/install-production.sh` |
| maasweekly-activate（服务器侧激活器） | `ops/server/maasweekly-activate` |
| maasweekly-deploy-shell（受限 shell） | `ops/server/maasweekly-deploy-shell` |
| maas-agent-run（槽位启动 wrapper） | `ops/server/maas-agent-run` |
| release_manifest.py | `pipeline/scripts/release_manifest.py` |
| release_manifest_verify.py | `ops/server/release_manifest_verify.py` |
| export-public-data.py（公开投影） | `pipeline/scripts/export-public-data.py` |
| canonical.py（datasetVersion/dataThrough） | `pipeline/public_export/canonical.py` |
| public schema | `schemas/public-v1/*.schema.json`（8 个） |
| 公开数据 manifest | `data/public/v1/manifest.json` |
| 公开数据 release | `data/public/v1/releases/<datasetVersion>/` |
| model-registry | `data/model-registry/models.json` |
| systemd unit 模板 | `ops/maas-agent@.service` |
| env 样例 | `ops/maas-agent.env.example` |
| nginx http 稳定配置 | `ops/nginx/maasweekly-agent-http.conf` |
| nginx server 稳定 snippet | `ops/nginx/maasweekly-agent-server.conf` |
| agent-api server.ts | `services/agent-api/src/server.ts` |
| agent-api http.ts | `services/agent-api/src/http.ts` |
| agent-api dataset.ts | `services/agent-api/src/dataset.ts` |
| agent-api query.ts | `services/agent-api/src/query.ts` |
| daily-update workflow | `.github/workflows/daily-update.yml` |
| deploy workflow | `.github/workflows/deploy.yml` |
| weekly-update workflow | `.github/workflows/weekly-update.yml` |
| OpenAPI v1 | `site/public/openapi-v1.json` |
| 防遥测守护测试 | `tests/test_skill_package.py:376` |
| T07-5 ontology 设计 | `docs/product/maas-daily-product-plan/task-07-5-cross-platform-ontology-design.md` |
| T07-5.1 ontology inventory | `docs/product/maas-daily-product-plan/task-07-5-1-ontology-inventory.md` |

---

## 8. Constraints

T08-0 调查发现的硬约束（影响后续 T08-1 至 T08-8 设计）：

1. **前端是纯 SSG**：Astro 静态生成，无 SSR/adapter。Browser analytics 只能在客户端 JS 执行，不存在服务端渲染注入点。统一插入点是 `Layout.astro` 的 `<head>`。

2. **无 admin 体系**：无 `/admin` 路由、无鉴权中间件、无管理后台。`/admin/analytics` Dashboard 需要从零建立，且必须解决 authentication 问题（当前 API 是纯匿名只读）。

3. **T07-5 ontology 未实现**：`developer_id` / `platform_id` / `upstream_model_id` 是 T07-5 设计的新实体，当前仍处于 inventory 阶段，**未进入 public schema**。当前 public catalog 只有 `modelId` / `modelName` / `familyId` / `familyName`。Analytics Page Taxonomy 不能依赖这些字段。

4. **nginx access_log 不在仓库内**：主站 nginx 全局配置（含 log_format）在服务器侧，仓库不可审计。T08-5 GEO Crawler 不能直接建立在现有 access log 上。

5. **无 CDN 前置**：nginx 直接面对公网，`$remote_addr` 即真实客户端 IP。这对 traffic attribution 是有利条件。

6. **release 模型是唯一发布通道**：所有产物（site / data / agent-api）必须进入 release 才能上线。Analytics 产物不例外。

7. **先提交后发布**：daily-update workflow 先 `git commit` 数据到 HEAD，再从精确 SHA 构建 release。Analytics 聚合数据若由 pipeline 产出，必须遵循此模式。

8. **零 cookie / 零 PII 原则**：当前架构零 cookie、CORS 匿名无 credentials、有防遥测守护测试。Analytics 设计必须保持 cookie-less，不引入 PII。

9. **双消费者分树权限**：release 目录内 `site/` 归 www-data 读、`agent-api/` + `data/` 归 maasagent 读。Analytics 数据文件的属主需按消费者确定。

10. **datasetVersion 稳定性**：datasetVersion 排除 generatedAt 等不稳定字段。Analytics 聚合数据若进入 `data/public/v1/`，其时间字段（generatedAt）不能影响 datasetVersion，或独立版本管理。
