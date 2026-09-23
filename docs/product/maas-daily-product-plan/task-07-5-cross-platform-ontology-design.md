# T07-5 Cross-platform Model Ontology Design

日期：2026-09-23。状态：**设计阶段（不编码）**。

前置：T07-1～T07-4B 已 RELEASED。当前 `modelId = provider-scoped canonical observed identity`。

## 1. Current-state analysis

### 1.1 当前 provider namespace 实际语义

**修正（review 后）**：当前 `providerId`（modelId 前缀）**最准确的定义不是"平台"，也不是"开发者"，而是一个 public query namespace / 聚合命名空间**。它服务于现有 API 的 provider/sourceId 映射与 changes/prices 共用查询，不等于 Platform，也不等于 Developer。

`public_providers.json` 的 `sourceToProvider` 证明：多个 source 聚合到同一个 `providerId`。最明显的反例是 Google——8 个 source（google-gemini-blog/pricing/changelog/modellist + google-vertex-blog/pricing/changelog/modellist）全部映射成 `providerId = google`。因此 `google` 不能等价于 Gemini API，也不能等价于 Vertex AI，更不能简单定义成"开发者=平台合一"。它实际上把至少两个平台/产品面的 source 聚合到了一个 namespace 下。

各 namespace 的历史背景（**不是 ontology 定义，只是背景描述**）：

| providerId | displayName | 历史背景 | 模型品牌 |
|---|---|---|---|
| alibaba | 阿里百炼 | 聚合了阿里百炼平台 source | Qwen（通义千问） |
| volcengine | 火山方舟 | 聚合了火山方舟平台 source | Doubao（豆包） |
| zhipu | 智谱AI | 聚合了智谱开放平台 source | GLM |
| anthropic | Anthropic | 聚合了 Anthropic API source | Claude |
| openai | OpenAI | 聚合了 OpenAI API source | GPT |
| google | Google | 聚合了 Gemini API + Vertex AI source（8 个 source） | Gemini |
| deepseek | DeepSeek | 聚合了 DeepSeek API source | DeepSeek |
| kimi | Kimi | 聚合了 Kimi Platform source | Kimi/Moonshot |

**核心结论（修正）**：`providerId` 是历史兼容的 public query namespace，**不属于 T07-5 新 ontology 四实体中的任何一个**。T07-5 新增的是另一层更准确的实体关系（Developer / Platform / Upstream Model / Availability），`providerId` 继续服务现有 API（`modelId` / provider filter），不承担新 ontology 语义。

### 1.2 ledger provider vs canonical provider

ledger（pricing 数据源）用 **pricing provider**（`qwen`/`doubao`/`glm`），canonical 用 **providerId**（`alibaba`/`volcengine`/`zhipu`）。`public_providers.json` 的 `pricingProviderIdToProvider` 做映射。

两者都是 public query namespace 层面的映射，**不等价于 Developer 或 Platform**。ledger 的 pricing provider 更接近模型品牌（Qwen/Doubao/GLM），canonical 的 providerId 是聚合命名空间——但都只是 legacy namespace，不承担新 ontology 语义。

### 1.3 跨平台同模型现状待 T07-5.1 inventory 验证

**修正（review 后）**：之前文档写"对 ledger 2598 条 price 按 model_display_name 分组，零个模型名出现在多个 provider"——这一分析结果**在仓库内没有可复核的脚本或持久化产物**，属于 Agent 临时分析，不能作为 ontology 的硬前提。

T07-5.1 必须把这类统计正式产出成可复核 inventory（持久化脚本 + 结果文件 + Gold Set），而不是只写一句结论。

当前可以确认的仓库事实是：`sourceToProvider` 把 8 个 google source 聚合到 `providerId=google`，说明同一 namespace 下可能包含多个平台/产品面 source。因此 **modelId → Availability 的 cardinality 不能假设为 1:1**，T07-5.1 必须真正验证。

### 1.4 snapshot / pointer / preview

当前数据存在同一 namespace 内的变体，三类语义不同：

- **snapshot**：`qwen-flash-2025-07-28`（日期快照）、`qwen-flash`（基名）——registry 标 `type=snapshot`
- **pointer**：`qwen-plus-latest` 等带 `-latest`/`-next` 的串，registry 明确标 `classification=pointer`。pointer 具有时间性（指向目标随时间变化）
- **preview**：`gemini-3-flash-preview` 等——**ontology 语义未定**（evidence-driven unresolved）。当前 resolver 规定"禁止删除 -preview / 禁止指针猜测"只说明 identity resolver 不擅自合并，**不证明 preview 是 pointer，也不证明是独立 upstream model**

