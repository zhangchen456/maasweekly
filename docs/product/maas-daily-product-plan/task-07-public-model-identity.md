# Task 07：Public Model Identity + Structured Query Contract（T07-3 设计文档）

日期：2026-09-21。前置：T07-1（盘点）+ T07-2（Registry + Resolver）+ T07-2.5（Coverage 补录）。

## 1. modelKey 与 modelId 的区别

```
modelKey   = 来源数据中的原始模型标识（永远保留）
modelId    = MaaS Daily 维护的稳定模型实体 ID（provider:canonicalSlug）
modelName = registry.canonicalName（人类可读，允许未来改名不影响 modelId）
familyId  = 正式注册的模型家族 ID（family 改名不改既有 modelId）
```

原始 `modelKey` 永远保留；`modelId`/`modelName`/`familyId` 是 `projector` 经 resolver
投影后的 additive optional fields。**没有 modelId 优于错误 modelId。**

## 2. Public Family Contract

**正式 family（4→24 →7→24）**：
- 升级有明确产品语义的 grouping key（如 qwen3-coder、doubao-seed-1.6、claude-opus、
  gemini-2.5、glm-4.7、qwen3、gemini-omni 等）为正式 `classification=family` 实体。
- **validator `public-family-reference-complete`**：model 实体引用的 `familyId` 必须有
  正式 entity（否则该 `familyId` 不得对外发布）。

## 3. Model Identity Projection 规则（exporter → prices/changes/items）

`pipeline/model_identity/projector.py`（`project_model_identity` 是唯一入口）。

| resolver 状态 | 公开字段 |
|---|---|
| resolved | modelId + modelName（正式 family 则附 familyId/familyName） |
| family | familyId + familyName（正式 family 时；否则空） |
| pointer | 空（保留调用方的 modelKey，不冒充 family） |
| ambiguous / unresolved | 空（字段 omit） |

## 4. Pointer 行为

`-latest`/`-next`/阿里 `-preview` 在 resolver 中标 `resolutionType=pointer`——
公开投影不写 modelId 也不写 familyId。`pointer ≠ family`（测试锁定）。
旧 `model=` 参数语义不变（backward compat 红线）。

## 5. REST 新增 structured filters

- `?modelId=<canonicalProviderId>:<canonicalSlug>`：精确匹配（如
  `alibaba:qwen3-coder-plus`）。
- `?familyId=<providerId>:<familySlug>`：精确匹配（只匹配正式 family）。
- 未知 `modelId`/`familyId` → 400 `invalid_model_id`/`invalid_family_id`（不静默）。
- 合法但无记录 → 200 + empty items。
- 旧 `?model=` 语义保留（=原始 modelKey 字符串精确匹配）。

## 6. MCP

`maas_get_changes` / `maas_get_prices` 新增 optional `modelId` / `familyId` 参数，
与 REST 共用 query core。示例：「查询 `anthropic:claude-sonnet-4.5` 的价格」→
`modelId` 精确 filter。

## 7. datasetVersion 规则

- 同输入 + 同 registry → datasetVersion 稳定。
- 修改实际被公开引用的 model identity → datasetVersion 改变（如 familyName 去后缀、
  alias 增删不影响；但 modelId/familyId 的投影字段变化才算）。
- registry 中仅 notes/家族增补（未进投影）→ 不应仅因此改变 datasetVersion。

## 8. Backward compatibility

- 旧 `?model=` 语义不变（`modelKey` 精确匹配）。
- 旧消费者忽略新字段（`modelId`/`modelName`/`familyId`/`familyName`）仍正常工作。
- unresolved/pointer/ambiguous 不伪造 modelId——`projector` 返回空对象。
- source_observation（244 条无结构化模型）不经 helper——天然不写 modelId。

## 9. Build Gate（exporter fail closed）

`projector.verify_projection` 在 `exporter.build_release` 内累计违规——
`_mi_gate_errors`——非零即 `ExportError`、正式目录零写入。

## 10. 验证命令与 status

```
python3 pipeline/scripts/validate-model-registry.py          # 12+2 项零违规
python3 pipeline/scripts/audit-model-registry-coverage.py  # unresolved 分层
python3 -m unittest discover -s tests -p 'test_model_registry.py'         # 30 项
python3 -m unittest discover -s tests -p 'test_model_identity_audit.py'   # 16 项
python3 -m unittest discover -s tests -p 'test_model_public_projection.py' # 11 项
./scripts/run-all-tests.sh                                   # 26/26
```

## 11. 真实数据验收

- **prices**：1387 条 — 有 modelId 859（62%）、familyId 564
- **price_change**：4156 条 — 有 modelId 2814（68%）
- **source_observation**：244 条 — modelId 泄漏 0
- **resolver 分布**：resolved 259 / family 15 / ambiguous 0 / unresolved 288
- **false positive = 0**（dangerous inputs 38 个零 resolved）
