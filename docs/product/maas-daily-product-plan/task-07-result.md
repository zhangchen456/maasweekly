# Task 07 结果报告：模型实体关联、别名规范化与跨平台筛选

日期：2026-09-20。当前状态：**T07-1（盘点与 Gold Set 基线）完成；T07-2 及之后未开始**。

## T07-1 交付记录

### 扫描的真实数据

| 数据源 | 范围 | 说明 |
|---|---|---|
| `site/src/data/pricing/ledger.json` | 2722 条价格事实（296 模型） | `price.model` / `model_display_name` / provider |
| `data/public/v1/releases/ds_24f83f7e…/changes.json` | 4400 条（4156 price_change + 244 source_observation） | `price.model`（结构化）+ `title`（文本抽取对照） |
| `pipeline/config/public_providers.json` | provider 映射表 | 发现双命名体系（见 inventory §3） |
| `pipeline/config/maas_official_sources.json` | 17 平台 registry | provider/来源维度（无模型级字段） |

### 核心数字

- **unique raw model strings：322**
- provider 分布（折叠后）：alibaba 221 / google 32 / volcengine 24 / anthropic 17 / zhipu 14 / openai 5 / deepseek 5 / kimi 4
- 命名形态：specific 262 / variant-like 55 / family-like 5
- **raw 层零大小写/分隔符变体、零跨 provider 同名**（结构化抓取的意外高质量结论）
- display name 与 raw 差异：54/296 对
- source_observation 244 条**全部无结构化 model 字段**（最大空白区）

### Gold Set

`task-07-model-identity-gold.json`：**49 项**（model 39 / family 4 / ambiguous 3 / non_model 3），覆盖 8 个 provider + 通配。全部难例类型来自真实数据：日期快照（qwen-plus 8+ 写法）、噪音序号（deepseek-flash-(1)）、滚动指针（-latest 真实在库 6+ 个、-next、-preview）、跨代命名、Google 产品名 preview vs 阿里快照 preview 语义差异。

### 主要风险样例（自动误绑高危）

- `qwen-flash` vs `qwen3-flash`（代际）
- `gemini-2.5-flash` vs `gemini-2.5-flash-lite`（lite 独立模型）
- `claude-sonnet-4` vs `claude-sonnet-4.5`（小数版本）
- `gpt-5.6-sol` vs `gpt-5.6-terra`（同 family 代号）
- 日期快照互斥（`qwen-plus-2025-07-28` vs `qwen-plus-2025-09-11`）
- 噪音序号（`deepseek-flash-(1)` vs `(2)`——可能是不同定价行）
- 数据里发现：`gemini-3-pro-image-🍌`（Google 页面 emoji 混入 raw——extractor 噪音又一形态）

### 测试

```
$ python3 -m unittest discover -s tests -p 'test_model_identity_audit.py' -v
Ran 16 tests — OK
$ ./scripts/run-all-tests.sh
通过: 23 | 失败: 0   （新增套件挂入，原 22 项零影响）
```

测试过程逮住 Gold Set 两处人工错误（vision-pro 张冠李戴、preview 语义误标）——真实数据校验的价值实证。

### 是否修改生产数据：**NO**

- 只读审计（mtime/size/hash 前后一致有测试断言）
- 未改任何 model ID / record ID / fact_key / API / MCP / 页面
- 未引入任何自动 model identity 判断

### 审计命令（复现）

```bash
python3 pipeline/scripts/audit-model-identities.py            # 人类可读报告
python3 pipeline/scripts/audit-model-identities.py --json     # 完整 JSON
python3 pipeline/scripts/audit-model-identities.py --output /tmp/model-audit.json
```

（确定性：两次执行输出哈希一致，已验证）

### 下一步建议：T07-2 Model Registry schema + Resolver contract

1. Registry schema 按 inventory §6 设计（modelId 候选算法：provider + canonical slug）
2. Resolver 按 inventory §7 优先级（噪音清洗 → apiId 精确 → 人工 alias 精确 → 归一精确 → family 映射 → ambiguous）
3. Gold Set 49 项作为 resolver 首批评估基准（验收标准：零误绑——宁可 unresolved 不可错绑）
4. provider 双命名体系折叠是 T07-2 前置（resolver 输入统一到公开 providerId）
5. source_observation 的模型关联留 T07-3+（依赖 registry 先落地）
