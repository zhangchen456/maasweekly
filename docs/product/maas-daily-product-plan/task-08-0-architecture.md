# T08-0 Analytics / SEO / GEO Observability — Architecture

日期：2026-09-30。状态：**设计冻结（不编码）**。

前置：T08-0 Inventory 已完成（见 `task-08-0-inventory.md`）。本文档所有
proposed architecture 均明确标记为 **[PROPOSED]**，不描述为 existing behavior。

本文档遵循 **Inspect → Evidence → Decide → Document** 原则，所有决策建立在
当前仓库代码与生产架构基础上。

---

## 1. Decision Summary

| 决策项 | 结论 | 依据 |
|---|---|---|
| Traffic Analytics 技术选型 | **Self-hosted Umami**（cookie-less） | §3 |
| Visitor / Session | **provider-generated visitor_id + 30 分钟 session**，无 cookie、无 fingerprinting | §4 |
| Event Schema | **8 事件**：page_view / landing / content_view / scroll_depth / model_click / change_click / outbound_click / copy | §5 |
| Page Taxonomy | **11 种 page_type**，基于真实路由 | §6 |
| Traffic Attribution | **UTM > known referrer > direct**，11 个 source channel | §7 |
| SEO Architecture | **GSC + Bing Webmaster**，GitHub Actions 周同步，凭证用 GitHub Secrets | §8 |
| GEO Crawler Architecture | **独立 analytics log_format + AI Crawler Registry**，不依赖现有 access log | §9 |
| Unified Analytics Dataset | **沿用 raw → normalized → aggregate → manifest 模式**，`data/analytics/` 独立子目录 | §10 |
| Dashboard | **`/admin/analytics` 静态生成 + API 读取**，需 authentication | §11 |
| Failure Strategy | **Analytics 失败不阻断核心数据服务**，降级保留 last-known-good | §12 |
| Release 模型 | **Analytics 产物进入现有 release**，不独立部署 | Inventory §3.11 |

---

## 2. Traffic Analytics Decision

### 2.1 评估维度

| 维度 | Umami | Plausible | 自建 Analytics |
|---|---|---|---|
| 接入复杂度 | 低（一行 script） | 低（一行 script） | 高（需自建采集+存储+查询） |
| Cookie-less | 是（默认） | 是（默认） | 取决于实现 |
| PV | 是 | 是 | 需自建 |
| UV | 是（visitor_id，无 cookie） | 是（visitor_id，无 cookie） | 需自建 |
| Session | 是 | 是 | 需自建 |
| Referrer | 是 | 是 | 需自建 |
| UTM | 是 | 是 | 需自建 |
| Custom Event | 是 | 是（需付费版） | 需自建 |
| Custom Properties | 是 | 付费版 | 需自建 |
| API | 是（REST API） | 是（需付费版） | 取决于实现 |
| 历史数据查询 | 是（自托管，全量） | 付费版有限 | 取决于实现 |
| Self-host | 是（Docker / Node） | 是（Docker / Elixir） | 不适用 |
| 数据所有权 | 完全自有 | 完全自有 | 完全自有 |
| 成本 | 免费（自托管） | 免费（CE 版）/ 付费（Cloud） | 高（开发+维护） |
| 维护成本 | 中（需维护 Umami 服务） | 中（需维护 Plausible 服务） | 极高 |
| 与 maasweekly pipeline 集成 | 低（REST API 拉取聚合） | 中（Cloud 版 API 限制） | 高（原生集成） |

### 2.2 Recommended: Self-hosted Umami

**理由：**

1. **cookie-less 默认**：Umami 默认不设 cookie，使用随机 visitor_id（localStorage 或服务端生成），符合当前零 cookie 架构与 §4 visitor/session 策略
2. **自托管，数据自有**：与 maasweekly "数据所有权"原则一致（现有 pipeline 全自建，数据全在仓库/服务器）
3. **REST API 成熟**：Umami 提供 REST API 可拉取 PV/UV/Session/Referrer/Event 聚合数据，便于 T08-6 统一数据层拉取
4. **Custom Event + Custom Properties 免费**：Plausible 的 Custom Event 需付费版，Umami 免费版即支持
5. **部署形态契合**：Umami 是 Node.js 服务，可与 agent-api 并行以 systemd + nginx 反向代理部署，复用现有部署模式（不进入 release，类似 agent-api 独立服务）
6. **接入简单**：一行 `<script>` 插入 `Layout.astro` 的 `<head>`，覆盖全站 17 个路由

**部署方式 [PROPOSED]：**
- Umami 服务独立部署（类似 agent-api），systemd 管理，nginx 反向代理
- Umami 数据库（PostgreSQL 或 MySQL）在服务器本地，不进入 release
- Umami 采集脚本插入 `site/src/layouts/Layout.astro` 的 `<head>`
- Umami 聚合数据通过 REST API 由 T08-6 数据层拉取进入 Unified Analytics Dataset

### 2.3 Alternative: Self-hosted Plausible

**理由：** 同样 cookie-less、自托管，但 Custom Event 需付费版，且 Elixir 技术栈与现有 Node/Python 栈不匹配，维护成本略高。

### 2.4 Rejected / Not Recommended

- **自建 Analytics**：开发与维护成本极高，且无法达到 Umami/Plausible 的成熟度，违背"不重复建设"原则
- **Google Analytics**：非 cookie-less，与零 cookie 架构冲突，数据不在自有服务器
- **Cloud 版 Plausible/Umami**：数据不在自有服务器，违背数据所有权原则

