# Task 03：统一公开数据投影与 REST API v1

状态：待实现，可直接交给 coding agent 执行。日期：2026-09-16。

前置：Task 01 已建立稳定来源记录和永久链接；Task 02 已建立价格事实、证据、价格事件与归档门禁。本任务进入 P0-2“信息可查询”，把两套归档转换为同一版本的公开数据，并提供匿名只读 REST API。

本任务完成不代表 Agent 接入或整个 P0 完成。MCP、Skill、RSS、接入页及生产发布分别留给后续任务。

## 1. 目标与用户体验

外部程序无需读取仓库内部目录，也能稳定完成以下查询：

1. 查询最近一段时间的平台变化，按平台、类型、关键词和日期筛选。
2. 按模型、平台、计费组件和条件查询价格，不丢失原币种、单位和适用条件。
3. 用稳定 ID 打开来源记录或价格事件，并继续访问对应证据。
4. 查询正式周报及各数据流当前覆盖、更新时间和失败状态。
5. 使用 cursor 连续翻页时始终读取同一个数据版本；版本失效时得到明确恢复动作。

产品依据：[产品规划 P0-2、F02、F06 及公共业务规则](./product-plan.md)、[用户故事 US-02、US-03、US-05、US-06、US-08、US-09、US-11](./user-stories.md)、[实施细化草案 C 工作包](../../research/2026-09-11-evolution-plan.md)。

## 2. 工作边界

- 开始前读取当前 `AGENTS.md`、README、HANDOFF、Task 01/02 结果文档，复核工作区及已部署数据；本文中的数量不是固定验收值。
- 授权范围为本地实现、fixture、测试、本地服务和可审查文档。不包含 commit、push、服务器配置或生产部署；发布等待用户明确指示。
- 公开服务只读取 Task 01/02 已提交归档和正式周报，不在请求期间抓网页、调用 LLM、改写数据或读取任意路径。
- 不实现 MCP、Skill、RSS、账户、API Key、收费、收藏、Webhooks、全文搜索、向量库、数据库、模型推荐或“最低价”结论。
- 不重构 Task 01/02 身份算法和归档格式。发现源归档损坏时构建失败，不在 exporter 内静默修复。
- 不公开内部原始 HTML、抓取凭据、本地路径或无必要全文。公开 evidence 只包含 Task 02 已批准的必要摘录、定位和 hash。
- 不把滚动 7 天摘要称为正式周报；不把缺记录解释成“没有变化”。
- 故障注入、版本清理和并发测试必须使用临时目录，不修改真实归档。

## 3. 交付文件

建议新增或修改以下位置；coding agent 开始时应核对现状并在结果文档记录最终路径：

```text
docs/contracts/public-api-v1.md
schemas/public-v1/
  common.schema.json
  record.schema.json
  price.schema.json
  evidence.schema.json
  weekly.schema.json
  status.schema.json
  manifest.schema.json
pipeline/public_export/
  canonical.py
  loaders.py
  projector.py
  validator.py
pipeline/scripts/export-public-data.py
data/public/v1/
  manifest.json
  releases/<datasetVersion>/
    changes.json
    items.json
    prices.json
    evidence.json
    weekly.json
    status.json
services/agent-api/
  package.json
  package-lock.json
  tsconfig.json
  src/server.ts
  src/dataset.ts
  src/query.ts
  src/http.ts
  tests/
site/public/openapi-v1.json
tests/test_public_export.py
```

可调整模块拆分，但必须保留唯一 exporter、公开 schema、不可变版本目录、REST 服务和可直接执行的测试入口。

## 4. 公开数据契约

### 4.1 版本与目录

`export-public-data.py` 是唯一公开投影入口。它从已校验的 Task 01/02 归档和正式周报构建完整 release，先在临时目录完成 schema、引用和 hash 校验，再原子发布。

`datasetVersion` 为全部公开实体规范内容的 SHA-256，格式 `ds_<64 hex>`。计算时：

- 使用 UTF-8、对象键排序、稳定数组排序和紧凑 JSON。
- 排除构建机器路径、临时时间、requestId 和 release 目录名。
- `generatedAt` 可记录在 manifest，但不得参与 `datasetVersion`；同输入重建必须得到相同版本和相同业务文件字节。
- 任一公开实体、状态或 coverage 变化都必须产生新版本。

`data/public/v1/manifest.json` 是当前指针，至少包含：

