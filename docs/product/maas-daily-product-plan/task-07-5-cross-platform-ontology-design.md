# T07-5 Cross-platform Model Ontology Design

日期：2026-09-23。状态：**设计阶段（不编码）**。

前置：T07-1～T07-4B 已 RELEASED。当前 `modelId = provider-scoped canonical observed identity`。

## 1. Current-state analysis

### 1.1 当前 provider namespace 实际语义

当前 `providerId`（modelId 前缀）混合了三种不同概念：

| providerId | displayName | 实际语义 | 模型品牌 | 说明 |
|---|---|---|---|---|
| alibaba | 阿里百炼 | **API 平台** | Qwen（通义千问） | 平台=阿里百炼，模型开发者=阿里通义 |
| volcengine | 火山方舟 | **API 平台** | Doubao（豆包） | 平台=火山方舟，模型开发者=字节跳动 |
| zhipu | 智谱AI | **开发者+平台合一** | GLM | 开发者=智谱，平台=智谱开放平台 |
| anthropic | Anthropic | **开发者+平台合一** | Claude | 开发者=Anthropic，平台=Anthropic API |
| openai | OpenAI | **开发者+平台合一** | GPT | 开发者=OpenAI，平台=OpenAI API |
| google | Google | **开发者+平台合一** | Gemini | 开发者=Google，平台=Vertex AI / Gemini API |
| deepseek | DeepSeek | **开发者+平台合一** | DeepSeek | 开发者=DeepSeek，平台=DeepSeek API |
| kimi | Kimi | **开发者+平台合一** | Kimi/Moonshot | 开发者=Moonshot AI，平台=Kimi |

**核心冲突**：`alibaba` 和 `volcengine` 是**纯平台**（模型品牌 Qwen/Doubao 不是平台名），而 `anthropic`/`openai`/`google` 是**开发者=平台**。当前 system 把这两种不同关系混在同一个 `providerId` 字段里。

### 1.2 ledger provider vs canonical provider

ledger（pricing 数据源）用 **pricing provider**（`qwen`/`doubao`/`glm`），canonical 用 **platform provider**（`alibaba`/`volcengine`/`zhipu`）。`public_providers.json` 的 `pricingProviderIdToProvider` 做映射。

这进一步证明：ledger 的 provider 更接近**模型品牌**，canonical 的 provider 更接近**平台**，但 canonical 把 alibaba（平台）和 anthropic（开发者）混在了一起。

### 1.3 当前数据无跨平台同模型

对 ledger 2598 条 price 做 `model_display_name` 分组，**零个模型名出现在多个 provider**。当前 MaaS Daily 数据源是各厂商自己的定价页，不包含第三方平台（如 Bedrock/Vertex/OpenRouter）的价格。因此当前数据**没有跨平台同模型的实际需求**。

### 1.4 snapshot / pointer / preview

当前数据存在同一平台内的变体：
- **日期快照**：`qwen-flash-2025-07-28`（快照）、`qwen-flash`（基名）
- **指针**：`qwen-plus-latest`、`gemini-3-flash-preview`
- 这些目前是 unresolved 或 pointer，不进入 catalog

## 2. Problem statement

当前 ontology 无法回答：

1. Claude Sonnet 4.5 在哪些平台可用？（当前只有 Anthropic API）
2. 不同平台的 `claude-sonnet-4.5` 是否同一个上游模型？
3. `alibaba:qwen3-coder-plus` 的开发者是谁？（阿里通义，不是"阿里百炼"）
4. 同一上游模型在不同平台的价格事实有哪些？

根本问题：**provider 同时承载了"平台"和"开发者"两种语义**，且没有显式的"上游模型"实体。

## 3. Terminology

| 术语 | 定义 | 当前对应 |
|---|---|---|
| **Developer** | 模型的开发/拥有方（Anthropic, 阿里通义, 字节跳动, DeepSeek） | 部分隐含在 providerId |
| **Platform** | 模型被调用/销售的平台（Anthropic API, 阿里百炼, 火山方舟, Bedrock, Vertex） | 部分对应 providerId |
| **Upstream Model** | 跨平台稳定的模型实体（Claude Sonnet 4.5, Qwen3 Coder Plus） | 不存在 |
| **Availability** | 某 upstream model 在某平台上的可用性（含 modelKey/region/status） | 不存在 |
| **modelKey** | 平台上的原始 API model string（qwen3-coder-plus, claude-sonnet-4.5） | 已存在于 prices/changes |
| **modelId** | provider-scoped canonical observed identity（T07-3 已定义） | **保留不变** |

