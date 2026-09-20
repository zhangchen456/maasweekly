# Task 07：Model Registry 与 Resolver Contract（T07-2 设计文档）

日期：2026-09-20。前置：T07-1 盘点（inventory 文档 + Gold Set 50 项）。

## 1. Provider Canonicalization

**双命名体系统一**（T07-1 发现的最重要结构事实）：

```
ledger pricing providerId    canonical providerId（公开投影体系）
  qwen                 →       alibaba
  doubao               →       volcengine
  glm                  →       zhipu
  （其余同名）          →       原样
```

实现：`pipeline/model_identity/provider_map.py`——映射唯一来源于
`public_providers.json`（单一事实来源），未知 provider 显式 `UnknownProviderError`
（绝不静默生成新 id）。registry/resolver 内部只用 canonical；ledger 原始值保留不覆盖。

## 2. modelId 设计

```
<canonicalProviderId>:<canonicalSlug>
例：alibaba:qwen-plus / anthropic:claude-sonnet-4.5 / google:gemini-2.5-flash
```

- slug 保留小数点（`qwen3.7-flash`——版本语义），其余非字母数字折叠为 `-`
- slug 来自人工确认的 registry 主键，**不从 raw string 运行时生成**
- 契约：canonicalName 改名 / alias 增删 / familyId 改名都不改变 modelId；
  modelId 一旦公开永不复用

## 3. Registry Schema（data/model-registry/models.json）

```json
{
  "modelId": "alibaba:qwen-plus",
  "providerId": "alibaba",
  "canonicalName": "Qwen Plus",
  "familyId": "alibaba:qwen-plus",
  "classification": "model",          // model | family | pointer | non_model
  "aliases": [
    {"value": "qwen-plus", "type": "raw", "source": "pricing"},
    {"value": "qwen-plus-2025-07-28", "type": "snapshot", "source": "pricing"},
    {"value": "Qwen Plus", "type": "display", "source": "public"}
  ],
  "notes": "..."
}
```

- **ambiguous / unresolved 不进 registry**（它们是 resolver 结果状态）
- alias type 六类：`raw / display / snapshot / cross_generation / api_id / platform_sku`
- 稳定排序（providerId, modelId）；人工可 review；零运行时学习

## 4. alias 分类原则（T07-1 教训固化）

| 类型 | 判定 | 例 |
|---|---|---|
| raw | 抓取器产出的原始串 | `qwen-plus` |
| display | 展示名（含空格/大小写） | `Claude Opus 4.1` |
| snapshot | **人工确认**同模型的日期快照 | `qwen-plus-2025-07-28` |
| cross_generation | **产品明确**同长期实体的跨代写法 | `doubao-pro-32k` → `doubao-1.5-pro-32k` |
| api_id | 厂商 API id（与 raw 不同时） | （当前数据未单独承载） |
| platform_sku | 同模型不同平台 SKU | （当前数据未单独承载） |

## 5. pointer / snapshot / preview 处理原则

- **pointer**（`classification=pointer` 的 registry 实体）：`-latest`/`-next`/
  阿里 `-preview` 滚动指针——resolver 命中后返回 **family 状态**（列出家族成员），
  **绝不落到固定 modelId**。定价随指针变，绑定即错误。
- **snapshot**：只在 registry 显式登记（人工确认）后才绑定 modelId；
  未登记的日期后缀一律 unresolved——**绝不自动裁剪日期后匹配**。
- **preview 双语义**（按 provider）：Google 的 `-preview` 是产品名组成部分
  （resolved 到该模型）；阿里的 `-preview` 是滚动快照（pointer 语义）。
  规则按 registry classification 逐实体声明，不做字符串一刀切。

## 6. Resolver 状态定义

```
resolved   {status, modelId, familyId, matchedBy, confidence: 'exact'}
family     {status, familyId, candidateModelIds[]}
ambiguous  {status, candidateModelIds[], reason}
unresolved {status, reason}
```

无数值 confidence（拒绝伪精确「0.82 置信度」）；matchedBy ∈
`alias | display_alias | normalized_exact`。

## 7. Resolver 优先级（严格有序）

1. provider canonicalization（未知 → unresolved）
2. 噪音预处理（**仅白名单**：trim + NFC + 空白折叠 + lower——见
   `config/model-normalization-rules.json`，禁改列表显式在文件内）
3. provider + alias 精确匹配（含 api_id/raw/display 三类 alias 值）
4. provider + normalized exact（大小写折叠后精确相等；多候选 → ambiguous）
5. family exact（family 实体 → 返回成员列表）
6. 其余 → unresolved

## 8. 明确禁止（红线）

- fuzzy / 编辑距离 / embedding / LLM 决定 modelId
- 跨 provider 仅按名称相同合并（索引按 provider 隔离，T17 测试锁定）
- family 自动映射到某个 variant
- latest/next/preview 自动落到当前模型
- 日期后缀自动裁剪后绑定
- 噪音序号 `(1)/(2)` / `-us` / emoji 自动删除

## 9. Gold Set 常驻门禁

`tests/test_model_registry.py` 的 **test_gold_set_zero_false_positive**：
Gold 50 项中所有 family/non_model/ambiguous/指针输入 + 真实数据全部
latest/preview/next 串（37 个危险输入）——**任何一个被 resolved 成固定
modelId 即测试失败**。当前：**false positive = 0**。

## 10. 真实数据全量分布（322 raw × provider 组合 = 562 次解析）

| 状态 | 次数 | 说明 |
|---|---|---|
| resolved | 107 | 全部 matchedBy=alias（精确层） |
| family | 15 | family 字符串与指针 |
| ambiguous | 0 | 无（normalized 层无真歧义） |
| unresolved | 440 | registry 首批覆盖之外的长尾（含 anthropic 旧版本号、deepseek 噪音序号等） |

**数字只用于观察，不是 KPI**。unresolved 主体是首批 registry 未覆盖的
长尾（如 anthropic 全版本系列），下一轮补录即可；无一是「错绑」。

## 11. 验证命令

```bash
python3 pipeline/scripts/validate-model-registry.py        # 12 项检查零违规
python3 pipeline/scripts/validate-model-registry.py --check
python3 -m unittest discover -s tests -p 'test_model_registry.py'   # 24 项
python3 -m unittest discover -s tests -p 'test_model_identity_audit.py'  # 16 项（T07-1 套件继续有效）
```