```json
{
  "schemaVersion": "1.0",
  "datasetVersion": "ds_...",
  "generatedAt": "2026-09-16T00:00:00Z",
  "dataThrough": "2026-09-16T00:00:00Z",
  "coverage": {},
  "files": [
    {"path": "releases/ds_.../changes.json", "sha256": "...", "bytes": 123}
  ],
  "retainedVersions": ["ds_..."]
}
```

每个 `files` 条目必须核对相对路径、大小和 SHA-256。manifest 只允许引用 `data/public/v1/` 内文件，不接受 `..`、绝对路径或符号链接逃逸。

构建默认保留当前版本及最近 7 个自然日内仍被 manifest 记录的版本，至少保留当前和上一版本。Task 03 只实现本地保留与查询语义；生产 release 切换和服务器清理属于 Task 06。不得清理 Task 01/02 原始归档。

### 4.2 公共响应元数据

所有成功 JSON 响应共享：

```json
{
  "schemaVersion": "1.0",
  "datasetVersion": "ds_...",
  "dataThrough": "2026-09-16T00:00:00Z",
  "query": {},
  "coverage": {},
  "items": [],
  "page": {"limit": 20, "nextCursor": null}
}
```

实体接口可以用 `item` 代替 `items/page`，但仍返回 schemaVersion、datasetVersion、dataThrough 和 coverage。成功响应不能加入每次请求变化的时间或 requestId，保证 ETag 稳定；requestId 通过 `X-Request-Id` header 返回。

时间统一为带 `Z` 的 ISO 8601 UTC。只有日期精度的历史数据保留 `observationDate` 和 `timePrecision="date"`，不得补造午夜时间。所有 Decimal 金额用字符串返回。

### 4.3 变化与条目

公开 changes 同时容纳：

- Task 01 `source_observation`；
- Task 02 `price_change`。

公共记录最少包含：id、revision、status、recordType、providerId、sourceId、observedAt、observationDate、timePrecision、publishedAt、updatedAt、title、summary、summaryOrigin、changeType、evidenceLevel、quality、links、evidenceIds。

规则：

- 保留归档中的稳定 id、revision、status 和 permalink；exporter 不重新计算另一套公共 ID。
- `providerId` 与 `sourceId` 使用现有 registry 映射。行业来源允许 providerId=null；未知 sourceId 是门禁错误，不能临时取展示名。
- withdrawn 条目保留在 items 中；changes 默认不返回，显式 `includeWithdrawn=true` 才返回。
- 通用页面差异为 `changeType=source_updated`、`evidenceLevel=source_diff`，不能升级为模型发布、下线或价格变化。
- 价格事件保留 before/after 事实版本引用、真实单位、条件和 comparison；不新增跨币种或跨条件推断。
- `summaryOrigin` 只能是 `rule`、`llm`、`manual`；未知时为 null，不猜测。
- `quality` 至少含 state、reason、lastSuccessAt；失败沿用的旧数据不能显示为 fresh。

### 4.4 价格

价格投影以 Task 02 `current.json` 指向的已接受事实版本为准，而不是旧 ledger 的显示行。每项至少返回：

id（version_id）、factKey、providerId、modelKey、component、amount、currency、unitQuantity、unitName、region、billingMode、serviceTier、contextBand、timeCondition、effectiveAt、observedAt、evidenceId、evidenceStatus、quality。

- 默认只返回当前可用事实；stale 事实仍可查询，但必须带状态和原观察时间。
- 不合并不同 region、billingMode、serviceTier、contextBand 或 timeCondition。
- 不自动选择最低价，不计算动态汇率，不把展示换算写回事实。
- model 查询 P0 采用规范化后的大小写不敏感精确匹配或明确的 `q` 文本包含；不做未经维护的模型别名推断。
- evidenceStatus 非 complete 时原样披露，API 不能因对象存在就改为 verified。

### 4.5 证据

公开 evidence 由 Task 02 不可变证据记录投影，至少包含 id、sourceId、providerId、sourceUrl、subpageUrl、observedAtRange、locatorType、locator、extractorVersion、excerptText、excerptHash、contentHash、completeness、reasons 和 relatedFactIds。

- evidence ID、excerptHash 和快照关联必须由 Task 02 门禁验证后才能发布。
- 不暴露内部原始快照文件、HTML 或本地路径。
- relatedFactIds 必须双向存在；无引用但合法的历史证据可保留在静态投影，不应出现在默认 API 列表。
- 恶意 HTML 以普通字符串返回；客户端展示安全属于客户端责任，但 API 不生成可执行片段或 `javascript:` 链接。