## 4. Candidate entities

### 4.1 Developer（开发者）

```
developerId: "anthropic" / "alibaba-qwen" / "bytedance-doubao" / "deepseek" / "moonshot-kimi"
displayName: "Anthropic" / "阿里通义" / "字节跳动" / "DeepSeek" / "Moonshot AI"
```

### 4.2 Platform（平台）

```
platformId: "anthropic-api" / "alibaba-bailian" / "volcengine-ark" / "bedrock" / "vertex-ai"
displayName: "Anthropic API" / "阿里百炼" / "火山方舟" / "AWS Bedrock" / "Google Vertex AI"
developerOwned: true/false  // Anthropic API 由 Anthropic 自己拥有；阿里百炼由阿里云运营
```

### 4.3 Upstream Model（上游模型）

```
upstreamModelId: "anthropic:claude-sonnet-4.5" / "alibaba-qwen:qwen3-coder-plus"
displayName: "Claude Sonnet 4.5" / "Qwen3 Coder Plus"
developerId: "anthropic" / "alibaba-qwen"
```

### 4.4 Availability（平台可用性）

```
availabilityId: "anthropic-api:claude-sonnet-4.5" / "alibaba-bailian:qwen3-coder-plus"
upstreamModelId: "anthropic:claude-sonnet-4.5"
platformId: "anthropic-api" / "alibaba-bailian"
modelKey: "claude-sonnet-4.5" / "qwen3-coder-plus"  // 该平台上的实际 API model string
region: "global" / "cn"
status: "active" / "deprecated"
```

## 5. Candidate relations

```
Developer ──develops──→ Upstream Model
Upstream Model ──available on──→ Platform (via Availability)
Availability ──has modelKey──→ raw API string
existing modelId ──maps to──→ Availability (1:1 in current data)
```

## 6. Real-data examples

### 10 个代表性模型 ontology mapping

| Current modelId | Developer | Upstream model | Platform | Observed modelKey |
|---|---|---|---|---|
| anthropic:claude-sonnet-4.5 | Anthropic | Claude Sonnet 4.5 | Anthropic API | claude-sonnet-4.5 |
| anthropic:claude-opus-5 | Anthropic | Claude Opus 5 | Anthropic API | claude-opus-5 |
| openai:gpt-6-astra | OpenAI | GPT-6 Astra | OpenAI API | gpt-6-astra |
| openai:gpt-5.6-sol | OpenAI | GPT-5.6 Sol | OpenAI API | gpt-5.6-sol |
| google:gemini-2.5-pro | Google | Gemini 2.5 Pro | Google Vertex AI / Gemini API | gemini-2.5-pro |
| google:gemini-3-flash-preview | Google | Gemini 3 Flash Preview | Google Vertex AI / Gemini API | gemini-3-flash-preview |
| alibaba:qwen3-coder-plus | 阿里通义 | Qwen3 Coder Plus | 阿里百炼 | qwen3-coder-plus |
| alibaba:qwen3-coder-plus | 阿里通义 | Qwen3 Coder Plus | 阿里百炼 | qwen3-coder-plus-2025-07-22 (snapshot) |
| volcengine:doubao-seed-1.6 | 字节跳动 | Doubao Seed 1.6 | 火山方舟 | doubao-seed-1.6 |
| zhipu:glm-4.7 | 智谱 | GLM 4.7 | 智谱开放平台 | glm-4.7 |
| deepseek:deepseek-v4-pro | DeepSeek | DeepSeek V4 Pro | DeepSeek API | deepseek-v4-pro |
| kimi:kimi-k3 | Moonshot AI | Kimi K3 | Kimi Platform | kimi-k3 |

