# 跨平台比较：实施边界与验收顺序

状态：关系与价格身份冲突已核对；功能尚未实施、未发布。

当前 providerId 是历史查询命名空间，不能直接等同于开发者或调用平台。Google 命名空间内已有 Gemini API 和 Vertex 来源；同名字符串不构成同一上游模型的证据。保留所有现有 modelId、价格 ID、游标与筛选语义。

## 按顺序实施

1. **关系 registry**：增加 upstream-models / availabilities；以官方文档明确的 API identifier 建立精确映射，记录证据 URL、核验日期、平台、区域和状态。首先覆盖 Gemini 3.8 Flash 在 Gemini API / Google Cloud，Claude Sonnet 5.5 在 Anthropic API / Google Cloud。snapshot、preview、latest 指针分别处理，不模糊匹配。
2. **报价事实与适配器**：接入 Google Cloud 官方价格，保留原始快照和解析证据。当前价格 fact identity 不包含 source_key，不能以同一个 pricing provider 写入两平台，否则覆盖事实。新增平台独立的 pricing provider 与显式 legacy namespace 映射；避免更改既有 ID。标准、优先、Batch、Flex、缓存、区域、长上下文和未来生效优惠分别存储；报价缺失显示缺失，不按零元处理。
3. **公开合同与查询**：加法投影实体关系和报价平台，Python validator、TypeScript contract、生成副本和引用完整性一起更新。旧调用不加新参数时保持旧语义；同一 legacy modelId 可关联多个 availability。首页默认报价仍使用原平台，不因新平台更新时间较晚而悄悄替换。
4. **页面与发布**：模型页呈现开发者及可用平台；比较页按同一 upstream model 展示同口径平台报价和限制，附核验日期及官方来源。回归覆盖同模型不同平台、异名同源、有相似名字但无证据、缺价、区域/档位差异、旧价格 ID 和旧查询不变。完成完整回归、页面验收及四入口验证后归档发布资料。

## 官方证据入口

- https://platform.claude.com/docs/en/models/overview
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/sonnet-5-5
- https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing

官方当前表含不同区域与多个计费档位，且部分价格 2027-01-01 才生效。不能摘取页面第一个数字作为通用当前报价。以上是证据入口，不代表已将其导入生产账本。
