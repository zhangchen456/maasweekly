# 公开数据契约与 REST API v1（Task 03）

状态：本地实现完成，待 Task 04 接入 MCP/Skill、待 Task 06 生产部署。
本文是 `site/public/openapi-v1.json` 的行为说明，两者由
`services/agent-api/src/tests/openapi.test.ts`（T17）自动对照。

## 1. 数据对象与版本

### 1.1 datasetVersion

`ds_<64 hex>`，由六个公开集合（changes/items/prices/evidence/weekly/status）
及 release 内冻结的 `modelIdentities` catalog 的规范内容摘要计算：UTF-8、对象键排序、稳定数组排序、紧凑 JSON；
排除 `generatedAt`（墙钟）与任何构建路径。同输入重建得到相同版本与
相同业务文件字节；任一实体、状态、coverage 或 catalog 公开身份/名称/家族关系变化产生新版本。

`manifest.json` 的 `files[].sha256` 记录**实际文件字节**哈希（供
`--check` 与服务端启动校验），与 datasetVersion 的规范内容摘要分离。

### 1.2 时间精度

- 时间统一 ISO 8601 UTC（带 Z）。
- 只有日期精度的历史数据保留 `observationDate` + `timePrecision=date`，
  `observedAt` 为 null，不补造午夜时间。
- `publishedAt` 是官方发布时间，无来源则为 null，不用 updatedAt 替代。

### 1.3 金额

Decimal 字符串（如 `"1.500000"`），禁止浮点。原币种（USD/CNY）、
原单位（unitQuantity + unitName）与完整适用条件原样返回；不合并
不同 region/billingMode/serviceTier/contextBand/timeCondition，不自动
选最低价，不计算动态汇率。

## 2. 变化与条目（changes / items）

- `recordType=source_observation`（Task 01 来源观察）与
  `price_change`（Task 02 价格事件）统一投影。
- id/revision/status/permalink 保留归档原值，exporter 不重算公开 ID。
- 通用页面差异为 `changeType=source_updated`、`evidenceLevel=source_diff`，
  不升级为模型发布/下线/价格变化。
- source_observation 的 `evidenceIds=[]`（证据即来源 diff 本身）；
  price_change 的 `evidenceIds=[before?, after?]`。
- `summaryOrigin` 仅 rule/llm/manual/null；价格事件 title 为规则拼装、
  summary 为 null（不编造）。
- **withdrawn**：保留在 items 集合；changes 列表默认隐藏，
  `includeWithdrawn=true` 显式返回；`/items/{id}` 始终可读（含修订链）。
- `quality.state`：fresh/stale/unknown。Task 01 来源流的状态由
  daily_changes 的 failed 记录联查推导（精度=日）；Task 02 价格流由
  current.json sources 推导。失败沿用的旧数据标 stale，不显示 fresh。
- 公开投影不含 provenance（Task 01 记录的 diff_file 含本地路径）。

## 3. 价格（prices）

- 只投影 `current.json` 指向的已接受事实版本（非旧 ledger 显示行）。
- `id` = fact version_id；默认只返回当前可用事实；stale 事实照常
  返回并带 quality 状态与原观察时间。
- `model` 查询为规范化后大小写不敏感**精确匹配**，无别名推断；
  `q` 为 modelKey 文本包含。
- `evidenceStatus` 非 complete 原样披露（不因存在改为 verified）。

## 4. 证据（evidence）

- Task 02 不可变证据的投影：excerptText/excerptHash/locator/
  completeness/relatedFactIds。
- 不暴露原始快照文件、HTML 文件本体、本地路径与 snapshotContentId。
- `observedAtRange`：引用该证据的事实观察时间区间（无引用为 null）。
- `relatedFactIds` 为闭合集合——仅保留在公开数据（prices 或公开
  change 的版本引用）中可达的事实版本。无引用的历史证据保留在静态
  投影中，但无列表端点（只有 `/evidence/{id}`），天然不在默认列表。
- excerptText 恶意 HTML 以普通字符串原样返回；展示安全属客户端责任。

## 5. 周报（weekly）

- 只读 `site/src/content/weekly/` 正式周报（id=发布日期），消费
  weekly-structured 结构化投影；`/weekly/{id}` 返回结构化内容 +
  `/weekly/{id}/` 网页链接。
- 滚动 `weekly-digest.json` 不是正式周报实体，不在任何 weekly 端点。

## 6. 查询、分页与版本固定

- limit 默认 20、上限 100；q 长 2–100（trim+casefold）。
- 时间窗口 `[from, to)`，最大 90 天；无 from/to 时以 release
  dataThrough 锚定最近 7 个上海日历日（不使用请求机器墙钟）。
- provider/component/billingMode/region 用枚举（来自当前 release 的
  status）；未知值 400，不静默空列表。
