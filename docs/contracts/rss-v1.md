# RSS v1 合同（Task 05）

状态：静态 feed 随 Task 05 上线；**缓存响应头（Cache-Control/ETag/304）由 Task 06 生产服务器配置验收**——本地静态文件可解析不等于线上缓存生效。
本文与 `site/src/lib/feed-build.ts` 的实现共同构成行为基准。

## 1. 两个 feed

| 路径 | 内容 | 上限 | 排序 |
| --- | --- | --- | --- |
| `/feed.xml` | 当前公开 release 的最近**有效**变化 | 100 条 | observationDate 倒序 + id 升序（与公开 changes 查询默认排序一致） |
| `/feed/weekly.xml` | 最近正式周报 | 30 期 | 发布日期倒序 |

- 输出 RSS 2.0、UTF-8；feed 与每个 item 的 link 使用 canonical HTTPS
  URL（`https://daily.maas.click`，单一配置来源 public-access.ts）。
- 「有效变化」= `status=active`；**已撤回（withdrawn）记录不进默认 feed**。
- weekly 只含 `site/src/content/weekly/` 正式周报——滚动摘要、草稿
  不在此 feed。

## 2. 身份、链接与修订

- 变化项 GUID = 稳定 record ID（obs_/price_ 前缀）；
  周报 GUID = 稳定 weekly ID（发布日期）。均 `isPermaLink="false"`。
  GUID **不含** datasetVersion、标题、排序位置或构建日期。
- 变化链接 → `/item/{id}/`；周报链接 → `/weekly/{id}/`——构建产物中
  真实存在（测试逐链接检查 dist 实存）。
- 同一记录修订（标题/摘要/状态更新）保持 GUID。阅读器是否覆盖旧条目
  取决于客户端——**feed 与页面均提示详情页是修订与撤回的权威状态**。
- 撤回记录退出默认 feed；已被阅读器缓存的内容无法可靠召回。不得用
  新 GUID 制造假「新变化」覆盖旧项。

## 3. 时间与内容

- **pubDate**：仅 `timePrecision=datetime` 且 observedAt 非空的记录输出
  （RFC 822，固定 UTC，`GMT` 结尾）。只有日期精度的记录**省略 pubDate
  元素**，不合成午夜时间；原始日期精度保留在 description
  （「观察日期 YYYY-MM-DD（日期精度）」）。
- channel **不输出 lastBuildDate/pubDate**：数据时间（dataThrough）只有
  日期精度——数据截至与 datasetVersion 写在 channel description，不用
  站点构建时间冒充数据时间。
- description 为纯文本（XML 实体转义，无 CDATA 节）：
  - price_change：规则拼装的结构化事实（模型/组件/金额变化/币种/单位），
    金额为 Decimal 字符串原样，不跨条件合并不做「最低价」；
  - source_observation 有 summary：输出 summary；`summaryOrigin=llm`
    时追加「（摘要由 LLM 生成，可能不准确，请以证据与官方页面核验。）」；
  - 无 summary：只写「来源页面观察更新（平台），差异与证据见详情页」
    ——**不编造摘要**；
  - 所有条目追加元数据行（观察日期/精度/状态/修订号）。
- 不复制第三方页面全文或长摘录；来源原文经 evidence/官方 URL 回查。
- 截断常量：title 200 码点、description 600 码点（超出加省略号）。

## 4. 安全（XML 1.0 合法字符集）

- 生成前剥离 XML 1.0 非法字符（控制字符 #x0-#x8/#xB/#xC/#xE-#x1F 等）；
- 全部实体转义（`& < > " '`），无 CDATA 节——`]]>` 天然安全；
- 恶意标题、脚本标签、超长内容不破坏 feed、不产生可执行 HTML
  （description 是纯文本，浏览器不执行）。

## 5. 字节稳定性

同一 release 重复构建，两个 feed 业务内容逐字节相同（纯函数组装：
无 Date.now/new Date/Math.random/process.cwd 进内容；固定缩进与元素
顺序）。rfc2822Utc 只解析传入的 ISO 时间，绝不使用本地时区或当前时钟。

## 6. 缓存边界（Task 05 只承诺静态文件）

- 建议生产 `Cache-Control: public, max-age=1800`（≥30 分钟）+ ETag/304；
- **实际响应头与条件请求由 Task 06 的生产服务器配置验收**；
  本地 `astro preview` 的响应头不作为验收依据。
- 建议阅读器轮询间隔 ≥30 分钟。

## 7. 内容类型

endpoint 声明 `Content-Type: application/rss+xml; charset=utf-8`——
静态构建下此头是否生效取决于部署服务器；Task 06 验收时确认。