这些 identifier 不一定形成独立 public entity；pointer 被排除，snapshot/preview 语义由现有 identity 与 T07-5 evidence 分别处理。T07-5.1 需验证它们在新 ontology 中的归类。

## 2. Problem statement

当前 ontology 无法回答：

1. Claude Sonnet 4.5 在哪些平台可用？
2. 不同平台的 `claude-sonnet-4.5` 是否同一个上游模型？
3. `alibaba:qwen3-coder-plus` 的开发者是谁？（阿里通义，不是"阿里百炼"）
4. 同一上游模型在不同平台的价格事实有哪些？

根本问题：**当前 `providerId` 是 legacy public query namespace，不是 Developer 或 Platform**，且没有显式的"上游模型"实体。`providerId` 无法可靠回答跨平台/跨产品面的模型关系问题（Google namespace 同时聚合 Gemini API + Vertex AI source 是明确反例）。

## 3. Terminology

| 术语 | 定义 | 当前对应 |
|---|---|---|
| **Developer** | 模型的开发/拥有方（Anthropic, 阿里通义, 字节跳动, DeepSeek） | 部分隐含在 providerId |
| **Platform** | 模型被调用/销售的平台（Anthropic API, 阿里百炼, 火山方舟, Bedrock, Vertex） | 部分对应 providerId |
| **Upstream Model** | 跨平台稳定的模型实体（Claude Sonnet 4.5, Qwen3 Coder Plus） | 不存在 |
| **Availability** | 某 upstream model 在某 platform 上的可用关系；observed identifiers 为 1:N；region/status 是否属于 Availability 属性由 T07-5.1 验证 | 不存在 |
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
availabilityId: "anthropic-api:claude-sonnet-4.5" / "alibaba-bailian:qwen-plus"
upstreamModelId: "anthropic:claude-sonnet-4.5"
platformId: "anthropic-api" / "alibaba-bailian"
observedIdentifiers: [  // 1:N（一个 availability 可有多个 observed identifier）
  { value: "qwen-plus", type: "canonical" },
  { value: "qwen-plus-2025-07-28", type: "snapshot" },
  { value: "qwen-plus-latest", type: "pointer" }  // pointer 需带时间性（见 §12）
]
region: "global" / "cn"
status: "active" / "deprecated"
```

**修正（review 后）**：Availability 的 observed identifier 是 **1:N**，不是单值 `modelKey`。registry 里 `alibaba:qwen-plus` 下同时存在 `qwen-plus`、`qwen-plus-2024-12-20`、`qwen-plus-2025-01-12`、`qwen-plus-2025-07-28` 等，registry 标 `type=snapshot`。这证明一个 availability 显然可以有多个 observed identifier。

## 5. Candidate relations

```
Developer ──develops──→ Upstream Model
Upstream Model ──available on──→ Platform (via Availability)
Availability ──has observedIdentifiers[]──→ raw API strings (1:N)
existing modelId ──maps to──→ Availability (cardinality 待 T07-5.1 验证，不假设 1:1)
```

**修正（review 后）**：`existing modelId → Availability` 的 cardinality **不假设 1:1**。如 `google:gemini-2.5-pro` 可能对应 Gemini API + Vertex AI 两个 availability，T07-5.1 必须验证。

## 6. Real-data examples

### 10 个代表性模型 ontology mapping

| Current modelId | Developer | Upstream model | Platform | Observed modelKey |
|---|---|---|---|---|
| anthropic:claude-sonnet-4.5 | Anthropic | Claude Sonnet 4.5 | Anthropic API | claude-sonnet-4.5 |
| anthropic:claude-opus-5 | Anthropic | Claude Opus 5 | Anthropic API | claude-opus-5 |
| openai:gpt-6-astra | OpenAI | GPT-6 Astra | OpenAI API | gpt-6-astra |
| openai:gpt-5.6-sol | OpenAI | GPT-5.6 Sol | OpenAI API | gpt-5.6-sol |
| google:gemini-2.5-pro | Google | Gemini 2.5 Pro | Gemini API / Vertex AI candidates，mapping/cardinality unresolved | gemini-2.5-pro |
| google:gemini-3-flash-preview | Google | Gemini 3 Flash Preview | Gemini API / Vertex AI candidates，mapping/cardinality unresolved | gemini-3-flash-preview |
| alibaba:qwen3-coder-plus | 阿里通义 | Qwen3 Coder Plus | 阿里百炼 | qwen3-coder-plus |
| alibaba:qwen3-coder-plus | 阿里通义 | Qwen3 Coder Plus | 阿里百炼 | qwen3-coder-plus-2025-07-22 (snapshot) |
| volcengine:doubao-seed-1.6 | 字节跳动 | Doubao Seed 1.6 | 火山方舟 | doubao-seed-1.6 |
| zhipu:glm-4.7 | 智谱 | GLM 4.7 | 智谱开放平台 | glm-4.7 |
| deepseek:deepseek-v4-pro | DeepSeek | DeepSeek V4 Pro | DeepSeek API | deepseek-v4-pro |
| kimi:kimi-k3 | Moonshot AI | Kimi K3 | Kimi Platform | kimi-k3 |

**关键观察（candidate mapping，尚未经 T07-5.1 Gold Set/evidence 验证）**：
- 上述 mapping 是基于现有数据的**候选映射**，不是 verified ontology relation
- "developer=platform"与"平台≠品牌"并存说明 `providerId` 不能可靠决定 Developer 或 Platform——Google namespace（Gemini API + Vertex AI）是更明确的反例
- snapshot（`qwen3-coder-plus-2025-07-22`）是同一 availability 的 observed identifier 候选，不是独立 upstream model 候选——但 T07 registry classification ≠ 自动成为 T07-5 ontology truth，仍需 evidence 验证
- **跨平台同模型 cardinality 未经验证**——T07-5.1 必须正式产出可复核 inventory，不能基于此候选表假设

## 7. Proposed schema

### 方案 B：独立实体 + relation（推荐）

```
data/model-registry/
  developers.json      # Developer 实体
  platforms.json       # Platform 实体
  upstream-models.json # Upstream Model 实体
  models.json          # 现有（保留 modelId）
  availabilities.json  # Availability relation（upstreamModelId × platformId + observedIdentifiers[]）