- `modelId` / `familyId` 的合法集合来自该 release 的 `model-identities.json`，
  不从 changes/prices/items 反推。catalog 的 `models` 只含正式 model，
  `families` 只含正式 family；合法但整个 dataset 无记录 → 200 + 空 items，
  未登记 → 400 `invalid_model_id` / `invalid_family_id`。
- catalog 为内部辅助文件，进入 manifest、bytes/SHA-256 校验和 datasetVersion，
  不新增公开 `/models` endpoint。历史 cursor 只用目标 release 自己的 catalog
  重验查询；缺失/损坏（含补丁前未携带 catalog 的旧版本）按 409 处理，不回填当前 registry。
- **cursor**：base64url 规范 JSON，绑定 schemaVersion/datasetVersion/
  endpoint/查询摘要(qh)/排序键，并携带原始查询参数（翻页时服务端
  恢复查询，客户端只传 cursor）。**cursor 带 HMAC-SHA256 服务端签名**
  （复验 P1-2 修复）：篡改任何字段（含重算 qh）→ 400 invalid_cursor；
  签名有效时恢复的查询参数仍重新走全量校验（limit/窗口/枚举同第一页）。
  - cursor 必须单独传递（携带其他任何参数 → 400 cursor_conflict）。
  - 后续页固定读取 cursor 中的 datasetVersion，不自动切到 current。
  - 版本已清理**或完整性校验失败** → 409 dataset_version_expired，
    recovery=从第一页重查（历史 release 按 per-release manifest 的
    bytes/SHA-256 校验，篡改即拒载）。
  - qh 与查询参数自洽性校验（防篡改第二层）。
- 排序：changes 日期倒序 + id 升序；prices provider/model/component/
  factKey 升序；weekly 日期倒序。keyset 分页，同版本全量翻页无重复
  无遗漏。
- 合法查询无结果返回 200 + 空 items + 实际 coverage；不能宣称覆盖
  外日期「没有变化」。

## 7. HTTP 行为

- 成功响应 ETag = 响应体字节 SHA-256 强 ETag；支持 If-None-Match/304。
- `Cache-Control: max-age=0, s-maxage=300`；`X-Request-Id` 每请求
  唯一（header，不进响应体——保证 ETag 稳定）。
- CORS：`Access-Control-Allow-Origin: *`，无 credentials；暴露
  ETag/Retry-After/X-Request-Id。支持 HEAD/OPTIONS。
- 错误为 `application/problem+json`，含 code/requestId/recovery：
  - 400 invalid_*（参数/cursor）、cursor_conflict、cursor_endpoint、
    cursor_query_mismatch
  - 404 not_found（未知实体/路径；无通配读取）
  - 409 dataset_version_expired
  - 413 request_too_large（URL/超长 cursor）
  - 429 rate_limited（带 Retry-After；进程内令牌桶，匿名共享）
  - 503 no_data_available（无有效 release；status 端点仍可用）
- 错误响应 `Cache-Control: no-store`。

## 8. 服务运维

- 默认 `127.0.0.1` + PORT；`PUBLIC_DATA_ROOT` 指定数据根。
- 启动全量校验（manifest/路径/hash/结构），失败不半加载。
- 热重载：轮询 manifest（RELOAD_INTERVAL_MS，默认 30s）或 SIGHUP；
  新 release 先完整加载验证再原子替换；失败续服旧版并在
  /status 披露 lastReloadError。单请求单 dataset 实例，不混版。

## 9. 保留与修正

- **每个 release 目录自带 manifest.json**（复验 P1-1 修复）：与顶层
  指针 manifest 同构，供历史版本按相同路径/bytes/SHA-256 校验加载。
- release 保留：当前版本 + 7 自然日内 manifest 记录的 + 至少上一版。
- 清理只操作 `data/public/v1/releases/`，绝不触碰 Task 01/02 原始归档。
- 实体修订产生新 datasetVersion；旧版本在保留期内仍可经 cursor 访问。

## 10. 覆盖限制（如实声明）

- 数据**不代表实时**：release 是快照，dataThrough 是数据上限。
- Task 01 来源流状态精度为**日**（daily_changes 滚动窗口约 60 天），
  窗口外为 unknown；不能用构建时间冒充数据更新时间。
- 条目数量不是核验覆盖率。
- 覆盖外日期不能宣称「没有变化」。

## 11. v1 兼容策略

允许新增可选字段；删除字段、改字段含义或改类型必须开 v2。
schemaVersion 当前 "1.0"。

## 12. 本地体验

```bash
python3 pipeline/scripts/export-public-data.py          # 构建 release
python3 pipeline/scripts/export-public-data.py --check  # 校验
cd services/agent-api && npm run build && npm start     # 127.0.0.1:8787
curl http://127.0.0.1:8787/api/v1/status
```
