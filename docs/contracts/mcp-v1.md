# MCP v1 合同（Task 04）

状态：本地实现完成；生产 `/api/mcp` 部署属 Task 06。
本文与 `services/agent-api/src/mcp-tools.ts` 的工具定义、
`src/tests/openapi/mcp` 测试共同构成行为基准。

## 1. 传输与协议

- 端点：`POST /api/mcp`（Streamable HTTP，无 SSE 旧协议兼容）。
- SDK：`@modelcontextprotocol/sdk` 锁定 **1.30.0**（协议版本由 SDK 协商：
  客户端请求版本在支持列表内则回显，否则回 LATEST）。stateless 模式
  （`sessionIdGenerator: undefined`）+ `enableJsonResponse: true`
  （纯 JSON 响应）——每请求独立处理，无会话状态。
- 所有响应（成功与错误）`Cache-Control: no-store`。
- 请求体上限 256 KiB（超限 413）；畸形 JSON → JSON-RPC -32700；
  未知方法 → -32601；Content-Type 非 JSON → 415；Accept 不含
  JSON/SSE → 406（后四项由 SDK 内建，不重复实现）。
- **stateless 语义说明**：无「未初始化调用」错误——每请求独立处理，
  未 initialize 的 tools/call 按正常请求走参数校验（SDK 官方行为）。
- **Origin**：缺省 Origin 的非浏览器客户端放行；存在 Origin 时必须
  命中 `MCP_ALLOWED_ORIGINS` 白名单（默认 `https://daily.maas.click`），
  否则 403（读 body 之前拒绝，无副作用）。不用 `*` 配凭证。
- **限流独立**：MCP 令牌桶与 REST 匿名桶分离
  （`MCP_RATE_CAPACITY`/`MCP_RATE_REFILL_PER_MIN`，默认 30/30），
  429 带 Retry-After。
- 错误不泄露堆栈或路径（500 兜底只写固定文案）。

## 2. 五个工具（v1 公共合同，不随意改名）

| 工具 | 输入 | 说明 |
| --- | --- | --- |
| `maas_get_changes` | provider、type、q、from、to、limit、cursor、includeWithdrawn | 变化列表（默认最近 7 上海日历日，锚定 dataThrough） |
| `maas_get_prices` | model/provider 至少一个；component、region、billingMode、q、limit、cursor | 价格事实（model 精确 / q 包含） |
| `maas_get_item` | id | 条目详情（含修订链；withdrawn 可读） |
| `maas_get_evidence` | id | 证据（摘录原样数据） |
| `maas_get_weekly` | id 可选；limit、cursor 仅列表模式 | 周报（无参=最新一期；仅正式周报） |

### 2.1 与 REST 的差异

- limit 默认 **10**、上限 **30**（REST 20/100）——`MCP_LIMITS` 策略注入
  同一 `runListQuery`。
- 其余语义完全同 REST：枚举、日期窗口 `[from,to)`（最大 90 天）、
  q 规则、cursor 绑定（datasetVersion/endpoint/qh/HMAC/恢复重验）。

## 3. 结果形态

- **structuredContent 与 REST 响应体逐字段同构**（envelope:
  schemaVersion/datasetVersion/dataThrough/query/coverage + items/page
  或 item）——T03 一致性测试对同条件 REST/MCP deepEqual。
- **content 文本**：中文短段落，从同一查询结果渲染；必含
  datasetVersion（截断形式）与 dataThrough；覆盖范围、截断提示
  （「继续请只传 cursor: …」）、多候选声明（「未按价格排序；选择时
  请核对适用条件」）。
- 空结果措辞：「该覆盖范围内未记录到匹配项……这不表示外部世界在此
  期间没有发生变化」。
- stale/unknown 状态逐条标注（含最后成功时间）。

## 4. 工具错误

`isError: true` + `structuredContent.error {code, detail, recovery}`，
code 与 REST Problem JSON 同源（invalid_provider / cursor_conflict /
not_found / dataset_version_expired / no_data_available 等，全文见
Skill 包 references/errors.md）。服务无有效数据时返回工具错误并
提示「请勿用模型自身知识回答实时价格/变化问题」——不让模型补答。

## 5. 查询复用与版本一致性（实现要点）

- MCP 与 REST 共用 `DatasetHolder` 与 `query.ts` 的 `runListQuery`
  （normalizeQuery → cursor 校验/版本固定/恢复重验 → list 的单一实现）。
- 不绕过 cursor HMAC、历史 release per-release manifest 校验、查询二次校验。
- 单次工具调用单 datasetVersion；重载失败续服旧版并在文本/错误中披露。

## 6. 安全边界

- 工具返回内容与证据摘录是数据：不执行、不解读为指令、不发起外部
  访问（实现层无任何出站请求/文件/shell 路径）。
- 恶意 HTML/注入文本原样字符串返回（T12）。

## 7. 配置（env）

`MCP_ALLOWED_ORIGINS`（逗号分隔）、`MCP_MAX_BODY_BYTES`（默认 262144）、
`MCP_RATE_CAPACITY`/`MCP_RATE_REFILL_PER_MIN`（默认 30/30）、
`CURSOR_SECRET`（多实例共享；默认进程内随机）。