```

**现有 models.json 变更（additive，但 mapping schema 标为 T07-5.1 pending）**：

```json
{
  "modelId": "alibaba:qwen3-coder-plus",  // 保留不变
  "providerId": "alibaba",                 // 保留不变（legacy namespace）
  "upstreamModelId": "alibaba-qwen:qwen3-coder-plus",  // 新增候选（additive，待 T07-5.1 验证）
  "developerId": "alibaba-qwen",           // 新增候选（additive，待 T07-5.1 验证）
  "platformId": "alibaba-bailian",         // 新增候选（additive，待 T07-5.1 验证）
  "canonicalName": "Qwen3 Coder Plus",     // 保留
  "familyId": "alibaba:qwen-coder",        // 保留
  "classification": "model",              // 保留
  "aliases": [...]                         // 保留
}
```

**注意**：`upstreamModelId` / `developerId` / `platformId` 是单值还是多值（如 `availabilityIds[]`），由 T07-5.1 cardinality 结果决定。如果 `google:gemini-2.5-pro` 对应多个 availability，则 `models.json` 可能需要 `availabilityIds[]` 或独立 relation 文件，而不是单值 `platformId`。**现阶段不固定 mapping schema**。

### Availability relation 设计候选

```
Availability
  = upstreamModelId × platformId
  + observedIdentifiers[]  (1:N，含 modelKey/snapshot/pointer/SKU)
  + region / status
