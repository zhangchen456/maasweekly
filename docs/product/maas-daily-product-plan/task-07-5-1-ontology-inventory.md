# T07-5.1 Ontology Inventory + Gold Set

日期：2026-09-23。状态：**Inventory 完成，Gold Set 建立，分析完成**。

前置：T07-5 Ontology Design FINAL PASS（commit `784948f6a`）。

## 产物

| 产物 | 路径 |
|---|---|
| Inventory 脚本 | `pipeline/scripts/ontology-inventory.py` |
| Inventory 结果 | `docs/product/maas-daily-product-plan/task-07-5-1-ontology-inventory.json` |
| Gold Set | `docs/product/maas-daily-product-plan/task-07-5-1-ontology-gold-set.json` |
| 分析文档 | 本文 |

## 可复核命令

```bash
python3 pipeline/scripts/ontology-inventory.py
```

脚本从仓库真实数据生成 inventory，不依赖临时分析。

## 输入文件

- `data/model-registry/models.json`（registry：107 model + 24 family + 7 pointer）
- `pipeline/config/public_providers.json`（sourceToProvider / pricingProviderIdToProvider）
- `pipeline/config/maas_official_sources.json`（17 platform metadata，含 vendor 字段）
- `data/public/v1/releases/<datasetVersion>/model-identities.json`（catalog：107 models / 24 families）
- `data/public/v1/releases/<datasetVersion>/changes.json`（4993 changes）
- `data/public/v1/releases/<datasetVersion>/prices.json`（1425 prices）
- `site/src/data/pricing/ledger.json`（2598 ledger prices，含 source_url）

## 107 model inventory coverage

| 维度 | 结果 |
|---|---|
| publicModels | 107 |
| 有 price/change 记录 | 106 |
| 无记录（known-but-empty） | 1（`deepseek:deepseek-flash`） |

## developer verified/candidate/unresolved

| 状态 | 数量 | 说明 |
|---|---|---|
| candidate | 107 | 全部从 providerId 推断候选（candidate ≠ verified） |
| unresolved | 0 | — |

**注意**：developer 全部是 candidate（从 providerId 推断），没有 Gold Set verified 的批量 mapping。Gold Set 覆盖 10 个代表，其中 8 个有 evidence 的 developer mapping。

## upstream verified/candidate/unresolved

| 状态 | 数量 |
|---|---|
| candidate | 107（developer:model-slug 格式） |
| unresolved | 0 |

## platform cardinality 分布

| cardinality | 数量 | 说明 |
|---|---|---|
| 1（candidate） | 106 | 1 个 candidate platform |
| 0 | 1 | `deepseek:deepseek-flash`（无 price/change 记录） |
| 2+ | **0** | **没有 1:N availability** |

**关键结论：modelId → Availability cardinality 全部是 1（或 0），没有 1:N**。

## modelId → availability cardinality 分布

```
0 availability: 1（deepseek:deepseek-flash，known-but-empty）
1 availability: 106
2+ availabilities: 0
```

**1:N 不存在**。当前数据中，每个有记录的 modelId 只在一个 source/platform footprint 出现。

## Google Gemini/Vertex 实际结果

| 维度 | 数量 |
|---|---|
| Google total | 14 |
| Gemini source only | 14 |
| Vertex source only | 0 |
| Both sources | **0** |
| No source footprint | 0 |

**关键结论**：虽然 `providerId=google` 聚合了 8 个 source（gemini + vertex），但 14 个 Google model 的 price/change 记录**全部来自 `google-gemini-pricing` source，0 个来自 Vertex source**。Google namespace 下的 model 没有出现 1:N availability。

**但**：providerId=google 同时聚合 Gemini API 和 Vertex AI 两组 source 是事实。platform mapping（gemini-api vs vertex-ai）仍需官方文档验证——当前数据无法区分 model 实际在哪个 platform 可用，只能确认 source footprint。

## 是否真实发现 1:N availability

**否**。当前数据中 modelId → availability 全部是 1:1（或 0:0）。Google 虽然有 8 个 source，但实际 model 数据全部来自 Gemini source。

## 哪些 model 当前无法区分 platform

全部 107 个 model 的 platform 都是 **candidate**（从 source footprint 推断），不是 verified。但 source footprint 清晰：106 个有 1 个 source footprint，1 个无记录。

Google 14 个 model 虽然全部来自 `google-gemini-pricing`，但 `providerId=google` 聚合了 Gemini API + Vertex AI——**platform 是 Gemini API 还是 Vertex AI 需官方文档验证**，当前数据无法区分。

## observedIdentifiers cardinality

| cardinality | 数量 |
|---|---|
| single（1 modelKey） | 81 |
| multiple（2+ modelKeys） | 25 |
| zero | 1 |

25 个 model 有多个 observed modelKey（含 snapshot 变体）。

## snapshot 结果

| 维度 | 数量 |
|---|---|
| snapshot alias 总数 | 43 |
| 有 snapshot 的 model 数 | 23 |

23 个 model 有 snapshot alias（如 `qwen-plus` 下有 `qwen-plus-2025-07-28` 等）。T07 registry 标 `type=snapshot`，但 **T07 classification ≠ 自动成为 T07-5 ontology truth**——snapshot 是否属于同一 Availability 的 observedIdentifier 需 evidence 验证。