**关键观察**：
- 当前数据**全部是 developer=platform 的情况**（开发者自己运营平台）
- `alibaba`/`volcengine` 是例外：平台≠模型品牌（阿里百炼≠Qwen，火山方舟≠Doubao）
- snapshot（`qwen3-coder-plus-2025-07-22`）是同一 availability 的 observed modelKey 变体，不是独立 upstream model
- 当前**无跨平台同模型**数据（Claude 只在 Anthropic，不在 Bedrock/Vertex）

## 7. Proposed schema

### 方案 B：独立实体 + relation（推荐）

```
data/model-registry/
  developers.json     # Developer 实体
  platforms.json      # Platform 实体
  upstream-models.json # Upstream Model 实体
  models.json         # 现有（保留 modelId + 新增 availabilityId 字段）

data/model-registry/
  availabilities.json # Availability relation（upstreamModelId × platformId × modelKey）
```

**现有 models.json 变更（additive）**：

```json
{
  "modelId": "alibaba:qwen3-coder-plus",  // 保留不变
  "providerId": "alibaba",                 // 保留不变
  "upstreamModelId": "alibaba-qwen:qwen3-coder-plus",  // 新增（additive）
  "developerId": "alibaba-qwen",           // 新增（additive）
  "platformId": "alibaba-bailian",         // 新增（additive）
  "canonicalName": "Qwen3 Coder Plus",     // 保留
  "familyId": "alibaba:qwen-coder",        // 保留
  "classification": "model",              // 保留
  "aliases": [...]                         // 保留
}
```

## 8. Alternative architecture comparison

### 方案 A：在现有 model registry 上扩展字段

```json
{
  "modelId": "alibaba:qwen3-coder-plus",
  "upstreamModelId": "...",
  "developerId": "...",
  "platformId": "..."
}
```

| 维度 | 方案 A（字段扩展） | 方案 B（独立实体+relation） |
|---|---|---|
| 可维护性 | 简单（一个文件） | 中等（多文件，但职责清晰） |
| 跨平台关系表达 | 弱（modelId 已 provider-scoped，跨平台需推断） | 强（upstreamModelId 显式跨平台） |
| 向后兼容 | 好（additive 字段） | 好（modelId 不变，新实体 additive） |
| 人工维护成本 | 低（只改 models.json） | 中（需维护 developers/platforms/upstream-models） |
| 未来 query 能力 | 弱（无法直接查"Claude 在哪些平台"） | 强（availability relation 可直接查） |
| 跨平台扩展 | 难（Bedrock Claude 需新建 modelId 再关联） | 自然（新建 availability 即可） |

**推荐方案 B**：虽然当前数据无跨平台同模型，但方案 B 的实体分离让未来扩展自然——新增 Bedrock Claude 只需加 availability，不需改 upstream model。方案 A 在跨平台场景会产生 `anthropic:claude-sonnet-4.5` 和 `bedrock:claude-sonnet-4.5` 两个 modelId，关联关系隐含在字段里，查询不便。

## 9. Migration strategy

### Phase 1：只加实体，不改现有行为

1. 新增 `developers.json` / `platforms.json` / `upstream-models.json` / `availabilities.json`
2. 现有 `models.json` 加 additive 字段（`upstreamModelId`/`developerId`/`platformId`）
3. public projection 不变（model-identities.json 不加新字段）
4. API/UI 不变

### Phase 2：public projection 加 upstream 字段

1. model-identities.json 加 `upstreamModelId`/`developerId`/`platformId`（additive optional）
2. `/api/v1/models` 返回新字段
3. UI 可选展示 developer/platform

### Phase 3：跨平台 query

1. `/api/v1/upstream-models` endpoint
2. 跨平台价格比较页（如果数据有跨平台）

## 10. Compatibility strategy

- `modelId` **保留不变**，继续作为 public API/UI 的稳定 identity
- 新字段全部 **additive optional**
- 旧消费者忽略新字段仍正常工作
- `model-identities.json` 的现有字段不改变含义
- `/api/v1/models` / `/api/v1/changes?modelId=` / `/api/v1/prices?modelId=` / `/model/:modelId` 全部保留

## 11. Evidence / verification model

跨平台 identity 关联必须有可审计的证据：

```json
{
  "upstreamModelId": "anthropic:claude-sonnet-4.5",
  "platformId": "bedrock",
  "modelKey": "anthropic.claude-sonnet-4.5",
  "evidence": {
    "source": "official-docs",
    "url": "https://docs.aws.amazon.com/bedrock/...",
    "verifiedAt": "2026-09-23",
    "verifiedBy": "manual"
  }
}
```