```

**修正（review 后）**：Availability 的 observed identifier 是 **1:N**（registry 里 qwen-plus 下有多个 snapshot 证明），不是单值 `modelKey`。具体唯一性与 cardinality 由 T07-5.1 决定。

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

**推荐方案 B**：当前跨平台覆盖情况尚未形成可复核 inventory，但方案 B 的实体分离让未来扩展自然——新增 Bedrock Claude 只需加 availability，不需改 upstream model。方案 A 在跨平台场景会产生 `anthropic:claude-sonnet-4.5` 和 `bedrock:claude-sonnet-4.5` 两个 modelId，关联关系隐含在字段里，查询不便。

## 9. Migration strategy

### Phase 1：只加实体，不改现有行为

1. 新增 `developers.json` / `platforms.json` / `upstream-models.json` / `availabilities.json`
2. 现有 `models.json` 的 mapping 字段（`upstreamModelId`/`developerId`/`platformId` 单值还是 `availabilityIds[]` 多值）**待 T07-5.1 cardinality 验证后确定**，不预先固定 schema
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

- snapshot（`qwen3-coder-plus-2025-07-22`）：T07 registry 已将其标为 `alibaba:qwen3-coder-plus` 的 `type=snapshot` alias。但 **T07 registry classification ≠ 自动成为 T07-5 ontology truth**——T07-5.1 仍需验证 snapshot alias 对应 upstream/availability 的 evidence，不能仅凭 T07 classification 自动归入同一 Availability
- pointer（`qwen-plus-latest`）：指向某个 upstream model，但本身不是 upstream model。**pointer 具有时间性**——`latest` 指向的目标会随时间变化，因此 pointer → target 必须考虑 `observedAt` / `validFrom` / `validTo`，不能只做 `pointer → upstreamModelId` 静态映射
- preview（`gemini-3-flash-preview`）：**ontology 语义未定**（修正——不能固定为"独立 upstream model"）：
  - 有官方证据证明是独立版本 → independent upstream model
  - 只是 endpoint / lifecycle label → variant / availability identifier
  - 证据不足 → unresolved
  - 当前 resolver 规定"禁止删除 -preview / 禁止指针猜测"只说明 identity resolver 不擅自合并，**不证明 preview 一定是独立 upstream model**
- emoji/噪音（`deepseek-flash-(1)`）：extractor 噪音，不进入 ontology
- **跨平台同模型当前无可靠 inventory**：Bedrock/Vertex 的 Claude/Gemini 是否在当前数据源内待 T07-5.1 正式盘点——ontology 设计应支持但不提前实现

## 13. Risks

1. **provider 语义拆分风险**：`alibaba`→`alibaba-qwen`(developer) + `alibaba-bailian`(platform) 可能影响现有 provider filter 语义——需保持 `providerId` 不变，只加新字段
2. **跨平台 false positive 风险**：`claude-sonnet-4.5` 在不同平台的 modelKey 可能不同（如 Bedrock 用 `anthropic.claude-sonnet-4.5`），不能自动字符串匹配
3. **数据源覆盖风险**：当前跨平台覆盖情况尚未形成可复核 inventory，仓库已有 Gemini/Vertex 两组 source，实际模型与价格覆盖待 T07-5.1 inventory
4. **registry 维护成本**：新增 4 个实体文件增加维护负担——可以基于现有数据生成 candidate mapping，但 candidate ≠ verified ontology relation。Google namespace 已证明 `providerId` 不能可靠决定 platform，正式 registry 必须经过 Gold Set / evidence gate

## 14. Recommended implementation phases

### T07-5.1 Ontology inventory + Gold Set

- 盘点现有 107 个 model 的 developer/platform/upstream 映射
- 建 Gold Set（10-15 个代表，含 alibaba/volcengine 平台≠品牌案例）
- 不改代码

### T07-5.2 Developer / Platform registry

- 新增 `developers.json` / `platforms.json`
- 基于现有数据生成 candidate developer/platform 实体（8-16 个候选），candidate ≠ verified，正式 registry 必须经过 Gold Set / evidence gate
- validator + 测试

### T07-5.3 Upstream Model registry

- 新增 `upstream-models.json`
- 基于现有 modelId 生成 candidate upstream model（107 个候选），candidate ≠ verified，必须经过 Gold Set / evidence gate
- developer 关联

### T07-5.4 Availability relation

- 新增 `availabilities.json`
- 关联 upstreamModel × platform + observedIdentifiers[]（1:N）
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
3. **snapshot vs 独立模型**：`qwen-flash-2025-07-28` 是 `qwen-flash` 的快照还是独立模型——registry 标为 `type=snapshot` alias，但 T07 registry classification ≠ 自动成为 T07-5 ontology truth，不自动归并
4. **family 跨平台**：`anthropic:claude-sonnet` 和未来 `bedrock:claude-sonnet` 的 family 关系——需要 upstream family 实体，不在本轮设计

---

## 关键设计决策

1. **modelId 保留不变**——新 ontology 是 additive
2. **推荐方案 B（独立实体+relation）**——为跨平台扩展打基础
3. **providerId 是 legacy public query namespace**——不属于新 ontology 四实体（Developer/Platform/Upstream Model/Availability），继续服务现有 API，不承担新 ontology 语义
4. **modelId → Availability cardinality 不假设 1:1**——T07-5.1 必须验证（google namespace 下含 Gemini API + Vertex AI 两个平台 source）
5. **Availability 的 observed identifier 是 1:N**——不是单值 modelKey（registry 里 qwen-plus 下有多个 snapshot 证明）
6. **preview ontology 语义未定**——evidence-driven，不固定为"独立 upstream model"
7. **pointer 具有时间性**——pointer → target 需考虑 observedAt/validFrom/validTo，不能做静态映射
8. **证据可审计**——跨平台关系需官方文档证据，禁止自动推断
9. **false positive = 0**——宁可 unresolved，不可错绑

### 修正后的基础模型

```
Legacy Provider Namespace (providerId)
        │
        │ compatibility mapping（继续服务现有 API，不属于新 ontology）
        ▼