### 4.6 正式周报与状态

weekly 只读取 `site/src/content/weekly/` 中符合现有正式周报契约的条目，保留已有 `/weekly/{id}/` 路径。滚动 `weekly-digest.json` 不能作为正式周报实体。

status 聚合来源记录、价格抓取和正式周报三类数据流：lastAttemptAt、lastSuccessAt、state、reason、coverage、dataThrough。未知值显式为 null/unknown。一次成功构建不能覆盖来源失败状态。

## 5. Exporter 行为

实现以下命令：

```bash
python3 pipeline/scripts/export-public-data.py
python3 pipeline/scripts/export-public-data.py --check
python3 pipeline/scripts/export-public-data.py --dry-run
python3 pipeline/scripts/export-public-data.py --output-dir /tmp/public-v1
```

- 默认输入为仓库正式归档，默认输出 `data/public/v1/`。
- `--check` 只验证当前 manifest、全部文件 hash、schema、排序和引用，不创建或修改任何文件。
- `--dry-run` 完整构建到内存或临时目录并报告预计 datasetVersion、数量和错误，正式目录逐字节不变。
- `--output-dir` 允许隔离测试；不能暗中改写站点数据或正式 manifest。
- 输入 JSON 损坏、未知身份、重复 ID 内容冲突、引用悬空、schema 不符、hash 不符时非零退出，正式输出零写入。
- 相同 ID 出现不同身份是硬错误；相同规范内容可幂等复用。
- loader 只接受固定配置的输入根，拒绝符号链接和目录穿越。
- 公开数组有稳定排序；changes 使用有效时间倒序、id 升序作为最终 tie-break；prices 使用 providerId、modelKey、component、factKey；其他集合规则写入合同并测试。

构建报告输出各实体数量、fresh/stale/unknown、complete/partial/unavailable、正式周报数量、覆盖日期和版本。不得把条目数量当作核验覆盖率。

## 6. REST API v1

服务位于 `services/agent-api/`，使用 Node.js 22 + TypeScript。可以采用轻量 HTTP 框架或 Node 标准库，但业务查询必须集中在无 HTTP 依赖的 `query` 模块，供后续 MCP 复用。依赖锁定在 package-lock；请求期间只读已发布 release。

### 6.1 接口

| 方法与路径 | 参数 | 行为 |
| --- | --- | --- |
| `GET /api/v1/changes` | provider、type、q、from、to、limit、cursor、includeWithdrawn | 最近变化；默认最近 7 天，以 release 的 asOf/dataThrough 为锚点 |
| `GET /api/v1/items/{id}` | 无 | 返回 source observation 或 price event；withdrawn 仍返回 200 和状态 |
| `GET /api/v1/prices` | provider、model、component、region、billingMode、q、limit、cursor | 返回原币种、原单位和完整条件 |
| `GET /api/v1/evidence/{id}` | 无 | 返回必要摘录、定位、完整性和相关事实 |
| `GET /api/v1/weekly` | limit、cursor | 正式周报索引，默认最新在前 |
| `GET /api/v1/weekly/{id}` | 无 | 返回指定正式周报结构化内容与网页链接 |
| `GET /api/v1/status` | 无 | 返回当前版本和各数据流状态 |

实现 `HEAD` 与 `OPTIONS`。除上述路径外返回 404，不提供文件路径参数或通配读取。

### 6.2 参数与时间窗口

- 默认 limit=20，上限 100；非整数、0、负数或超上限返回 400。
- q 长度 2–100，做 Unicode trim/casefold；空白、超长返回 400。
- from/to 接受 `YYYY-MM-DD` 或带时区 ISO 8601；绝对窗口采用 `[from,to)`，最大 90 天，from >= to 返回 400。
- changes 无 from/to 时，以 release 的 `asOf` 计算最近 7 个上海日历日，不使用请求机器墙钟。
- provider、type、component、billingMode 使用明确枚举或现有 registry；未知值返回 400，不静默返回空列表。
- 重复参数、未知参数、cursor 与其他分页/筛选参数冲突均返回 400。
- 合法查询无结果返回 200、空 items 和实际 coverage；不能宣称覆盖外日期“没有变化”。

### 6.3 Cursor 与固定版本

cursor 为 base64url 编码的规范 JSON，至少绑定：schemaVersion、datasetVersion、endpoint、normalizedQueryHash、lastSortKey。它是不透明分页令牌，不是权限凭证。

