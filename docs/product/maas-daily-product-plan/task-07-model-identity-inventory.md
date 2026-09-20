# Task 07 盘点：模型身份字段与命名差异（T07-1）

日期：2026-09-20。基线数据：`ds_24f83f7e…`（dataThrough 2026-09-20）。
审计工具：`pipeline/scripts/audit-model-identities.py`（只读/确定性/无网络/无 LLM）。
本阶段不做 resolver、不改 API/MCP/UI、不改任何 ID/fact_key。

## 1. 模型信息来自哪些字段（按可信等级排序）

| # | 来源 | 字段 | 形态 | 可信等级 |
|---|---|---|---|---|
| 1 | ledger 价格事实 | `price.model` | 结构化（extractor 产出） | **高**——抓取器从厂商定价页结构化提取 |
| 2 | 公开投影 price_change | `price.model` | 结构化（同上，经投影） | **高**（与 ledger 同源） |
| 3 | ledger 价格事实 | `model_display_name` | 结构化展示名 | 中——人工/页面展示层，与 raw 差异 54/296 对 |
| 4 | price_change | `title`（「Provider · MODEL 组件 价格变化」） | 文本模板抽取 | 低（模板可靠但属文本）——实测 136 个抽取全部与结构化一致 |
| 5 | source_observation | `title`/`summary` | 纯文本 | **无结构化 model 字段**——244 条全部无模型维度 |
| 6 | registry | `public_providers.json` 的 provider 映射 | 结构化（provider 层） | 高（人工维护） |

## 2. 核心数字

- **unique raw model strings：322**（ledger 2722 条价格事实 + 投影 4156 条 price_change，两处同源）
- provider 分布（raw string 数，按公开 providerId 折叠后）：alibaba 221、google 32、volcengine 24、zhipu 14、anthropic 17、kimi 4、openai 5、deepseek 5
- 命名形态：specific 262 / variant-like 55 / family-like 5
- **raw 层零大小写/分隔符变体、零跨 provider 同名**（见 §5 结论）

## 3. Provider 双命名体系（最重要的结构发现）

ledger 的 pricing providerId（`qwen/doubao/glm`）与公开投影的 providerId（`alibaba/volcengine/zhipu`）**是两套体系**，靠 `public_providers.json` 的 `pricingProviderIdToProvider` 映射连接。审计时 240 个 raw string 同时携带两套 provider 名（同一模型两家名）——**这不是跨 provider，是同一 provider 的两个名字**。任何 registry/resolver 必须先折叠到单一 provider 体系。

## 4. 命名差异的主要类型（真实分布）

1. **raw ↔ display name**（54/296 对）：`claude-fable-5.1` ↔ `Claude Fable 5.1`、`glm-4.5v` ↔ `GLM-4.5V`、`gemini-2.5-flash-lite` ↔ `Gemini 2.5 Flash-Lite`——连字符/大小写/复合词位置三重差异
2. **日期快照后缀**（阿里百炼特色，约 80 个）：`qwen-plus-2025-07-28` 与基名 `qwen-plus` 并存——基名=最新快照（厂商语义），同一逻辑模型 8+ 种写法
3. **family × tier × 模态 × 变体的多维矩阵**：`qwen3-tts-flash-realtime-2025-09-18`（family3tts × tier flash × realtime × 日期）
4. **参数规格型 vs tier 型混用**：`qwen3-coder-30b-a3b-instruct`（开源规格）与 `qwen3-coder-plus`（闭源 tier）同 family
5. **跨代命名**：`qwen-deep-research`（qwen 前缀）归 qwen3 代；`doubao-pro-32k` 与 `doubao-1.5-pro-32k` 同模型两代写法
6. **代号型变体**（OpenAI 特有）：`gpt-5.6-sol/terra/luna/cyber`——代号非 tier 词，无词表可枚举
7. **页面噪音**：`deepseek-flash-(1)`、`deepseek-v4-pro-(2)`——同名表格行序号被 extractor 带进 raw（**数据质量问题，先于归一化**）

## 5. 产品问题的直接回答

**Q：当前有多少模型名称实际上只是字符串？**
322 个 raw string 全部是字符串，但**质量分层明显**：openai/anthropic/deepseek/kimi 的 raw 即厂商 API id 形态（≈稳定 ID，45/322）；alibaba/volcengine/zhipu 的 raw 含日期快照/噪音（需清洗）；google 双源（Gemini API/Vertex）已折叠到单一 providerId 但命名带展示空格差异。