Current modelId
        │
        ├───────────────┐
        ▼               ▼
Upstream Model      Availability
        │               │
        ▼               ▼
Developer          Platform
                        │
                        ▼
              Observed Identifiers (1:N)
              modelKey / snapshot / pointer / SKU
```

**关键变化**：`providerId` 不属于新 ontology 四实体中的任何一个。它是历史兼容 namespace，继续服务现有 API（`modelId` / provider filter）。T07-5 新增的是另一层更准确的实体关系。

### T07-4B 技术债记录（T07-5.5/UI 阶段处理）

`/model/[modelId].astro` 里有手写 `providerLabels` map + `model.modelId.split(':')[0]`——这在 T07-4B 还能工作（展示 legacy provider namespace），但 T07-5 后不能继续当成 Platform 或 Developer。T07-5.5/UI 阶段必须移除这种语义依赖。

---

## Review 修订记录（2026-09-23）

基于仓库实际代码和数据结构 review，修正四点：

1. **providerId 定义修正**：从"平台/开发者混合"改为"legacy public query namespace / 聚合命名空间"——google 8 个 source（gemini + vertex）全部聚合到 `providerId=google` 证明它不是平台也不是开发者，而是聚合命名空间
2. **modelId → Availability cardinality 修正**：从"1:1"改为"不假设 1:1，T07-5.1 验证"——google namespace 含 Gemini API + Vertex AI 两个平台 source，modelId 可能对应多个 availability
3. **Availability modelKey 修正**：从"单值 modelKey"改为"1:N observedIdentifiers"——registry 里 qwen-plus 下有多个 snapshot 证明一个 availability 有多个 observed identifier
4. **preview 结论修正**：从"独立 upstream model"改为"evidence-driven unresolved"——resolver 规定"禁止删除 -preview"只说明不擅自合并，不证明 preview 一定是独立 upstream model
5. **跨平台同模型统计修正**：从"零个模型名出现在多个 provider（不可复核的 Agent 分析）"改为"T07-5.1 必须正式产出可复核 inventory"

**pointer 时间性补充**：pointer（如 `qwen-plus-latest`）指向的目标会随时间变化，pointer → target 必须考虑 `observedAt` / `validFrom` / `validTo`，不能做静态映射。

### 第二轮 Review 修订（文档一致性收口）

基于仓库实际代码复审，清理 6 处旧语义残留：

1. **§1.2 / §2**：删除"canonical provider 更接近平台""provider 同时承载平台和开发者语义"。统一定义 `providerId = legacy public query / source aggregation namespace ≠ Developer ≠ Platform`
2. **§1.4**：把 `gemini-3-flash-preview` 从 pointer 示例移出。snapshot / pointer / preview 分别描述，preview ontology semantic = unresolved / evidence-driven
3. **§6**：删除"当前数据全部 developer=platform""当前无跨平台同模型数据"等未经 inventory 验证的结论。表格改为 candidate mapping examples，明确待 T07-5.1 Gold Set/evidence 验证
4. **§7 / §9**：models.json 不固定单值 `availabilityId`/`platformId`（mapping schema 标为 T07-5.1 pending）。availabilities.json 从 `upstreamModelId × platformId × modelKey` 改为 `upstreamModelId × platformId + observedIdentifiers[]`（1:N）
5. **§13 / T07-5.2 / T07-5.3**：删除"provider → developer/platform 可自动推断""107 upstream model 可直接从 modelId 推断"。统一改为"candidate generation ≠ verified mapping，正式 registry 必须经过 Gold Set / evidence gate"
6. **§15 snapshot**：修正 `qwen-flash-2025-07-28` 当前状态——registry 实际标为 `type=snapshot` alias（不是 pointer/unresolved）。明确"T07 registry classification ≠ 自动成为 T07-5 ontology truth"