- 解码、字段、长度、版本、端点和查询摘要严格校验；篡改或跨查询复用返回 400 `invalid_cursor`。
- 后续页固定读取 cursor 中的 datasetVersion，不自动切到 current。
- 对应 release 已清理时返回 409 `dataset_version_expired`，recovery 明确要求从第一页重查。
- 分页排序必须有唯一最终键；同版本全量翻页无重复、无遗漏。

### 6.4 HTTP、缓存与错误

成功响应 ETag 由规范查询及稳定响应内容生成。支持 `If-None-Match`：未变化返回 304、空响应体。GET/HEAD 成功默认：

```text
Cache-Control: max-age=0, s-maxage=300
Content-Type: application/json; charset=utf-8
X-Request-Id: <opaque id>
```

允许匿名 GET/HEAD/OPTIONS CORS，默认 `Access-Control-Allow-Origin: *`，不允许 credentials；暴露 ETag、Retry-After、X-Request-Id。Task 03 不实现用户身份。

错误采用 `application/problem+json`：

```json
{
  "type": "https://daily.maas.click/problems/invalid-query",
  "title": "Invalid query",
  "status": 400,
  "detail": "limit must be between 1 and 100",
  "code": "invalid_limit",
  "requestId": "...",
  "recovery": "Use an integer from 1 to 100."
}
```

至少覆盖：400 非法查询/cursor、404 未知实体/路径、409 版本失效、413 请求过大、429 限流并带 Retry-After、503 无任何有效数据。错误响应 `Cache-Control: no-store`。服务更新失败时继续服务最近有效 release，并在 status 披露；启动时从未有有效 release 则 503。

匿名限流采用可配置、进程内的保守默认值即可，测试不依赖真实客户端 IP。Task 06 再决定 nginx 层限流。

### 6.5 启动与重载

- 默认绑定 `127.0.0.1`，端口来自 `PORT`，不自行终止 TLS。
- 启动时完整验证 manifest、schema 和文件 hash；失败不得半加载。
- 可轮询 manifest 或响应显式信号重载。先加载并验证新 release，再原子替换内存 dataset；验证失败继续服务旧版并记录状态。
- 单次请求固定持有一个 dataset 实例，重载期间不得混用版本。
- 测试可通过 `PUBLIC_DATA_ROOT` 指定临时目录；生产路径固定由部署配置提供。

## 7. OpenAPI 与合同文档

生成或维护 `site/public/openapi-v1.json`，内容必须与实际路由、参数、响应和 Problem JSON 一致。构建测试应对照服务路由，避免文档存在但接口缺失。

`docs/contracts/public-api-v1.md` 说明：

- 数据对象、时间精度、状态、保留与修正规则；
- 查询过滤、排序、分页和版本失效；
- 缓存、ETag、错误码及恢复动作；
- 数据覆盖限制和“不代表实时/完整历史”的边界；
- v1 兼容策略：允许新增可选字段，删除/改义/改类型必须开 v2。

本任务不编写 MCP 配置、Skill 文档、安装器或接入营销页面。

## 8. 开发顺序

1. **盘点与字段映射**：统计 Task 01/02/weekly 的真实字段、状态和异常样本；输出映射表，不直接照抄旧页面 JSON。
2. **固定 schema 与规范化**：先写 schema、canonical JSON、排序、datasetVersion 和 manifest 测试。
3. **实现 loaders/projector**：加载三类输入，建立显式 source/provider 映射，完成双向引用与状态校验。
4. **实现 exporter**：两阶段输出、`--check`、`--dry-run`、隔离输出及重复构建稳定性。
5. **实现 query 模块**：筛选、时间窗口、排序、cursor 和固定版本分页。
6. **实现 HTTP 层**：路由、ETag、CORS、Problem JSON、限流、启动与安全重载。
7. **生成 OpenAPI 和合同**：与实际行为做自动一致性检查。
8. **真实数据验收**：用当前完整归档生成 release，启动本地服务，执行第 9 节场景并记录数量、版本、耗时和限制。
9. **交付收尾**：新增 `task-03-result.md`，更新 README/HANDOFF；不提交无关工作区内容，不部署。

