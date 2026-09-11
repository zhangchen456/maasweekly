# AIHOT（aihot.news）产品与技术研究

日期：2026-09-11。方法：站点页面逐页抓取 + 公开 API 实测探测（items / snapshot / changes / hot-topics / llms.txt），响应头与游标协议均为实测确认，非猜测。

## 一、产品定位

AI 行业动态聚合站：数百信源（X/微信公众号/RSS/官方博客）自动抓取 → LLM 生成摘要、打分精选 → 每天 08:00（北京时间）发布精编日报。免费使用，商业用途需书面授权。

与本项目（MaaS 平台变化追踪）是同构产品：同样的「采集 → LLM 加工 → 分发」管线，差异在垂直领域（全 AI 圈 vs MaaS 平台）与分发策略（匿名免费 vs 账号凭证体系）。

## 二、功能清单

### 内容层

| 功能 | 说明 | 本项目现状 |
| --- | --- | --- |
| 精选流 | LLM 打分筛选，每条附推荐理由（reason）与 AI 评分 | 有 diff 无打分；llm-digest 只做每日要点 |
| 全量信息流 | 公开池（不含未审/低相关/重复条目），逐条带 AI 评分 | 无此层 |
| 热点榜 + 事件页（story） | Top10 热点；每个热点聚合多信源报道时间线 + 随演化更新的 AI 综述 + 关联事件 | 无——事件是平的，没有多来源聚合 |
| 主题地图（topics） | AI 自动打标签聚合（公司/模型系/技术方向），点入看该主题全部动态 | 无（按 provider 平铺） |
| AI 日报 | 每天 08:00 精编，保留 30 期，可按日期取 | 有周报，无日报 |
| 大模型排行榜 | 综合多项公开评测的 MODEL INDEX，按分类看所长 | 有（LMArena 等），弱于它 |
| 收藏 | 本机收藏（localStorage），明确不跨设备同步 | 无 |

### 分发层

| 通道 | 实现方式 | 关键设计 |
| --- | --- | --- |
| Agent Skill | install.sh 一键安装；多平台目录约定（`~/.agents/skills/` 共享，Claude Code 软链不复制）；含 SKILL.md、按需 references、元数据、许可证、校验清单；版本化管理（1.6.0） | 安装器原子替换、不猜平台、发现旧副本停下；支持 `--migrate-legacy` 清理重复副本 |
| 远程 MCP | Streamable HTTP（`https://aihot.news/api/mcp`），5 个只读工具：get_latest / search / get_hot_topics / get_story / get_daily | 匿名只读、无需 token |
| RSS（六轨） | 精选摘要 / 精选全文 / 全量 / 日报 / 分类 ×5（ai-models、ai-products、industry、paper、tip） | 全文是白名单：仅明确允许再分发的来源内联 content:encoded；支持 ETag/304；建议 30 分钟轮询 |
| REST API v1 | items / hot-topics / stories/{id} / dailies / selected/snapshot / selected/changes | 匿名 GET；OpenAPI 3.1；llms.txt 供 Agent 发现 |
| 微信群推送 | 每天最精选几条自动推群 | — |

### 前端

Next.js App Router（SSR），CSS 变量主题系统（深浅色），页面数据随 HTML 下发（约 350KB/页），SEO 友好，京ICP 备案。

## 三、技术实现要点（实测确认）

### 1. 同步协议：无状态自编码游标

```
GET /api/v1/selected/snapshot        → 首次完整快照 + cursor
GET /api/v1/selected/changes?cursor= → 只返回新增/修改/撤选
```

实测 cursor 形态：`v1s.<base64>`，解码后为 `{k: key, v: version, w: watermark, f: fields}`——**watermark 是单调整数**（实测值 58251），编码在 cursor 内，服务端不存任何游标状态。

- 无 cursor 调 changes → `409 snapshot_required`，错误体 detail 直接给出恢复动作（"fetch snapshot first"）
- 响应含 `schemaVersion` / `fields`（字段集协商）/ `asOf`（快照时间点）/ `hasMore` / `nextPage`
- 变更类型：新增 / 修改 / 撤选——与本项目 create/revise/withdraw 语义相同

**对本项目的意义**：本项目三轮验收中 R01 反复暴露的游标问题（读取消耗、交接漏数、保留期清理），根因是服务端有状态游标；AIHOT 的自编码 cursor 天然规避——无状态、天然幂等、无需清理逻辑。

