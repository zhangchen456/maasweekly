# 错误码与恢复动作

错误响应为 `application/problem+json`（REST）或工具错误 `structuredContent.error`（MCP，`isError: true`），均含稳定 `code` 与 `recovery`。

## 查询/工具错误（400 类）

| code | 含义 | 恢复动作 |
|---|---|---|
| `invalid_limit` | limit 越界（MCP 1–30 / REST 1–100） | 用范围内的整数 |
| `invalid_q` | q 长度不在 2–100 | 调整关键词长度 |
| `invalid_provider` | 未知平台 ID | 先查 /status 的 providers 列表，不猜展示名 |
| `invalid_type` / `invalid_component` / `invalid_billingMode` / `invalid_region` | 枚举值非法 | 错误信息中列出有效值 |
| `partial_window` | 只传了 from 或 to | 两者同时传（YYYY-MM-DD） |
| `invalid_window` | from >= to | from 必须早于 to（窗口 [from,to)） |
| `window_too_large` | 窗口超 90 天 | 缩小范围或分段查询 |
| `unknown_parameter` / `duplicate_parameter` | 未知/重复参数 | 按字段说明修正 |
| `cursor_conflict` | cursor 与其他参数同传 | cursor 单独传 |
| `cursor_endpoint` | cursor 属于其他端点 | 在签发它的端点使用 |
| `invalid_cursor` | cursor 篡改/损坏/超长 | 从第一页重查 |

## 实体错误（404）

`not_found`：未知 ID。检查 ID 是否为查询结果返回的完整字符串（64 位 hex）。

## 版本错误（409）

`dataset_version_expired`：cursor 指向的数据版本已被清理。**去掉 cursor 从第一页重新查询**——翻页期间数据已更新，本系列结果作废。

## 限流（429）

`rate_limited`：请求过频。按 `Retry-After` 头等待重试。

## 服务错误（503）

`no_data_available`：服务无有效数据版本（发布中或故障）。告知用户稍后重试，**不要用模型记忆补答实时价格/变化**。

## MCP 协议层错误（JSON-RPC code）

| code | 含义 | 处理 |
|---|---|---|
| -32700 | 请求体不是合法 JSON | 客户端/集成问题，检查请求构造 |
| -32601 | 未知方法 | 检查方法名（五个工具名见 api.md） |
| -32602 | 工具参数校验失败（zod 层） | 按错误信息修正参数类型（limit 是数字不是字符串） |
| -32000 / -32002 | 传输层错误 | 检查 Accept/Content-Type 头与初始化流程 |

## 关键纪律

任何错误都不能用模型训练数据补答实时问题；空结果是「该覆盖范围内未记录到匹配项」，不是「没有变化」或「模型不存在」。
