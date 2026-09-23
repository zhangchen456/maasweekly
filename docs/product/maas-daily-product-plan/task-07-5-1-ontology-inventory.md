# T07-5.1 Ontology Inventory + Gold Set

日期：2026-09-23。状态：**Inventory 完成（correction pass），Gold Set 建立，分析完成**。

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

脚本从仓库真实数据生成 inventory，不依赖临时分析。datasetVersion / dataThrough / changes / prices 等数字全部从 manifest 与 release 文件读取，写入 result，不人工写死。

## 输入文件

- `data/model-registry/models.json`（registry：107 model + 24 family + 7 pointer）
- `pipeline/config/public_providers.json`（sourceToProvider / pricingProviderIdToProvider）
- `pipeline/config/maas_official_sources.json`（17 platform metadata，含 vendor 字段）
- `data/public/v1/releases/<datasetVersion>/model-identities.json`（catalog：107 models / 24 families）
- `data/public/v1/releases/<datasetVersion>/changes.json`（manifest coverage.count 行 changes）
- `data/public/v1/releases/<datasetVersion>/prices.json`（manifest coverage.facts 行 prices）
- `site/src/data/pricing/ledger.json`（ledger prices，含 source_url）

**注意**：changes/prices 行数由脚本从 release 文件读取并写入 result，不人工写死。当前 release 的数字见 inventory result `stats.release`。

## 107 model inventory coverage

| 维度 | 结果 |
|---|---|
| publicModels | 107 |
| 有 price/change 记录 | 106 |
| 无记录（known-but-empty） | 1（`deepseek:deepseek-flash`） |

## developer candidate entities / mappings

| 维度 | 数量 |
|---|---|
| candidate developer entities | 8 |
| model→developer candidate mappings | 107 |
| unresolved mappings | 0 |

**注意**：8 是 unique candidate developer entities 数，107 是 model→developer mapping 数。两者是不同指标。全部是 candidate（从 providerId 推断），candidate ≠ verified。Gold Set 覆盖 10 个代表，0 个 developer relation verified，8 个 candidate，2 个 unresolved。

## upstream candidate entities / mappings

| 维度 | 数量 |
|---|---|
| candidate upstream entities | 107 |
| model→upstream candidate mappings | 107 |
| unresolved mappings | 0 |

107 个 upstream entity（每个 model slug 唯一，entity 数 = mapping 数）。全部是 candidate。

## source footprint cardinality（不是 availability cardinality）

| source footprint | 数量 |
|---|---|
| single-source-footprint | 106 |
| no-data | 1 |
| multi-source-footprint | 0 |

**重要**：这是 **observed source footprint**（identity-bearing records 实际来自哪些 source），**不是 availability cardinality**。source footprint != Platform；1 个 source footprint 不等于 1 个 availability。

## availability cardinality

| 状态 |
|---|
| **unresolved** — source footprint != availability；不可从现有数据直接推出 |

**修正（review 后）**：之前版本写"1:N 不存在""modelId → Availability 1:1"——这是把 source footprint 提升成了 availability 事实，证据不足。source footprint 只证明 identity-bearing records 来自 1 个 source family，不证明 model 只在 1 个 platform 有 1 个 availability。

正确状态：availability cardinality = **unresolved**，尚不能从现有数据直接推出。

## Google Gemini/Vertex 实际结果

| 维度 | 数量 |
|---|---|
| Google total | 14 |
| Gemini source footprint only | 14 |
| Vertex source footprint only | 0 |
| Both source footprints | **0** |
| No source footprint | 0 |

**修正（review 后）**：这是 **observed source footprint**（14 个 Google model 的 identity-bearing records 全部来自 `google-gemini-pricing` source，0 个来自 `google-vertex-*` source）。**这不等于"只存在于 Gemini API 不存在于 Vertex AI"**——platform mapping 仍需官方文档验证。

## 是否真实发现 1:N availability

**unresolved**。当前数据只证明 source footprint 是 1:1（106 个有 1 个 source footprint），但 source footprint != availability。不能从 source footprint 1:1 推出 availability 1:1。