---

## 3. Traffic Analytics Decision（与任务书 §9 对齐）

见 §2。推荐 Self-hosted Umami。

---

## 4. Visitor / Session Strategy

### 4.1 Visitor

**[PROPOSED] provider-generated visitor_id，无 cookie、无 fingerprinting。**

| 维度 | 设计 |
|---|---|
| visitor_id 生成 | Umami 服务端生成随机 ID（默认行为） |
| 存储 | 不设 cookie；Umami 默认使用 localStorage 或服务端哈希 |
| PII | 不采集 |
| fingerprinting | 不使用 |
| 永久跟踪 | 不永久跟踪，visitor_id 可随用户清除 localStorage 而失效 |
| Cookie Consent | 不需要（无 cookie） |

**选择 Umami 默认行为**，不自建 visitor_id 机制。Umami 的 visitor_id 设计已满足"无 PII、无 fingerprinting、无永久跟踪"要求。

### 4.2 Session

**[PROPOSED] 30 分钟 session timeout。**

| 维度 | 设计 |
|---|---|
| session start | 首次 page_view 产生新 session |
| session timeout | 30 分钟无活动 → session 结束，下次 page_view 产生新 session |
| landing page | session 的第一个 page_view 的 page_type + URL |
| returning visit | visitor_id 已存在 → returning；否则 new |

**选择 Umami 默认 session 机制**（30 分钟），不自建。

### 4.3 避免项

- 不采集 PII
- 不做 fingerprinting（canvas/WebGL/字体指纹等）
- 不永久跟踪用户
- 不引入 Cookie Consent 复杂度（无 cookie）

---

## 5. Event Schema

### 5.1 事件清单

**[PROPOSED] 8 个事件：**

| 事件 | trigger | 说明 |
|---|---|---|
| page_view | 页面加载 | 所有页面 |
| landing | session 首个 page_view | 由 session 逻辑判定 |
| content_view | model/changes 等内容展示 | 客户端 fetch 成功后 |
| scroll_depth | 滚动到 25/50/75/100 阈值 | 每个 page view 每 threshold 最多一次 |
| model_click | 点击模型链接 | 指向 `/model/<modelId>` |
| change_click | 点击变化条目 | 指向 `/item/<id>` |
| outbound_click | 点击外部链接 | 指向外站 |
| copy | 复制操作 | CopyBlock / 永久链接复制 |

### 5.2 page_view

| 维度 | 设计 |
|---|---|
| trigger | 页面加载（Umami `trackView` 自动触发） |
| required fields | `page_type`、`page_url`、`page_id`（若可推导）、`dataset_version`（构建时注入）、`data_through`（构建时注入） |
| optional fields | `referrer`、`utm_source`、`utm_medium`、`utm_campaign` |
| deduplication | Umami 自身去重（同 visitor + 同 URL 短时间内） |
| privacy | 不记录用户输入内容；不记录完整 IP（Umami 默认截断 IP） |

**dataset_version / data_through 注入 [PROPOSED]：**
- 构建时从 `loadVerifiedRelease()` 取 `datasetVersion` 和 `dataThrough`
- 作为 `data-*` 属性写入 `<html>` 或 `<body>` 标签
- page_view 事件读取这些属性作为 custom property 上报

### 5.3 landing

| 维度 | 设计 |
|---|---|
| trigger | session 的首个 page_view |
| 判定方式 | 由 Umami session 逻辑判定（首个 page_view 自动是 landing） |
| required fields | 同 page_view + `is_landing: true` |
| privacy | 同 page_view |

### 5.4 content_view

| 维度 | 设计 |
|---|---|
| trigger | changes 页 / model detail 页客户端 fetch 成功后 |
| required fields | `page_type`、`content_type`（changes/prices）、`model_id`（若适用） |
| optional fields | `family_id`、`provider_id` |
| deduplication | 同一 page view 同一 content_type 最多一次 |
| privacy | 不记录具体条目内容 |

### 5.5 scroll_depth

| 维度 | 设计 |
|---|---|
| trigger | IntersectionObserver 检测滚动到 25/50/75/100 阈值 |
| required fields | `page_type`、`depth`（25/50/75/100） |
| deduplication | **同一个 page view 每个 threshold 最多一次** |
| privacy | 无额外隐私风险 |

### 5.6 model_click

| 维度 | 设计 |
|---|---|
| trigger | 点击指向 `/model/<modelId>` 的链接 |
| required fields | `model_id`、`page_type`（来源页） |
| optional fields | `family_id`、`provider_id` |
| privacy | 无 |

### 5.7 change_click

| 维度 | 设计 |
|---|---|
| trigger | 点击指向 `/item/<id>` 的链接 |
| required fields | `item_id`、`page_type`（来源页） |
| optional fields | `record_type`（source_observation/price_change） |
| privacy | 无 |

### 5.8 outbound_click

| 维度 | 设计 |
|---|---|
| trigger | 点击指向外站的链接 |
| required fields | `target_host`、`target_category` |
| optional fields | 无 |
| **是否记录完整 URL** | **不记录完整 URL**，只记录 `target_host` + `target_category`（如 github/official-doc/blog/social） |
| privacy | 不记录完整 URL，避免泄露用户具体导航路径 |

### 5.9 copy