## 9. 必须通过的验收

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T01 | 相同输入连续导出两次 | datasetVersion、业务文件和 manifest 业务字段稳定，无多余 release |
| T02 | 摘要、revision、撤回或质量状态改变 | 身份不变；内容与 ETag 更新；withdrawn 详情仍可读，默认列表隐藏 |
| T03 | 输入含坏 JSON、未知 source、重复 ID 冲突、悬空证据 | exporter 非零退出，正式 public 目录逐字节不变 |
| T04 | `--check`、`--dry-run`、隔离 output-dir | 前两者正式目录零写入；隔离输出不污染仓库正式数据 |
| T05 | manifest 文件大小/hash、schema、目录穿越或符号链接篡改 | 门禁失败，不加载或发布损坏版本 |
| T06 | changes 默认查询及 provider/type/q/from/to 组合 | 结果、规范 query、coverage 与排序正确；默认窗口锚定数据版本而非墙钟 |
| T07 | prices 多平台、多组件、多 region/tier/context/time 条件 | 不丢条件、不自动择最低；Decimal、原币种和单位保持 |
| T08 | stale、partial、全来源失败但有旧版／无旧版 | 状态与时间真实；有旧版继续服务并披露，无有效版 503 |
| T09 | item、evidence、weekly 正常与未知 ID | 正常实体引用闭环；未知实体 404；正式周报不混入滚动摘要 |
| T10 | limit、q、日期、枚举、未知/重复参数非法 | 400 Problem JSON，code 与 recovery 可执行，不静默忽略 |
| T11 | 同版本连续翻完所有页 | 无重复、无遗漏；顺序稳定；cursor 与查询和端点绑定 |
| T12 | 翻页期间发布新版本 | 旧 cursor 继续读旧 release；清理后返回 409 restart_query |
| T13 | 相同请求 ETag 重试 | 首次 200，If-None-Match 后 304 空体；实体修订后重新 200 |
| T14 | HEAD、OPTIONS、CORS、请求过大、限流 | header 和状态正确；无 credentials；429 带 Retry-After |
| T15 | manifest 热重载成功与新版本损坏 | 成功原子切换；失败继续服务旧版本，单次请求不混版 |
| T16 | 恶意 excerpt、非法 URL、超长 cursor、路径编码 | 只作为数据返回或拒绝；不读 public root 外文件，不产生可执行 HTML |
| T17 | OpenAPI 路由与真实服务对照 | 路径、参数、状态码和核心 schema 一致，无文档假接口 |
| T18 | 当前真实归档全量导出并启动服务 | 六类核心查询返回真实数据，所有公开引用零悬空，Task 01/02 门禁继续通过 |

测试必须覆盖 CLI 和真实 HTTP 入口，不能只调用内部 helper。分页测试至少使用两个 datasetVersion；错误和热重载测试使用临时目录。

建议最终命令：

```bash
python3 -m unittest discover -s tests -p 'test_public_export.py' -v
python3 -m unittest discover -s tests -p 'test_record_archive.py' -v
python3 -m unittest discover -s tests -p 'test_price_archive.py' -v
python3 pipeline/scripts/validate-archive.py
python3 pipeline/scripts/validate-price-archive.py --check
python3 pipeline/scripts/export-public-data.py --check

cd services/agent-api
npm ci
npm test
npm run build

cd ../../site
npm ci
npm run build
```

具体脚本名可按实现调整，但交付报告中的命令必须实际运行，并记录退出码。不要为满足命令清单创建空测试或跳过真实数据验证。

## 10. 完成定义

- [ ] 当前 Task 01/02 归档和正式周报能生成 schema 合法、引用闭合的 `data/public/v1/` release。
- [ ] 同输入重建稳定；损坏输入、半写入和无效 manifest 不会替换上一有效版本。
- [ ] 七个 REST 路径真实可调用，筛选、分页、ETag、错误和 stale 行为符合合同。
- [ ] changes、prices、item、evidence、weekly、status 六类查询使用同一 datasetVersion。
- [ ] cursor 固定版本翻页无重复/遗漏，跨查询复用与过期恢复明确。
- [ ] OpenAPI 与实现一致；公开数据不包含原始 HTML、凭据或本地路径。
- [ ] T01–T18 通过，Task 01/02 归档与站点构建无回归。
- [ ] `task-03-result.md` 包含文件清单、命令与退出码、实体数量、datasetVersion、响应样例、性能、失败注入、已知限制和本地体验地址。

本地完成后仍标记“待 Task 04 接入 MCP/Skill、待 Task 06 生产部署”。不得把本地 REST 服务称为 Agent 接入已上线，也不得因为 API 能返回数据就宣称 P0 已完成。