- **禁止**：fuzzy string matching / edit distance / embedding / LLM 自动合并
- **允许**：官方文档 URL、provider 官方映射、人工验证
- 原则继续：**宁可 unresolved，不可 false positive**

## 12. Unresolved cases

- snapshot（`qwen3-coder-plus-2025-07-22`）：属于同一 availability 的 observed modelKey 变体，不是独立 upstream model
- pointer（`qwen-plus-latest`）：指向某个 upstream model，但本身不是 upstream model
- preview（`gemini-3-flash-preview`）：是独立 upstream model（preview 是模型名一部分）
- emoji/噪音（`deepseek-flash-(1)`）：extractor 噪音，不进入 ontology
- **跨平台同模型当前无数据**：Bedrock/Vertex 的 Claude/Gemini 不在当前数据源——ontology 设计应支持但不提前实现

## 13. Risks

1. **provider 语义拆分风险**：`alibaba`→`alibaba-qwen`(developer) + `alibaba-bailian`(platform) 可能影响现有 provider filter 语义——需保持 `providerId` 不变，只加新字段
2. **跨平台 false positive 风险**：`claude-sonnet-4.5` 在不同平台的 modelKey 可能不同（如 Bedrock 用 `anthropic.claude-sonnet-4.5`），不能自动字符串匹配
3. **数据源覆盖风险**：当前只有厂商自己的定价页，跨平台数据需要新增数据源
4. **registry 维护成本**：新增 4 个实体文件增加维护负担——但当前 107 个 model 的映射可半自动生成（provider→developer/platform 已可从现有数据推断）

## 14. Recommended implementation phases

### T07-5.1 Ontology inventory + Gold Set

- 盘点现有 107 个 model 的 developer/platform/upstream 映射
- 建 Gold Set（10-15 个代表，含 alibaba/volcengine 平台≠品牌案例）
- 不改代码

### T07-5.2 Developer / Platform registry

- 新增 `developers.json` / `platforms.json`
- 从现有 provider 推断初始实体（8-16 个 developer，8-16 个 platform）
- validator + 测试

### T07-5.3 Upstream Model registry

- 新增 `upstream-models.json`
- 从现有 modelId 推断初始 upstream model（107 个）
- developer 关联

### T07-5.4 Availability relation

- 新增 `availabilities.json`
- 关联 upstreamModel × platform × modelKey
- 现有 modelId → availability 映射

### T07-5.5 Public projection

- model-identities.json 加 additive optional 字段
- datasetVersion 变化（新内容参与 hash）

### T07-5.6 REST query

- `/api/v1/models` 返回新字段
- 未来 `/api/v1/upstream-models`（跨平台 query）

### T07-5.7 UI

- model detail 页展示 developer/platform/upstream
- 未来跨平台比较页（需跨平台数据源）

## 15. 哪些问题仍不能安全自动解决

1. **跨平台同模型判定**：`claude-sonnet-4.5` 在 Bedrock 和 Anthropic API 是否同一上游模型——需要官方文档证据，不能字符串匹配
2. **developer 与 platform 分离**：`alibaba` 是平台还是开发者——需要人工判定（阿里百炼=平台，阿里通义=开发者）
3. **snapshot vs 独立模型**：`qwen-flash-2025-07-28` 是 `qwen-flash` 的快照还是独立模型——当前标 pointer/unresolved，不自动归并
4. **family 跨平台**：`anthropic:claude-sonnet` 和未来 `bedrock:claude-sonnet` 的 family 关系——需要 upstream family 实体，不在本轮设计

---

## 关键设计决策

1. **modelId 保留不变**——新 ontology 是 additive
2. **推荐方案 B（独立实体+relation）**——为跨平台扩展打基础
3. **当前数据无跨平台同模型**——ontology 设计支持但不提前实现
4. **provider 语义拆分**——`alibaba`/`volcengine` 的平台≠品牌是主要冲突
5. **证据可审计**——跨平台关系需官方文档证据，禁止自动推断
6. **false positive = 0**——宁可 unresolved，不可错绑