| 维度 | 设计 |
|---|---|
| trigger | CopyBlock 复制 / 永久链接复制 |
| required fields | `copy_type`（code-block/permalink/other） |
| **禁止** | **禁止记录用户复制的具体文本内容** |
| privacy | 只记录 copy_type，不记录内容 |

---

## 6. Page Taxonomy

### 6.1 page_type schema

**[PROPOSED] 11 种 page_type，基于真实路由（Inventory §1.7）：**

| page_type | URL Pattern | 说明 |
|---|---|---|
| `home` | `/` | 首页 |
| `model_catalog` | `/changes`（含 `?modelId=` 筛选） | 变化浏览（含模型筛选） |
| `model_detail` | `/model/<modelId>/` | 模型详情 |
| `item_detail` | `/item/<id>/` | 条目详情 |
| `evidence_detail` | `/evidence/<id>/` | 证据详情 |
| `changes` | `/changes`（无筛选） | 变化浏览 |
| `prices` | `/pricing` | 价格台账 |
| `leaderboard` | `/leaderboards` | 榜单 |
| `weekly` | `/weekly/`、`/weekly/<id>/`、`/daily/<week>/` | 周报与归档 |
| `agent` | `/agent` | 接入页 |
| `other` | `/about`、`/method`、`/changelog`、`/sources` | 其他静态页 |

### 6.2 Model Detail 字段可获得性

任务书要求评估 model detail 页能否稳定获得 `model_id` / `developer_id` / `platform_id` / `upstream_model_id`。

**当前状态（基于 T07-5 inventory 实际代码）：**

| 字段 | 状态 | 证据 |
|---|---|---|
| `model_id` | **available** | public catalog `model-identities.json` 已有 `modelId`（如 `alibaba:qwen3-coder-plus`）；`site/src/pages/model/[modelId].astro` 从 catalog 取 |
| `family_id` | **available** | public catalog 已有 `familyId`（如 `alibaba:qwen-coder`） |
| `family_name` | **available** | public catalog 已有 `familyName` |
| `model_name` | **available** | public catalog 已有 `modelName` |
| `provider_id` | **derivable** | `modelId` 前缀即 `providerId`（如 `alibaba:qwen3-coder-plus` → `alibaba`）；`[modelId].astro` 已推导 |
| `developer_id` | **not_available** | T07-5 新实体，未进入 public schema；当前只有 candidate mapping（8 个 candidate developer），未 verified |
| `platform_id` | **not_available** | T07-5 新实体，未进入 public schema；`providerId` 是 legacy namespace，不等价于 Platform |
| `upstream_model_id` | **not_available** | T07-5 新实体，未进入 public schema；当前只有 107 个 candidate upstream，未 verified |

**结论：**

- Analytics Page Taxonomy 当前只能使用 `model_id` / `family_id` / `provider_id`（derivable）
- `developer_id` / `platform_id` / `upstream_model_id` **不可可靠获得**，待 T07-5 实现
- **禁止为了 Analytics 修改 T07-5 ontology**（任务书 §11 明确要求）

**T07-5 实现后的演进 [PROPOSED]：**
- T07-5 进入 public schema 后，Analytics Event Schema 可扩展 `developer_id` / `platform_id` / `upstream_model_id` 字段
- 这是 Analytics 的演进方向，不是 T08-0 的实现内容

---

## 7. Traffic Attribution

### 7.1 统一分类

**[PROPOSED] 11 个 source channel：**

| category | subcategory | 说明 |
|---|---|---|
| `direct` | - | 无 referrer 或 referrer 为空 |
| `search` | `google` / `bing` / `baidu` / `duckduckgo` / `yahoo` / `other_search` | 搜索引擎 |
| `ai` | `chatgpt` / `perplexity` / `claude` / `gemini` / `copilot` / `grok` / `other_ai` | AI 产品 |
| `github` | - | GitHub |
| `social` | - | 社交媒体（twitter/x、weibo、xiaohongshu 等） |
| `referral` | - | 其他外站推荐 |
| `internal` | - | 本站内导航（referrer 为 daily.maas.click） |
| `unknown` | - | 无法分类 |

### 7.2 referrer 可靠性分析

**当前环境（基于 Inventory §4）：**

| 维度 | 浏览器 Analytics 能获得 | 服务器 Log 能获得 |
|---|---|---|
| Referrer | `document.referrer`（由浏览器提供） | nginx `$http_referer`（默认 combined 格式记录） |
| CDN/Nginx 改变 referrer | **不改变**（无 CDN 前置，nginx 不改写 Referer header） | 同左 |
| 可靠性 | 依赖浏览器 `Referrer-Policy`（当前未设置，默认 `strict-origin-when-cross-origin`） | 依赖 nginx log_format（当前服务器默认） |

**关键发现：**
- 无 CDN 前置，nginx 直接面对公网，**referrer 不会被 CDN 改写**
- 当前未设置 `Referrer-Policy` header（Inventory §6.6），浏览器默认 `strict-origin-when-cross-origin` 会向同源发送完整 URL、向跨源只发 origin
- **AI 产品（ChatGPT/Perplexity/Claude/Gemini）的 referrer 可靠性取决于其前端实现**，需在实际数据中验证

### 7.3 Attribution Precedence

**[PROPOSED]：**

```
UTM 参数
  >
known referrer（匹配 AI/search/social/github/referral registry）
  >
direct（无 referrer 或 referrer 为空）
```