### 2. 缓存与成本控制：共享缓存架构

实测响应头：

```
etag: W/"v1-items-<内容哈希>"
x-nginx-cache: MISS
access-control-max-age: 86400
```

匿名只读 + nginx/CDN 共享缓存 → 极低边际成本。这是它能免费开放且不设 Key 的经济基础。

**刻意的取舍**：不提供 SSE / Webhook / 流式订阅。理由（原话转述）：响应走共享缓存，TTL 已决定任何客户端能有多新；条件轮询（ETag/304）拿到的新鲜度相同，还不用维持长连接、不受发布影响。

### 3. API 生命周期与合规响应头

```
x-aihot-release: <commit hash>          # 版本可观测
x-aihot-policy-version: 1.0
x-aihot-commercial-use: written-authorization-required
x-aihot-contact: <邮箱>
access-control-expose-headers: ETag, Last-Modified, Retry-After,
    X-Request-Id, Deprecation, Sunset, Link, ...
```

- **Sunset / Deprecation 头**实现旧接口下线：`/api/public/*` 宣布 2026-12-31 停服，新接入不受影响——标准 API 生命周期管理
- 商用授权边界通过响应头 + terms 页双通道声明

### 4. 内容边界处理

- 全量 feed 明确披露排除规则：「不含原公众号爆文榜来源、未审内容、低相关条目和已合并重复条目」——公开池 ≠ 全库
- 全文 RSS 白名单制：仅明确允许再分发的来源内联正文，其余一律摘要 + 阅读入口
- 对来源方提供更正/下架/调整展示的通道

## 四、复用与借鉴建议

### 直接采纳（与本项目三轮验收教训吻合）

| # | 建议 | 理由 |
| --- | --- | --- |
| 1 | **无状态自编码游标**（cursor 内嵌 watermark）重构同步层 | 一次解决 R01 全系列问题（游标消耗、交接漏数、保留期）；服务端零状态 |
| 2 | **错误体统一带恢复指引**（409 snapshot_required + "fetch snapshot first"） | 本项目已有 410/409 语义，但应统一到每个错误回答「下一步去哪」 |
| 3 | **无 SSE/Webhook，纯条件轮询 + 共享缓存** | ETag + s-maxage 让 CDN 扛流量；砍掉长连接复杂度；适合本项目静态站 + rsync 架构 |
| 4 | **llms.txt + OpenAPI 3.1 + Agent Skill（含 install.sh）三件套** | 机器入口成本极低、Agent 生态收益高；本项目有 SKILL.md 但无安装器与 llms.txt |
| 5 | **Sunset/Deprecation 响应头** | 为接口演进预埋下线机制，替代临时通知 |

### 值得借鉴的功能（按产品价值排序）

| # | 功能 | 对本项目的价值 |
| --- | --- | --- |
| 6 | Story（事件聚合页：多信源时间线 + AI 综述持续更新） | 从「信源 diff」升级到「事件报道」的关键形态；中期 T4 决策价值的基础 |
| 7 | RSS 六轨分发 | 本项目一条都没有；纯静态站加 RSS 零成本高回报（`@astrojs/rss` 本在 HANDOFF 演进方向） |
| 8 | 精选打分 + 推荐理由（score + reason） | 让「AI 筛选」透明化；解决 diff 噪声的另一角度——给信号加权，而非只降噪 |
| 9 | 主题标签地图 | 比按 provider 平铺更贴近「追某个模型系」的真实用法 |
| 10 | 白名单全文（逐来源决定发布范围） | 与 R07 教训一致：发布范围是逐来源决定的，不是全库一刀切 |

### 不跟进的

- **匿名无 Key API**：其商业模式（免费 + 商用书面授权）与本项目的账号/凭证验收基线是两种取向，不动
- **localStorage 收藏**：明确不跨设备同步，与本项目「不做关注系统」约束一致

## 五、一个核心判断

AIHOT 的公开 API 协议（snapshot/changes、自编码 watermark 游标、错误恢复语义、缓存策略）几乎就是把本项目三轮验收中被反复修复的问题一次性做对的版本。**下一轮重构同步层时，把它当作规格参考直接对齐，比再发明一轮协议划算。**