## pointer 结果

7 个 pointer（registry `classification=pointer`）。pointer 不进入 public catalog。pointer 具有时间性（`latest` 指向目标随时间变化），不适合作为 Availability 的普通 observedIdentifier——pointer → target 需 temporal relation（observedAt/validFrom/validTo），与普通 identifier 属于不同 relation 层。

## preview 结果

3 个 preview model（含 `gemini-3-flash-preview`）。preview ontology 语义未定（evidence-driven unresolved）：可能是独立 upstream model、lifecycle variant 或 availability identifier。需官方文档验证。

## region 是否属于 Availability

| 维度 | 结果 |
|---|---|
| 有多 region 的 model 数 | 33 |
| 样例 | `alibaba:qwen-plus`: ['cn', 'global'] |

**结论**：region 出现在 price fact 中，同一 modelId 有多 region。region 更可能是 **price fact condition**（价格条件）而非 Availability 属性。同一 model 在同一 platform 上的不同 region 属于同一 Availability，只是价格条件不同。**region 不应作为 Availability 属性**（待 Gold Set 最终验证，但当前数据支持此结论）。

## status 是否属于 Availability

当前数据中没有模型 availability 层面的 `status` 字段（active/deprecated）。price fact 有 `field_state`（confirmed/stale），但那是数据质量状态，不是模型 availability。**status 不应作为 Availability 属性**——当前数据无支持。

## developerId namespace 推荐

| providerId | candidateDeveloperId | 说明 |
|---|---|---|
| anthropic | anthropic | developer=platform |
| openai | openai | developer=platform |
| google | google | developer=platform（但 platform 含 Gemini+Vertex，待验证） |
| deepseek | deepseek | developer=platform |
| kimi | moonshot-kimi | developer(Moonshot AI) ≠ brand(Kimi) |
| zhipu | zhipu | developer=platform |
| alibaba | alibaba-qwen | developer(阿里通义) ≠ platform(阿里百炼) |
| volcengine | bytedance-doubao | developer(字节跳动) ≠ platform(火山方舟) |

**命名规则**：`developerId` 用 `<company>-<brand>` 格式（如 `alibaba-qwen`、`bytedance-doubao`），developer=platform 时用单一名（如 `anthropic`、`openai`）。

## upstreamModelId namespace 推荐

**命名规则**：`<developerId>:<model-slug>`（如 `alibaba-qwen:qwen3-coder-plus`、`anthropic:claude-sonnet-4.5`）。

**碰撞分析**：当前 107 个 model 的 slug 在 developer 范围内唯一，无碰撞。但跨 developer 可能存在同名 slug（如 `qwen-plus` 在 alibaba-qwen 下）——developerId 前缀避免碰撞。

**rename 风险**：现有 modelId（`alibaba:qwen3-coder-plus`）与 candidate upstreamModelId（`alibaba-qwen:qwen3-coder-plus`）不同——mapping 需保持 modelId 不变，upstreamModelId 是 additive。

## 是否发现四实体模型反例

**否**。当前数据不推翻四实体模型（Developer / Platform / Upstream Model / Availability）。关键发现：

1. **1:N availability 不存在**——当前数据支持 modelId → Availability 1:1（可保持 schema 简单）
2. **Google 1:N 预期未发生**——14 个 Google model 全部只在 Gemini source 出现（但 platform mapping 需验证）
3. **region 是 price fact condition**，不是 Availability 属性
4. **pointer 需 temporal relation**，不适合作为普通 observedIdentifier

## 是否需要修改 T07-5 ontology design

**不需要**。设计文档的四实体模型和 cardinality 待验证的立场仍然成立。关键修正：

- modelId → Availability 当前是 1:1，可保持 schema 简单（单值 `platformId` 可行）
- 但 Google namespace 的 platform mapping 仍需官方文档验证（candidate ≠ verified）
- Availability 的 observedIdentifiers 是 1:N（25 个 model 有多 modelKey，含 snapshot）
- pointer 需独立 temporal relation，不是普通 observedIdentifier
- region/status 不属于 Availability，属于 price fact

## 哪些 mapping 仍 unresolved

1. Google 14 个 model 的 platform mapping（gemini-api vs vertex-ai）——需官方文档
2. 3 个 preview model 的 ontology 语义——需官方文档
3. 107 个 developer/upstream mapping 全部是 candidate——需 Gold Set 扩展验证
4. pointer → target temporal relation——需 T07-5.4 设计

## tests / validation

inventory 脚本可重复执行：
```bash
python3 pipeline/scripts/ontology-inventory.py
```

输出持久化到 `task-07-5-1-ontology-inventory.json`，可 diff/review。

Gold Set 10 条覆盖：developer=platform / developer≠platform / multi-source namespace / multiple modelKeys / snapshot / pointer / preview / unresolved / known-but-empty。

## git status

工作区干净（待 commit + push）。

## 确认

- 是否修改 production behavior：**NO**
- 是否修改 public schema：**NO**
- 是否 merge main：**NO**
- 是否 production deploy：**NO**