**理由：**
- UTM 参数是最明确的来源标识（用户/营销主动标记），优先级最高
- known referrer 是次明确来源（通过 referrer 匹配 registry），优先级次之
- direct 是兜底（无任何来源信号）

**AI referrer registry [PROPOSED]（需实际数据验证）：**

| AI 产品 | referrer host 候选 | 状态 |
|---|---|---|
| ChatGPT | `chatgpt.com` | 需验证 |
| Perplexity | `perplexity.ai` | 需验证 |
| Claude | `claude.ai` | 需验证 |
| Gemini | `gemini.google.com` | 需验证 |
| Copilot | `copilot.microsoft.com` | 需验证 |
| Grok | `grok.com` / `x.com/i/grok` | 需验证 |

**注意：** 这些 referrer host 是候选，**必须在实际流量数据中验证后才进入生产 registry**。禁止根据网上博客直接建立生产规则（任务书 §15 原则）。

---

## 8. SEO Integration Architecture

### 8.1 统一 schema

**[PROPOSED]：**

```json
{
  "date": "2026-09-29",
  "engine": "google" | "bing",
  "query": "maas daily",
  "page": "/model/openai:gpt-5.6-luna/",
  "impressions": 120,
  "clicks": 5,
  "ctr": 0.0417,
  "position": 12.3
}
```

### 8.2 数据获取 API

| 引擎 | API | 凭证 |
|---|---|---|
| Google Search Console | Google Search Console API v1（`searchanalytics.query`） | OAuth 2.0 refresh token 或 service account JSON |
| Bing Webmaster Tools | Bing Webmaster API（`GetQueryStats`） | API key |

### 8.3 凭证管理

**[PROPOSED]：**
- GSC：service account JSON 存 GitHub Secret（`GSC_SERVICE_ACCOUNT_JSON`），workflow 内注入
- Bing：API key 存 GitHub Secret（`BING_WMT_API_KEY`），workflow 内注入
- 凭证不落盘仓库、不落日志

### 8.4 执行位置：GitHub Actions vs production server

**[PROPOSED] GitHub Actions 执行。**

理由：
1. GSC/Bing API 是外部 OAuth/API key 认证，GitHub Actions runner 天然适合（secrets 注入）
2. production server 当前不持有任何外部 OAuth 凭证，引入会增加攻击面
3. GitHub Actions 已有 Python/Node 环境，与现有 workflow 一致
4. 数据量小（日级聚合），无需 production server 算力

### 8.5 同步频率

**[PROPOSED] 每日同步，附属于 daily-update workflow。**

理由：
- GSC 数据有 ~2 天延迟（见 §8.6），日同步可保证数据新鲜度
- Bing 数据延迟较小，日同步即可

### 8.6 Search Console 数据延迟处理

**GSC 数据延迟约 2 天**（今日只能查到 2 天前数据）。

**[PROPOSED] 处理方式：**
- 每日同步查 `data_through = today - 2` 的数据
- 数据缺失日期标记为 `pending`，次日补齐
- aggregate 计算时跳过 `pending` 日期，不补零

### 8.7 raw 数据保存

**[PROPOSED] 保存 raw 数据。**

- raw：每日每引擎的完整 query/page/impressions/clicks/ctr/position，存 `data/analytics/seo/raw/<engine>/<date>.json`
- aggregate：按日/周/月聚合，存 `data/analytics/seo/aggregate/`
- raw 数据保留 90 天，之后只保留 aggregate

### 8.8 aggregate 进入 Analytics Dataset

见 §10 Unified Analytics Data Layer。

---

## 9. GEO Crawler Architecture

### 9.1 数据流

**[PROPOSED]：**

```
独立 analytics log_format（nginx）
       ↓
Crawler Parser（Python，按 AI Crawler Registry 匹配 UA）
       ↓
Daily Aggregate（按 crawler_id + page 聚合）
       ↓
Analytics Dataset（data/analytics/geo/）
```

### 9.2 为什么不直接建立在现有 Nginx access log 上

**不能直接建立**（见 Inventory §4.9），因为：
1. access_log 配置不在仓库内，不可审计、不可版本化
2. log_format 不可控，依赖服务器默认
3. 无日志轮转/retention 声明
4. 无日志导出管道

### 9.3 [PROPOSED] 独立 analytics log_format

**在仓库内声明 analytics 专用 nginx 配置**（T08-5 实现，本任务不修改 Nginx）：

```nginx
log_format analytics '$remote_addr - $remote_user [$time_local] '
                     '"$request" $status $body_bytes_sent '
                     '"$http_referer" "$http_user_agent" '
                     'request_id="$http_x_request_id"';
```

- 记录字段：remote IP、time、request（method+path+protocol）、status、bytes、referer、user-agent、request_id
- 输出到独立日志文件（如 `/var/log/nginx/maasweekly-analytics.log`）
- 独立 logrotate 配置（保留 90 天）

**注意：此为 T08-5 proposed 设计，T08-0 不修改 Nginx。**

### 9.4 AI Crawler Registry 数据结构

**[PROPOSED]：**

| 字段 | 说明 |
|---|---|
| `crawler_id` | 稳定 ID（如 `gptbot`、`claudebot`、`perplexitybot`） |
| `name` | 显示名（如 `GPTBot`、`ClaudeBot`、`PerplexityBot`） |
| `user_agent_pattern` | UA 匹配模式（正则或子串） |
| `vendor` | 厂商（OpenAI、Anthropic、Perplexity） |
| `official_evidence` | 官方文档 URL（必须） |
| `status` | `active` / `deprecated` |