## 哪些 model 当前无法区分 platform

全部 107 个 model 的 platform 都是 **candidate / unresolved**。source footprint 清晰（106 个有 1 个 source footprint），但 source footprint != Platform——Platform 需独立验证。Google 14 个 model 虽全部来自 Gemini source，但 platform mapping（gemini-api vs vertex-ai）unresolved。

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

**修正（review 后）**：当前仓库只提供 price-fact-level evidence（region 是 price fact 条件维度）。**是否属于 Availability ontology = unresolved**——"没有证据支持它属于"不能转换成"证据证明它不属于"。第一版 core Availability identity 不应包含 region（保守），但未来如果模型只在某些 region 可调用，region 可能成为 Availability 覆盖范围属性。

## status 是否属于 Availability

| 维度 | 结果 |
|---|---|
| availability status 数据 | 无 |
| field_state 值 | confirmed / stale（数据质量状态） |

**结论**：**not evidenced / unresolved**——当前仓库无 availability 层面 status 数据。"没有证据支持"不能转换成"证据证明它不属于"。

## developerId namespace 推荐

| providerId | candidateDeveloperId | 说明 |
|---|---|---|
| anthropic | anthropic | developer=platform 候选 |
| openai | openai | developer=platform 候选 |
| google | google | developer=platform 候选（但 platform 含 Gemini+Vertex，待验证） |
| deepseek | deepseek | developer=platform 候选 |
| kimi | moonshot-kimi | developer(Moonshot AI) ≠ brand(Kimi) 候选 |
| zhipu | zhipu | developer=platform 候选 |
| alibaba | alibaba-qwen | developer(阿里通义) ≠ platform(阿里百炼) 候选 |
| volcengine | bytedance-doubao | developer(字节跳动) ≠ platform(火山方舟) 候选 |

**命名规则**：`developerId` 用 `<company>-<brand>` 格式（如 `alibaba-qwen`、`bytedance-doubao`），developer=platform 时用单一名（如 `anthropic`、`openai`）。

## upstreamModelId namespace 推荐

**命名规则**：`<developerId>:<model-slug>`（如 `alibaba-qwen:qwen3-coder-plus`、`anthropic:claude-sonnet-4.5`）。

**碰撞分析**：当前 107 个 model 的 slug 在 developer 范围内唯一，无碰撞。但跨 developer 可能存在同名 slug——developerId 前缀避免碰撞。

## 是否发现四实体模型反例

**否**。当前数据不推翻四实体模型。但关键修正：**availability cardinality = unresolved**（不是 1:1）。source footprint 是 1:1，但 source footprint != availability。

## 是否需要修改 T07-5 ontology design

**不需要**。设计文档的四实体模型和 cardinality 待验证的立场仍然成立。关键修正：

- availability cardinality = unresolved（source footprint 1:1 不等于 availability 1:1）
- Availability 的 observedIdentifiers 是 1:N（25 个 model 有多 modelKey）
- pointer 需独立 temporal relation，不是普通 observedIdentifier
- region/status = unresolved（不是"不属于"）

## 哪些 mapping 仍 unresolved

1. 全部 107 个 model 的 availability cardinality = unresolved
2. Google 14 model 的 platform mapping（gemini-api vs vertex-ai）
3. 3 个 preview model 的 ontology 语义
4. 107 个 developer/upstream 全部是 candidate（0 verified）
5. pointer → target temporal relation
6. region/status 是否属于 Availability = unresolved

## Gold Set verification summary

| relation | verified | candidate | unresolved |
|---|---|---|---|
| developer | 0 | 8 | 2 |
| platform | 0 | 6 | 4 |
| availability | 0 | 0 | 10 |
| identifier | 7 | 0 | 3 |

repo-derived candidate ≠ verified relation；availability 全部 unresolved（source footprint != availability）。

## git status

工作区干净（待 commit + push）。

## 确认

- 是否修改 production behavior：**NO**
- 是否修改 public schema：**NO**
- 是否 merge main：**NO**
- 是否 production deploy：**NO**
