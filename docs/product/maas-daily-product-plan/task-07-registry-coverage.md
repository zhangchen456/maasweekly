# Task 07：Registry Coverage 补录记录（T07-2.5）

日期：2026-09-20。前置：T07-1（盘点）+ T07-2（Registry + Resolver）。

## 1. unresolved 分层方法

`pipeline/scripts/audit-model-registry-coverage.py`（只读/确定性）：
对全部真实 raw strings 跑当前 resolver，unresolved 项按**显式字符串特征**
分类（零 fuzzy/LLM）：

| 分类 | before 数量 | 特征 |
|---|---|---|
| safe_manual_add | 107 | 无日期/指针/序号/emoji/区域/规格风险特征 |
| snapshot | 112 | 日期后缀未登记 |
| long_tail | 210 | 低频或带模态/规格词（可后补） |
| needs_source_check | 7 | 序号 (N)/emoji/复合串 |
| pointer | 4 | -latest/-next |

排序 count desc → providerId → rawModel（稳定）。

## 2. 补录策略与执行

三类补录（任务书 §二）：**A 明确稳定模型 / B display alias / C 明确 family**。
Anthropic 全量（11 个 safe_manual_add 全补 + 3 个 family：claude-opus/sonnet/haiku）；
Alibaba 高频 28 项（Top 频次、无风险特征）；Volcengine 8 项；Google 12 项
（preview 逐项按产品名语义判别）；Zhipu 7 项；Kimi 1 项；DeepSeek 4 项
（依 source check 结论，见 §5）。

**未补**（红线维持）：日期快照未登记 112 项、-latest/-next 4 项、
序号/emoji 7 项、-us 区域变体、跨代不明确项、source_observation 文本。

## 3. before/after resolver 分布（322 raw × 562 组合）

| | before | after | 变化 |
|---|---|---|---|
| resolved | 107 | **259** | +152 |
| family | 15 | 15 | — |
| ambiguous | 0 | 0 | — |
| unresolved | 440 | **288** | **-152** |

## 4. 各 provider unresolved before/after

| provider | before | after |
|---|---|---|
| alibaba/qwen（双体系合计） | 181+168=349 | 129+116=245 |
| google | 27 | 18 |
| volcengine/doubao | 18+18=36 | 10+10=20 |
| zhipu/glm | 8+3=11 | 1+1=2 |
| anthropic | 11 | **0** |
| kimi | 1 | 0 |
| openai | 1 | 1 |
| deepseek | 4 | 2 |

## 5. Anthropic 处理结果

11 个旧版本（opus-4/4.5/4.6/4.7/4.8/5、sonnet-4.6/5、haiku-3.5、
fable-5、mythos-5）全部补录 + 3 个 family 实体（claude-opus/-sonnet/-haiku，
成员边界清楚）。**unresolved 11 → 0**。新增 model 14 / alias 26。

## 6. Alibaba 处理结果

28 项高频稳定模型（qwen3.5/3.6/3.7 系列、omni/livetranslate/vl 子家族、
qwen-turbo/max/math/mt/coder/doc 家族等）。每项判定依据：无日期基名歧义、
无指针、无区域歧义、family 归属明确。**unresolved 349 → 245**（剩余主体
为未登记快照 + 低频模态长尾 + -us 变体——按任务书属可接受长尾）。

## 7. DeepSeek (1)/(2) source check 结论（六问实答）

追到原始快照（data/snapshots/…/DeepSeek__pricing__…md）：

1. **(1)/(2) 是什么**：页脚注释标记。原始页面表头写 `deepseek-flash(1)`，
   页面正文明确「**(1) 模型名请使用 deepseek-flash**」；`价格(2)` 行头
   同样带脚注标记。
2. **多行计费条件？** 不是——是表格转 HTML 时 footnote 引用并入了单元格。
3. **页面表格索引噪音？** 是（脚注标记，非产品名组成部分）。
4. **真实产品名一部分？** 不是——正文明确剥离。
5. **不带序号的真实字段存在**：`deepseek-v4-pro`（当前 ledger 已干净）；
   `deepseek-flash` 是厂商声明的正确模型名。
6. **修复位置**：**extractor**（表头单元格剥离脚注标记 `(\d+)`）。
   - 页面 09-20 版已自然修复表头（v4-pro 干净）——`deepseek-flash-(1)`
     残留在 ledger 是历史数据
   - **本阶段不改 extractor**（按任务书：只提交方案设计）
   - registry 处理：`deepseek:deepseek-flash` 的 alias 标 `source=public`
     （厂商正文真值）——语义准确，等 extractor 修复后数据侧自然对齐
   - **不涉及 price identity/fact_key 变更**（未动任何 fact）

**修复方案设计（留独立任务）**：extractor 表头清洗规则
`re.sub(r'\(\d+\)$', '', cell)` + 存量 ledger 数据的自然轮换（脚注噪音
条目 stale 后退出）——不回改历史 fact（会破坏 fact_key 身份）。

## 8. 剩余 unresolved 分类（288 项）

- **snapshot 未登记**：~112（主体）——需逐项人工确认「同模型」才能登记
- **long_tail 低频模态**：~150（audio/image/mt/character/seed3d 等）
- **-us 区域变体**：~15——区域是定价维度还是模型维度未判定
- **emoji/复合串**：~7（Google 🍌 系列、逗号连接串）
- **pointer**：4
- **openai 1 项**：`gemini-3.8-live,…复合串`（Google 来源误归——见 needs_source_check）

## 9. false positive 状态

**仍为 0**（危险输入 38 个：Gold 指针/噪音/家族/负样例 + 全量
latest/next/非 Google preview——零 resolved）。pointer/snapshot/noise
红线全部有测试锁定不回归。

## 10. 是否建议进入 T07-3

**建议进入**。判断标准对照：false positive = 0 保持 ✓；unresolved 剩余
288 项中明确可人工补录的高频项已清空（safe_manual_add 类 high-freq 全
resolved），剩余主体是 snapshot 待确认（112）、低频长尾（150）、区域
变体（15）——全部属于「需要人工判断或可接受缺失」类。T07-3 公开数据
schema 设计可以开始；modelId 写入公开数据时对 unresolved 条目不写字段
（保持向后兼容）。

## 验证命令

```bash
python3 pipeline/scripts/validate-model-registry.py          # 12+2 项检查零违规
python3 pipeline/scripts/audit-model-registry-coverage.py    # 分层审计（人读）
python3 -m unittest discover -s tests -p 'test_model_registry.py'         # 30 项
python3 -m unittest discover -s tests -p 'test_model_identity_audit.py'   # 16 项
./scripts/run-all-tests.sh                                   # 26/26
```