### 9.5 User-Agent pattern 需要官方 evidence

**严格遵守任务书 §15 原则：User-Agent pattern 需要官方 evidence，禁止根据网上博客直接建立生产规则。**

**[PROPOSED] 已知 AI Crawler 候选（需官方 evidence 验证）：**

| crawler_id | UA pattern 候选 | 官方 evidence 来源（待验证） |
|---|---|---|
| `gptbot` | `GPTBot` | OpenAI 官方文档 |
| `claudebot` | `ClaudeBot` | Anthropic 官方文档 |
| `perplexitybot` | `PerplexityBot` | Perplexity 官方文档 |
| `google-extended` | `Google-Extended` | Google 官方文档 |
| `ccbot` | `CCBot` | Common Crawl 官方文档 |
| `bingbot` | `bingbot` | Bing 官方文档 |

**T08-5 实现时必须为每个 pattern 提供官方文档 URL 作为 evidence。**

### 9.6 本任务只设计数据结构

T08-0 不实现 crawler parser、不创建 registry 文件、不修改 Nginx。

---

## 10. Unified Analytics Data Layer

### 10.1 是否沿用现有 raw → normalized → aggregate → manifest 模式

**[PROPOSED] 沿用，独立子目录 `data/analytics/`。**

```
data/analytics/
  traffic/        ← Umami 拉取的聚合数据
    raw/
    aggregate/
  seo/             ← GSC/Bing 同步数据
    raw/
    aggregate/
  geo/             ← AI Crawler 解析数据
    raw/
    aggregate/
  manifest.json    ← Analytics manifest（独立于 data/public/v1/manifest.json）
```

### 10.2 数据是否进入 release

**[PROPOSED] 进入 release，但独立版本管理。**

- Analytics 数据进入 release 的 content scope（`data/analytics/` 随 release 发布）
- Analytics manifest 独立于 `data/public/v1/manifest.json`，避免 Analytics 数据变化影响核心 datasetVersion
- Analytics manifest 有自己的 `analyticsVersion` / `generatedAt` / `dataThrough`

**理由：**
- Analytics 数据需要随 Dashboard 一起发布（Dashboard 静态生成读 Analytics 数据）
- 独立版本管理避免 Analytics 数据变化频繁触发核心 datasetVersion 变化

### 10.3 历史数据保存

**[PROPOSED]：**
- raw：保留 90 天（traffic/seo/geo 各自）
- aggregate：永久保留（日/周/月粒度）
- 超过 90 天的 raw 数据在 release retention 时清理，aggregate 保留

### 10.4 aggregate 粒度

**[PROPOSED]：**
- 日级：`YYYY-MM-DD`（每日一条聚合）
- 周级：ISO 周（每周一条聚合）
- 月级：`YYYY-MM`（每月一条聚合）

### 10.5 7D / 30D / 90D 计算

**[PROPOSED]：**
- 滚动窗口计算，基于日级 aggregate
- 7D = 最近 7 个自然日的日级聚合求和
- 30D = 最近 30 个自然日
- 90D = 最近 90 个自然日
- 数据缺失日不补零，标注 `days_available` / `days_expected`

### 10.6 datasetVersion / generatedAt / dataThrough

**[PROPOSED] Analytics 独立 manifest：**

```json
{
  "schemaVersion": "1.0",
  "analyticsVersion": "an_<sha256>",
  "generatedAt": "2026-09-30T00:53:38+00:00",
  "dataThrough": "2026-09-29",
  "sources": {
    "traffic": { "available": true, "dataThrough": "2026-09-29" },
    "seo": { "available": true, "dataThrough": "2026-09-27" },
    "geo": { "available": true, "dataThrough": "2026-09-29" }
  }
}
```

- `analyticsVersion` = `an_` + sha256(canonical_json(payload))（类似 datasetVersion 算法）
- `generatedAt` 是墙钟时间，不进 `analyticsVersion`
- `dataThrough` 是各 source 的最小 dataThrough

### 10.7 数据缺失表达

**[PROPOSED]：**
- `sources.<name>.available: false` 表示该 source 同步失败
- aggregate 中缺失日标注 `days_available` / `days_expected`
- Dashboard 显示 "数据缺失" 而非零

### 10.8 某个 source 同步失败是否阻断 daily-update

**[PROPOSED] 不阻断。**

- Analytics 某个 source（如 GSC）同步失败 → `sources.<name>.available: false`，其他 source 正常
- **Analytics 不阻断 daily-update 的核心数据提交与发布**（见 §12 Failure Strategy）

---

## 11. Dashboard Architecture

### 11.1 路由

**[PROPOSED] `/admin/analytics`**

### 11.2 是否公开 / authentication / static generate / API / release

| 维度 | 设计 |
|---|---|
| 是否公开 | **不公开** |
| authentication | **需要**（当前 API 纯匿名只读，无鉴权；需新增 authentication 机制） |
| 是否 static generate | **是**（纯 SSG，随 release 发布） |
| 是否通过 API 获取 | **是**（静态页 + 客户端 fetch `/api/v1/analytics`） |
| 是否进入现有 release | **是**（`/admin/analytics` 页面进入 `site/dist/`） |
| 是否可能泄露敏感数据 | **可能**（PV/UV/traffic source 属于商业敏感数据） |