**Q：哪些 provider 的 modelKey 已接近稳定 ID？**
anthropic（`claude-opus-4.1` 即 API id）、openai、deepseek（除噪音序号）、kimi、zhipu（glm 系）。**最难是 alibaba**（日期快照 8+ 写法/模型、family 与 variant 命名不规则）与 volcengine（跨代命名）。

**Q：哪些来源只有文本没有结构化 model？**
source_observation 全部 244 条（博客/模型列表/变更日志观察）——只有 title/summary 文本。这是「模型实体关联」的最大空白区：模型列表来源更新提及的模型无法与价格体系关联。

**Q：同一模型跨平台有多少种命名？**
当前价格数据只覆盖单厂商官方定价（无 OpenRouter 等聚合商价格），跨平台命名主要体现为：raw ↔ display（2 种）+ 双 provider 体系（同模型 2 个 provider 名）+ 日期快照（最多 9 种写法/模型，如 qwen-plus）。

**Q：family 和 variant 混在一起的比例？**
raw 层 family-like 形态 5 个（glm-5.x 系列——审计启发式的边界，实为模型）；真正的混用风险在**查询层**：用户输入「qwen3」「gemini 2.5」时无法从当前 API 判断是 family 还是要全部 variant——这是 T07-2 resolver 要解决的核心场景。

**Q：哪些名称自动 fuzzy match 会高风险误绑？**
- `qwen-flash` vs `qwen3-flash`（无版本号代际差异）
- `gemini-2.5-flash` vs `gemini-2.5-flash-lite`（lite 是独立模型）
- `claude-sonnet-4` vs `claude-sonnet-4.5`（小数版本）
- `qwen3-coder-30b-a3b-instruct` vs `qwen3-coder-480b-a35b-instruct`（参数数字）
- `gpt-5.6-sol` vs `gpt-5.6-terra`（同 family 不同模型）
- 日期快照：`qwen-plus-2025-07-28` vs `qwen-plus-2025-09-11`（不同快照，语义上是否同模型需人工判定）
- 噪音序号：`deepseek-flash-(1)` vs `deepseek-flash-(2)`（可能同模型不同定价行）

**Q：首批 registry 应覆盖哪些模型？**
见 Gold Set（49 项）：8 个有价格数据的 provider 全覆盖 + family/ambiguous/non_model 四类基准——按高频排序，top 10 高频（qwen-plus 系/doubao-seed-2.0 系/qwen3-coder 系/gpt-5.6-sol）全部在内。

## 6. 推荐 registry schema 输入（T07-2 设计依据）

```
ModelIdentity {
  modelId            # 稳定 ID（算法 T07-2 定，倾向 provider + canonical slug）
  canonicalName      # 人类可读（Gold Set 已有 49 个基准）
  providerId         # 单一体系（公开 providerId——ledger 侧先折叠）
  family             # 家族（qwen3-coder / claude-opus / gpt-5.6）
  aliases[]          # 含：raw、display name、日期快照、跨代写法
  apiIds[]           # 厂商 API id（当前数据未单独承载——多数 raw 即 apiId）
  classification     # model | family | ambiguous | non_model
}
```

## 7. 推荐 resolver 优先级（建议，不实现）

1. 噪音清洗（剥离独立括号序号）——**先于一切**
2. provider 官方 API model id 精确匹配（raw 即 apiId 的 provider：anthropic/openai/deepseek/kimi/zhipu）
3. 人工维护 alias 精确匹配（Gold Set → registry）
4. provider + normalized exact name（大小写/连字符归一后精确相等——**不是 fuzzy**）
5. family 明确映射（「qwen3」→ family 实体，返回 variant 列表而非猜测）
6. 其余 → ambiguous / unresolved（如实返回，不猜）

## 8. 明确不能做的规则

- 编辑距离/字符串相似度自动合并
- 只看相似度跨 provider 合并（当前数据零跨 provider 同名，未来出现也必须人工）
- family 自动映射到某个 variant（「qwen3」≠「qwen3-max」）
- 「latest」/「auto」/「-next」/「-preview」自动猜真实模型（滚动指针语义，厂商随时间改指向）
- LLM 推断后直接落正式 model identity（可作为标注建议，必须人工确认）
- 噪音序号自动删除（`(1)`/`(2)` 可能对应不同定价行——需查源页）

## 9. source_observation 的空白（T07-2+ 的输入）

244 条观察记录覆盖 16 个 provider 维度，其中「模型列表来源更新」（43 条）天然携带模型清单信息但无结构化字段。跨数据源关联（价格模型 ↔ 模型列表 ↔ 博客提及）是 model identity 的第二价值场景，依赖 T07-2 registry 先落地。
