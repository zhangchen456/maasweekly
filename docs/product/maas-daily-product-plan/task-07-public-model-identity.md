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

## 7. Release identity catalog 与 datasetVersion

合法 identity 来自 **该 release 内冻结的 registry catalog**；记录存在性来自
`prices/changes/items`。两者独立：catalog 存在但三个集合均无记录时，
`prices` 与 `changes` 的 `modelId` / `familyId` 查询均返回 `200 + items=[]`；
catalog 不存在则分别返回 `400 invalid_model_id` / `invalid_family_id`。

每个新 release 包含内部文件 `model-identities.json`：

```json
{
  "models": [
    {
      "modelId": "anthropic:claude-sonnet-4.5",
      "modelName": "Claude Sonnet 4.5",
      "familyId": "anthropic:claude-sonnet",
      "familyName": "Claude Sonnet"
    }
  ],
  "families": [
    {"familyId": "anthropic:claude-sonnet", "familyName": "Claude Sonnet"}
  ]
}
```

- `models` 只含 `classification=model`；`families` 只含 `classification=family`。
  pointer、non_model、ambiguous、unresolved 不进入合法集合；model 的 grouping-only
  family 不公开，只有正式 family 才附 `familyId/familyName`。
- exporter 使用同一输入根的 registry 构建 catalog 与实体投影，按 identity ID 稳定排序。
- catalog 写入当前与 per-release manifest，记录 `bytes/sha256`，以
  `modelIdentities` 集合参与 `datasetVersion` 计算。新增零记录模型/家族、名称或
  正式家族关系变化都会产生新版本；notes、未影响投影的 alias 和 registry 行顺序不影响版本。
- Dataset 通过现有路径与 `bytes/sha256` 校验读取 catalog，再校验结构、ID 唯一性、
  名称和正式家族引用；只从 `models/families` 构建合法 ID 集合，不从记录反推。
- cursor 加载目标 release 自己的 manifest/catalog，并用该版本合法集合重验查询。
  current 增删 identity 不改变历史查询语义。
- catalog 缺失或损坏时拒绝加载；热重载失败保留上一有效 Dataset。补丁前没有 catalog
  的旧 release 不回填当前 registry，也不改写旧版本；对应 cursor 按既有合同返回
  `409 dataset_version_expired`，从第一页重查。
- 本阶段 catalog 仅供 runtime 内部使用，不增加 HTTP `/models` endpoint，也不发布到站点。

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