### 11.3 Authentication [PROPOSED]

当前仓库无鉴权体系（Inventory §1.11）。**[PROPOSED] 两种候选方案，T08-7 决定：**

**方案 A：nginx basic auth**
- `/admin/` 路径由 nginx 加 `auth_basic`，htpasswd 文件在服务器侧
- 优点：简单，不改 agent-api
- 缺点：basic auth 无 cookie 仍是浏览器原生弹窗体验差

**方案 B：agent-api 新增 admin 路由 + API key**
- `/api/v1/analytics` 需 API key（header `X-Admin-Key`）
- API key 存服务器 `shared/agent.env`
- 优点：与现有 agent-api 一致
- 缺点：需改 agent-api

**推荐方案 A**（nginx basic auth），因为更简单且不改动 agent-api。

### 11.4 第一版计划

**[PROPOSED]：**

**Overview**
- PV / UV / Sessions
- New / Returning
- Traffic Trend

**Traffic Sources**
- 按渠道（direct/search/ai/github/social/referral）
- Top Landing Pages

**SEO**
- Search Impressions
- Clicks
- CTR
- Position
- Organic Landing Sessions（从 search channel landing 推导）

**GEO**
- AI Crawl（按 crawler_id）
- AI Referral（从 ai channel 推导）
- Top AI Landing Pages
- Top Crawled Pages

### 11.5 时间范围

**[PROPOSED] 7D / 30D / 90D**（见 §10.5）

### 11.6 来源筛选

**[PROPOSED] All / Search / AI / Direct / Referral**

---

## 12. Failure / Degradation Strategy

### 12.1 基本原则

**Analytics 不应该降低 maasweekly 核心数据服务的可用性。**

### 12.2 各失败场景处理

| 失败场景 | 是否阻断 daily-update | 是否阻断 production release | 是否保留 last-known-good | 是否显示 stale |
|---|---|---|---|---|
| Analytics provider（Umami）unavailable | 否 | 否 | 是（保留上次聚合） | 是（Dashboard 标注数据截止日期） |
| GSC sync failed | 否 | 否 | 是 | 是 |
| Bing sync failed | 否 | 否 | 是 | 是 |
| Crawler parser failed | 否 | 否 | 是 | 是 |
| Analytics aggregate failed | 否 | 否 | 是 | 是 |

### 12.3 降级策略

**[PROPOSED]：**
- Analytics 任何 source 失败 → `sources.<name>.available: false`
- Dashboard 显示 `available: false` 的 source 标注"数据暂时不可用（使用上次成功同步数据）"
- **不影响**核心数据提交（`data/` 抓取与归档）、核心 release（`data/public/v1/`）、核心 API（agent-api）

### 12.4 daily-update 中的 Analytics 步骤位置

**[PROPOSED] Analytics 步骤放在 daily-update workflow 的核心数据提交之后、部署之前，且 `continue-on-error: true`：**

```
核心数据抓取与归档
  ↓
核心数据提交（git commit data/）
  ↓
Analytics 同步（continue-on-error）  ← 失败不阻断
  ↓
build-release（含 Analytics 数据，若失败则用 last-known-good）
  ↓
deploy
```

**注意：** Analytics 同步失败时，build-release 使用仓库内已有的 last-known-good Analytics 数据构建 release，不阻断发布。

---

## 13. Security / Privacy

### 13.1 原则

- 默认不采集 PII
- 不记录用户输入内容
- 不记录完整 IP 到 Analytics Dataset
- Secret 不进入仓库

### 13.2 Cookie-less Analytics 可行性

**可行**（见 Inventory §6.10）。Umami 默认 cookie-less，与现有零 cookie 架构无冲突。

### 13.3 IP 处理

**[PROPOSED]：**
- Umami 默认截断 IP（不记录完整 IP）
- nginx analytics log_format 记录 `$remote_addr`（完整 IP），但 Crawler Parser 只提取 UA + Path，**不将完整 IP 写入 Analytics Dataset**
- Analytics Dataset 中无 IP 字段

### 13.4 robots.txt [PROPOSED]

当前无 robots.txt（Inventory §6.5）。**[PROPOSED] T08-4 创建 `site/public/robots.txt`：**
- 允许搜索引擎爬取
- 可选：disallow `/admin/`

### 13.5 security headers [PROPOSED]

当前无 security headers（Inventory §6.6）。**[PROPOSED] T08-4 在 nginx 配置中添加：**
- `Referrer-Policy: strict-origin-when-cross-origin`（明确 referrer 策略）
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`

**注意：T08-0 不修改 Nginx，T08-4 实现时需把这些 header 纳入仓库可审计的 nginx 配置。**

---

## 14. Implementation Plan

### 14.1 原任务拆分评估

任务书原拆分（T08-1 至 T08-8）总体合理，但调查后发现两处需调整：

**调整 1：T08-1 应先建 Analytics 基础设施（Umami 部署 + script 插入）再建事件**

原 T08-1 "Traffic Base" 与 T08-2 "Events" 边界模糊。建议 T08-1 明确为"Umami 部署 + script 插入 + page_view 基础采集"，T08-2 为"自定义事件（content_view/scroll_depth/click/copy）"。

**调整 2：T08-4 SEO Integration 应包含 robots.txt + security headers**

当前无 robots.txt 和 security headers，这些是 SEO 与隐私基础，应在 T08-4 一并处理。

### 14.2 任务细化

#### T08-1: Traffic Base

| 维度 | 内容 |
|---|---|
| **Goal** | 部署 Self-hosted Umami，插入采集 script，实现 page_view 基础采集 |
| **Scope** | Umami 服务部署（systemd + nginx 反向代理）、Umami 数据库初始化、`Layout.astro` `<head>` 插入 Umami script、page_view 事件验证 |
| **Expected Files** | `ops/nginx/` 新增 Umami 反向代理配置、`ops/maas-umami@.service`（或类似）、`site/src/layouts/Layout.astro`（修改）、`site/src/config/public-access.ts`（新增 Umami 配置） |
| **Tests** | Umami 服务健康检查、page_view 事件上报验证、cookie-less 验证、不破坏现有 `test_no_sudo_no_telemetry` |
| **Acceptance Criteria** | 全站 17 路由 page_view 上报到 Umami、零 cookie、`test_no_sudo_no_telemetry` 通过 |
| **Dependencies** | 无（T08-0 已完成） |
| **Risks** | Umami 服务可用性影响采集（但不影响站点本身）；需服务器运维 |

#### T08-2: Events

| 维度 | 内容 |
|---|---|
| **Goal** | 实现自定义事件：content_view / scroll_depth / model_click / change_click / outbound_click / copy |
| **Scope** | Umami custom event 采集脚本、事件 trigger 实现、deduplication 逻辑 |
| **Expected Files** | `site/src/scripts/analytics-events.ts`（新增）、`site/src/layouts/Layout.astro`（引入事件脚本）、各页面修改（添加事件 trigger） |
| **Tests** | 每个事件上报验证、scroll_depth 每 threshold 最多一次验证、copy 不记录内容验证 |
| **Acceptance Criteria** | 8 个事件全部上报正确、scroll_depth 去重正确、copy 不记录内容 |
| **Dependencies** | T08-1 |
| **Risks** | 事件过多影响性能（需 throttle/debounce） |

#### T08-3: Attribution

| 维度 | 内容 |
|---|---|
| **Goal** | 实现 traffic attribution 分类（direct/search/ai/github/social/referral/internal/unknown） |
| **Scope** | referrer 解析、UTM 解析、AI/search/social referrer registry、attribution precedence 逻辑 |
| **Expected Files** | `site/src/scripts/analytics-attribution.ts`（新增）、AI referrer registry 数据文件 |
| **Tests** | 各 channel 分类验证、UTM precedence 验证、AI referrer 匹配验证 |
| **Acceptance Criteria** | 11 个 source channel 分类正确、UTM > referrer > direct precedence 正确 |
| **Dependencies** | T08-1 |
| **Risks** | AI referrer 需实际数据验证后才进生产 registry |

#### T08-4: SEO Integration

| 维度 | 内容 |
|---|---|
| **Goal** | 接入 Google Search Console + Bing Webmaster Tools；创建 robots.txt；添加 security headers |
| **Scope** | GSC/Bing API 同步脚本、GitHub Secrets 配置、SEO raw/aggregate 数据结构、robots.txt、security headers |
| **Expected Files** | `pipeline/scripts/sync-seo.py`（新增）、`site/public/robots.txt`（新增）、nginx security headers 配置、`data/analytics/seo/` 目录 |
| **Tests** | GSC/Bing API 同步验证、SEO schema validation、robots.txt 验证 |
| **Acceptance Criteria** | GSC/Bing 数据每日同步、robots.txt 公开可达、security headers 生效 |
| **Dependencies** | 无（可与 T08-1 并行） |
| **Risks** | GSC 数据延迟 2 天；GSC OAuth 凭证管理；需申请 Google/Bing 账号（T08-0 不申请） |

#### T08-5: GEO Crawler

| 维度 | 内容 |
|---|---|
| **Goal** | 实现 AI Crawler Observability |
| **Scope** | analytics 专用 nginx log_format、AI Crawler Registry、Crawler Parser、Daily Aggregate |
| **Expected Files** | `ops/nginx/` analytics log_format 配置、`pipeline/scripts/parse-crawlers.py`（新增）、`data/analytics/geo/` 目录、AI Crawler Registry 数据文件 |
| **Tests** | Crawler UA 匹配验证、每日聚合验证、registry 每条有 official evidence 验证 |
| **Acceptance Criteria** | AI Crawler crawl 数据每日聚合、registry 每条 pattern 有官方 evidence |
| **Dependencies** | 无（可与 T08-1 并行） |
| **Risks** | 需修改 nginx 配置（analytics log_format）；日志管道需服务器运维；AI Crawler UA 需官方 evidence |

#### T08-6: Analytics Data Layer

| 维度 | 内容 |
|---|---|
| **Goal** | 构建 Unified Analytics Dataset（traffic + seo + geo） |
| **Scope** | `data/analytics/` 目录结构、Analytics manifest、aggregate 计算（7D/30D/90D）、release 集成 |
| **Expected Files** | `pipeline/scripts/build-analytics-dataset.py`（新增）、`schemas/analytics-v1/`（新增 schema）、`data/analytics/manifest.json` |
| **Tests** | Analytics manifest validation、aggregate 计算验证、release 集成验证 |
| **Acceptance Criteria** | Analytics 数据进入 release、独立版本管理、7D/30D/90D aggregate 正确 |
| **Dependencies** | T08-1, T08-4, T08-5 |
| **Risks** | Analytics 数据变化频繁影响 release（用独立 analyticsVersion 缓解） |

#### T08-7: Analytics Dashboard

| 维度 | 内容 |
|---|---|
| **Goal** | 实现 `/admin/analytics` Dashboard |
| **Scope** | Dashboard 静态页、API 端点（`/api/v1/analytics`）、authentication、Overview/Traffic/SEO/GEO 四区 |
| **Expected Files** | `site/src/pages/admin/analytics.astro`（新增）、`services/agent-api/src/`（新增 analytics 端点）、nginx auth 配置 |
| **Tests** | Dashboard 渲染验证、API 响应验证、authentication 验证 |
| **Acceptance Criteria** | 四区全部渲染、7D/30D/90D 切换、来源筛选、authentication 生效 |
| **Dependencies** | T08-6 |
| **Risks** | 需新增 authentication 机制（当前无鉴权）；Dashboard 可能泄露敏感数据（需 auth 保护） |

#### T08-8: Production Verification

| 维度 | 内容 |
|---|---|
| **Goal** | 生产环境全链路验收 |
| **Scope** | Umami 采集验证、事件验证、attribution 验证、SEO 同步验证、GEO crawler 验证、Dashboard 验证、failure/degradation 验证 |
| **Expected Files** | 验收文档、验收脚本 |
| **Tests** | 端到端验收 |
| **Acceptance Criteria** | 所有 T08-1 至 T08-7 的 acceptance criteria 在生产环境全部通过 |
| **Dependencies** | T08-1 至 T08-7 全部完成 |
| **Risks** | 生产环境数据需积累才能验收（7D/30D/90D 需时间） |

### 14.3 后续

- **T08-9 GEO Citation Monitor**：在 T08-5 GEO Crawler 基础上，监控 AI 产品对 maasweekly 内容的引用（citation）。依赖 T08-5 与 T08-6 完成。

---

## 15. Open Questions

1. **Umami 部署位置**：Umami 服务部署在 maasweekly 同一服务器（47.237.135.97）还是独立服务器？同服务器可复用 nginx/systemd，但增加资源占用。**建议同服务器**，待 owner 决定。

2. **Umami 数据库选择**：PostgreSQL 还是 MySQL？maasweekly 当前无数据库（agent-api 零运行时依赖、数据全 JSON 文件）。**建议 PostgreSQL**（Umami 推荐），待 owner 决定。

3. **`/admin/analytics` authentication 方案**：nginx basic auth（方案 A）还是 agent-api API key（方案 B）？**建议方案 A**，待 owner 决定。

4. **GSC/Bing 账号申请**：T08-4 需要申请 Google Search Console 和 Bing Webmaster Tools 账号并验证站点所有权。这是 owner 必须参与的步骤（T08-0 不申请）。

5. **AI referrer registry 验证**：AI 产品（ChatGPT/Perplexity/Claude/Gemini）的 referrer host 是否可靠？需在实际流量数据中验证后才能确定生产 registry。

6. **Analytics 数据是否进入 `data/public/v1/`**：当前建议独立 `data/analytics/`（§10.1），但是否部分聚合数据（如 Top Landing Pages）进入 `data/public/v1/` 供 API 公开查询？**建议不公开**（属商业敏感数据），待 owner 决定。

7. **Dashboard 是否需要实时数据**：当前建议静态生成 + API 读取（§11.2），但若需实时（如 5 分钟刷新），需评估 Umami API 性能与缓存策略。

8. **security headers 与 robots.txt 归属**：T08-4 SEO Integration 是否是处理 robots.txt 和 security headers 的正确位置？还是应该独立为 T08-4.5 或归入 T08-1？**建议归入 T08-4**，待 owner 决定。

---

## 16. Validation

本文档提交前已执行以下验证：

1. **文档引用的所有关键代码路径真实存在**：见 Inventory §7 Relevant Code Paths，所有路径均经四路调查 agent 实际读取确认
2. **文档描述与当前 main 分支代码一致**：基于 2026-09-30 main 分支（commit `c98264481`）
3. **所有当前能力判断都有代码证据**：Inventory 每节均有代码路径 + 行号
4. **所有 proposed architecture 明确标记为 [PROPOSED]**：见各节
5. **不将 proposed design 描述成 existing behavior**：Inventory 记录 existing，Architecture 记录 proposed，两者分离
6. **git diff 确认只有 T08-0 Scope 内文件**：见提交
7. **仓库现有适用测试保持通过**：T08-0 不修改代码，不影响现有测试

---

## 关键设计决策

| 决策 | 理由 |
|---|---|
| Self-hosted Umami | cookie-less、数据自有、免费、Custom Event 支持、Node.js 技术栈契合 |
| Analytics 产物进入现有 release | 统一发布/回滚/权限，不引入第二套部署链 |
| Analytics 独立 analyticsVersion | 避免 Analytics 数据变化频繁影响核心 datasetVersion |
| 不依赖现有 nginx access log | access_log 配置不在仓库内、不可审计；建独立 analytics log_format |
| Page Taxonomy 不依赖 T07-5 新实体 | developer_id/platform_id/upstream_model_id 未进入 public schema；禁止为 Analytics 修改 ontology |
| Analytics 失败不阻断核心服务 | Analytics 是观测层，不应降低核心数据服务可用性 |
| `/admin/analytics` 需 authentication | 当前无鉴权，Dashboard 含商业敏感数据，必须保护 |
