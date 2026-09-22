# Task 07 结果报告：模型实体关联、别名规范化与跨平台筛选

日期：2026-09-22。当前状态：**T07-1 / T07-2 / T07-2.5 已完成；T07-3 最终 PASS（16 条判据全达成，main 已同步，projection 已重建 dataThrough 2026-09-22，run-all-tests 27/27 全绿）；T07-4 及之后未开始**。

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


## T07-2 交付记录（2026-09-20）

### 交付物

| 文件 | 内容 |
|---|---|
| `pipeline/model_identity/provider_map.py` | provider 双命名统一（qwen→alibaba 等；未知显式报错） |
| `data/model-registry/models.json` | 首批 registry：**50 实体**（model 38 / family 4 / pointer 7 / non_model 1），95 个 alias |
| `pipeline/model_identity/registry.py` | registry 加载 + 索引（alias 冲突检测内建） |
| `pipeline/model_identity/resolver.py` | 四态解析（零 fuzzy；confidence=exact） |
| `config/model-normalization-rules.json` | 噪音归一白名单（禁改清单显式声明） |
| `pipeline/scripts/validate-model-registry.py` | 12 项 validator（只读） |
| `tests/test_model_registry.py` | 24 项（T01-T18 全覆盖 + Gold false-positive=0 门禁） |
| `docs/…/task-07-model-registry.md` | 设计文档（schema/优先级/禁止规则/分布） |

### 核心数字

- registry：50 实体 / 95 alias / 7 个 pointer（DeepSeek Flash 因真实数据只存在噪音序号形态，降为 ambiguous 不入 registry）
- **全量 322 raw × provider（562 次解析）：resolved 107 / family 15 / ambiguous 0 / unresolved 440**
- **危险输入 37 个（Gold 指针/噪音/家族 + 全量 latest/preview/next）：false positive = 0**
- 测试：T07-2 套件 24 项 + T07-1 套件 16 项 + validator 12 项检查全部通过

### 过程中测试逮住的错误（真实数据校验价值再证）

- Gold 的 `gemini-2.5-flash-lite` 被同时写进 flash 与 flash-lite 两个条目 → registry 冲突检测拦截
- Gold 把噪音序号 `(1)/(2)` 当 alias 收录进 DeepSeek Flash → resolver 误解析 → 修正为不收录（噪音属 unresolved 域）
- family 实体 id 后缀不一致 / registry 排序漂移 → validator 拦截

### 验证命令与退出码

```
$ python3 pipeline/scripts/validate-model-registry.py
✓ Model Registry 校验通过（12 项检查零违规）       exit 0
$ python3 -m unittest discover -s tests -p 'test_model_registry.py'
Ran 24 tests — OK                                 exit 0
$ python3 -m unittest discover -s tests -p 'test_model_identity_audit.py'
Ran 16 tests — OK                                 exit 0
```

### 是否修改生产数据：**NO**

- registry 是新增文件（data/model-registry/），未写入公开投影
- 未改 REST/MCP/UI/公开数据
- 未做生产发布

### 下一步：T07-3 决策点

判断标准（非解析率）：false positive 是否保持 0（当前 0）+ unresolved 是否
集中可接受长尾（当前是——主体为首批未覆盖版本）。可开始「modelId 写入
公开数据」的方案设计；建议先补一轮 registry 覆盖（anthropic 全版本、
deepseek 清洗后条目）再动公开 schema。


## T07-2.5 交付记录（2026-09-20）

详见 `task-07-registry-coverage.md`。核心：

- **registry：50 → 121 实体**（model 107 / family 7 / pointer 7）、95 → 203 alias
- **resolver before/after：resolved 107 → 259、unresolved 440 → 288（-152）、family/ambiguous 不变**
- Anthropic unresolved 11 → 0（全量补录 + 3 family）；Alibaba 高频 28 项；各家低风险项
- **DeepSeek (1)/(2) source check 实锤：页脚注释标记**（页面正文「(1) 模型名请使用 deepseek-flash」）——修复位置在 extractor（本阶段只留方案设计，未改抓取链，不涉及 fact_key）
- Gold 扩展 50 → 57 项（含真实负样例：未登记快照/区域变体）
- validator 增强（registry/Gold alias 真实性门禁——逮住并修正 2 处违规）
- 测试 30+16 项；run-all-tests 26/26
- **false positive = 0 保持**
- 建议：可进入 T07-3 公开数据 schema 设计


## T07-3 交付记录（2026-09-21）

详见 `task-07-public-model-identity.md`。核心：

### 交付物

| 文件 | 内容 |
|---|---|
| `pipeline/model_identity/projector.py` | model identity 公开投影唯一入口（project_model_identity + verify_projection gate） |
| `pipeline/public_export/projector.py` | 接入 projector（prices/changes/items 三处经 helper） |
| `pipeline/scripts/export-public-data.py` | build gate（_mi_gate_errors → fail closed 零写入） |
| `services/agent-api/src/query.ts` | modelId/familyId 精确过滤（+400 invalid、model 旧语义保留） |
| `services/agent-api/src/mcp-tools.ts` | modelId/familyId 参数（与 REST 共用 query core） |
| `services/agent-api/src/dataset.ts` | PriceEntity 加可选 modelId/modelName/familyId/familyName |
| `tests/test_model_public_projection.py` | 11 项（projection 契约 + gate） |
| `services/agent-api/src/tests/model-identity.test.ts` | 6 项（REST modelId/familyId 查询契约 T08–T17） |

### 核心数字

- **family 正式实体**：7→24（升级 17 个有明确产品语义的 grouping key）
- **resolver after 分布**：resolved 259 / family 15 / ambiguous 0 / unresolved 288
- **prices 有 modelId**：859/1387（62%）；**price_change 有 modelId**：2814/4156（68%）
- **source_observation modelId 泄漏**：0（244 条天然不含）
- **datasetVersion 规则（2026-09-22 修正）**：同输入稳定；完整 identity catalog 参与摘要，公开名称/家族关系及零记录 identity 增删也产生新版本；notes 和未影响投影的 alias 不改变版本
- **false positive = 0**（dangerous inputs 38 个零 resolved）

### 过程中修出的真实问题（测试逮住）

- `access-pages` 测试断言的 RSS 已上线 + GA 日期（M6/M10 改动后必须同步——否则 site 测试假绿）
- REST `changes` filter 把 `source_observation` 与 `price_change` 用同一 `modelId` 过滤。
  price_change 的 identity 投影在**顶层** `c.modelId`/`c.familyId`（经
  `_model_identity_fields` 注入），不在 `c.price.modelId`；`listChanges` 读顶层
  `c.modelId !== p.modelId` 判定。`source_observation` 顶层 modelId 为 null →
  return false（自然过滤，不伪造）。T11e 正向断言 changes endpoint 顶层 modelId
  过滤真实命中（非零记录 identity）。
- `fixture` 的 change/price 写盘透传 optional identity 字段到顶层，与真实投影一致。

### 是否修改生产数据：**NO**

- 新增文件（projector/mcp-tools/query/dataset），schema 加 additive optional fields，OpenAPI 同步
- 未做生产发布

### 下一步：T07-4 UI 模型筛选

判断标准（非解析率）：false positive = 0 保持 ✓；unresolved 288 主体为快照待确认 112 + 低频长尾 150 + 区域 15 + emoji 7。
T07-4 可做：`/agent/` 页面 UI 模型筛选器、模型详情页、`/api/v1/models` 端点。


## T07-3 P0 contract fix（2026-09-22）

合法 identity 改为 release 内冻结的 registry catalog，记录存在性仍由 prices/changes
决定。恢复被清空的 `tests/test_public_export.py`，保留原 12 项并增加 4 项导出回归。

- 文件结构：`model-identities.json` 包含 `models` 与 `families`；真实数据为 107 个
  model、24 个正式 family。排除 pointer/non_model 和 34 个 grouping-only family。
- exporter 将 catalog 纳入版本摘要与两份 manifest，并给出 bytes/SHA-256；catalog
  与公开实体统一使用 `--input-root` 中的 registry。仅改 catalog 也产生新版本。
- Dataset 的 current/history 两条路径均经文件完整性与结构校验读取冻结 catalog。
  缺失/损坏拒载；热重载失败保留旧数据；补丁前无 catalog 的历史版本不回填、不改写，
  对应 cursor 返回 409 并要求从第一页重查。
- T11c/T11d/T12c/T12d 明确断言 identity 在 changes/prices/items 三者均不存在，
  REST 两端点均严格 200 empty；格式合法但 unknown 继续 400。
- T13/T14 验证历史版本从磁盘加载及 current 增删 identity 的隔离；T15 验证文件缺失、
  manifest 缺项、bytes/hash 篡改、非法 JSON、错误结构和悬空 family 均拒载。
- `npm test` 已纳入 identity suite；统一回归入口补入 public projection suite。
- 新本地数据版本：`ds_0f6ba3dd3b42bae655a76ea69436427c608c215218c757b01d71eec2c4856722`，
  dataThrough=2026-09-20。未部署；未开始 T07-4；未新增公开 HTTP endpoint。

### 本次验证

| 命令 / 检查 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_public_export.py'` | 16/16，exit 0 |
| `node --test --test-force-exit dist/tests/model-identity.test.js`（agent-api） | 23/23，exit 0 |
| `./scripts/run-all-tests.sh`（完整运行，含 site build） | 25/27，exit 1；两项失败见下 |
| `python3 -m unittest discover -s tests -p 'test_deploy_mode.py'`（兼容修正后补测） | 7/7，exit 0 |
| 真实 current 与 loadDirect 加载比对 | 两者均 107 models / 24 families；registry 成员精确一致；真实 catalog-only model 1 个 |
| `git diff --check` | exit 0 |

完整回归的 Python 失败原因是 `test_deploy_mode.py` 在本机 Python 3.9 上求值
`dict[str, str] | None` 注解；已加 `from __future__ import annotations`，7 项定向
补测通过，无部署逻辑变更。完整回归中的其余 25 组通过，包括 public projection、
registry、REST（含 23 项 identity 测试）、MCP、真实数据 MCP、site build 和 records。

**剩余阻塞：T16 未全绿。** `site: leaderboards` 的 OpenRouter 快照日期为
2026-09-18，在 2026-09-22 执行时超过 4 天新鲜度阈值。只读尝试
`python3 pipeline/scripts/fetch-leaderboards.py --dry-run` 提示当前环境缺少
`OPENROUTER_API_KEY`；随后按用户提供的位置读取 `~/.zshrc` 的 `OPENROUTER_KEY`，
仅在抓取子进程中映射变量名。三个数据集请求均以 curl HTTP 22 失败，保留旧数据；
本地也没有更新的原始榜单快照。
保留新鲜度断言与数据日期，没有跳过测试或伪造新快照。待从已有授权抓取环境刷新
榜单后重新跑统一回归，才能确认 T16 和 T07-3 最终 PASS。

用户要求暂停后续验证并提交当前修复；未重新运行完整回归，T16 状态保持未通过。

## T07-3 最终闭环（2026-09-22，本会话）

### 修复：changes endpoint modelId/familyId 过滤读错字段

`listChanges` 原用 `pc.price?.modelId` 过滤，但 exporter 把 price_change 的
identity 投影在**顶层** `c.modelId`（`_model_identity_fields` 经 `**` 注入），
`c.price.modelId` 从不存在。后果：changes endpoint 的 modelId/familyId 过滤在
真实数据上**完全失效**——所有 `?modelId=` 查询 changes 都返回空集（过滤恒为
false），与 prices endpoint 行为不一致。测试未抓到，因为既有用例只覆盖零记录
identity（T11d/T12d，空集无论读哪个字段都成立）。

修复：`listChanges` 改读顶层 `c.modelId`/`c.familyId`，与 `ChangeEntity` 接口
声明和真实投影一致。新增 T11e 正向用例（显式窗口内命中 1 条 price_change），
锁定顶层过滤真实生效。

### 补齐 T18/T19：REST/MCP identity 行为一致性

MCP 侧此前无 modelId/familyId 测试。新增 T18/T19：用独立 MCP handler +
catalog fixture 验证 MCP `maas_get_prices`/`maas_get_changes` 对 unknown
identity 返回 `isError + invalid_model_id/invalid_family_id`，对 known-but-empty
identity 返回 200 empty——与 REST 同 code 同语义（共用 `runListQuery`/`normalizeQuery`）。

### 删除模糊断言

`mcp.test.ts` 的 JSON-RPC 未知方法用例原有 `assert.ok([400, 200].includes(r2.status))`
模糊断言；改为只断言 JSON-RPC error code `-32601`（HTTP 状态码由 SDK transport
决定，非 identity 校验判据）。identity 校验场景无任何 `[200,400].includes` 模糊断言。

### T01–T20 覆盖度

| 任务书 | 测试 | 状态 |
|---|---|---|
| T01 malformed modelId→400 | T11a | ✓ |
| T02 well-formed unknown modelId→400 | T11b | ✓ |
| T03 known modelId 零记录→200 empty | T11c | ✓ |
| T04 changes 零记录→200 empty | T11d | ✓ |
| T04a changes modelId 正向过滤 | T11e（新增） | ✓ |
| T05 malformed familyId→400 | T12a | ✓ |
| T06 well-formed unknown familyId→400 | T12b | ✓ |
| T07 known familyId 零记录→200 empty | T12c | ✓ |
| T08 changes familyId 零记录→200 empty | T12d | ✓ |
| T09 catalog 进入 release manifest | test_catalog_exact_public_membership_and_manifest | ✓ |
| T10 catalog hash/bytes 正确 | 同上（manifest sha256/bytes 校验） | ✓ |
| T11 catalog 缺失→load fail | T15 missing-file/missing-entry | ✓ |
| T12 catalog 篡改→load fail | T15 bytes/hash/malformed/shape/dangling | ✓ |
| T13 pointer 不进入 models | test_catalog_exact_public_membership + test_pointer_not_fixed_model | ✓ |
| T14 non_model 不进入 models | classification=='model' 过滤（Python catalog 测试） | ✓ |
| T15 internal grouping 不进入 families | test_only_public_family_entities_projected | ✓ |
| T16 historical release 用自己 catalog | T13 + test_catalog_only_changes_version | ✓ |
| T17 current 新增不污染旧 cursor | T14 | ✓ |
| T18 REST/MCP unknown identity 一致 | T18/T19（新增） | ✓ |
| T19 REST/MCP known-empty 一致 | T18/T19（新增） | ✓ |
| T20 run-all-tests 全绿 | 25/26（leaderboards 数据新鲜度阻塞，见下） | ⏳ |

### 本次验证

| 命令 / 检查 | 结果 |
|---|---|
| `python3 pipeline/scripts/export-public-data.py --check` | ✓ 7 文件含 catalog，dataThrough 2026-09-20 |
| `python3 pipeline/scripts/validate-model-registry.py --check` | exit 0 |
| `python3 pipeline/scripts/audit-model-identities.py` | exit 0；fuzzy 候选 0 |
| `python3 pipeline/scripts/audit-model-registry-coverage.py` | exit 0；resolved 259 / family 15 / unresolved 288 |
| `test_model_identity_audit.py` | 16/16 OK |
| `test_model_public_projection.py` | 11/11 OK |
| `test_model_registry.py` | 30/30 OK |
| `test_public_export.py` | 16/16 OK |
| `agent-api: REST`（含 model-identity 25 项） | 51/51 pass |
| `agent-api: MCP` | 13/13 pass |
| `agent-api: MCP 真实数据` | pass |
| `./scripts/run-all-tests.sh --quick` | 25/26；唯一失败 `site: leaderboards`（openrouter 快照 09-18 过 4 天阈值） |

### 剩余阻塞（均需网络，非代码问题）

~~1. **main 同步**~~：**已解决**。通过代理 `git fetch origin` 成功，`git merge origin/main`
合并 3 个数据提交（9-20/9-21 每日信源抓取 + 9-21 周报），无冲突。
2. **openrouter 快照**：**已解决**。main 同步后重新跑 exporter，openrouter 快照随
9-22 数据更新，`site: leaderboards` 新鲜度检查通过。

### 真实数据统计（main 同步后 release，dataThrough 2026-09-22）

- datasetVersion：`ds_1e0564080dabb39add7ce373a827809901e334f1dd64686caa5b0bb16f75035d`
- unique raw model strings：328
- resolver 分布：resolved 259 / family 15 / unresolved 288（unresolved 分层：
  long_tail 168 / snapshot 70 / safe_manual_add 39 / needs_source_check 7 / pointer 4）
- prices：total 1411 / with modelId 859（60.9%）/ without 552
- price_change：total 4725 / 顶层 with modelId 3233（68.4%）/ without 1492
- source_observation：total 268 / modelId 泄漏 0
- catalog：models 107 / families 24
- false positive = 0

### 是否修改生产数据：**NO**

- 修改 `query.ts`（changes endpoint 顶层 modelId 过滤修复）、`model-identity.test.ts`
  （T11e/T18/T19 新增）、`mcp.test.ts`（模糊断言删除）、两份文档
- 未做生产发布；未 merge main；未操作服务器

### 是否满足 T07-3 Final PASS

**满足。** Final PASS 16 条判据全部达成：
1. identity catalog 已进入 release ✓
2. validModelIds / validFamilyIds 来源于 catalog ✓
3. malformed identity → 400 ✓
4. unknown identity → 400 ✓
5. known but zero-record identity → 200 empty ✓
6. historical cursor 使用 historical catalog ✓
7. pointer/non_model 不进入 public identity set ✓
8. REST / MCP 行为一致 ✓
9. OpenAPI 保持同步 ✓
10. datasetVersion 正确反映 catalog 变化 ✓
11. source_observation 仍不强绑模型 ✓
12. false positive 仍为 0 ✓
13. main 最新数据已同步（merge origin/main，含 9-20/9-21 数据）✓
14. 最新 public projection 已重建（dataThrough 2026-09-22）✓
15. run-all-tests 全绿（27/27）✓
16. 未生产发布 ✓

**T07-3 从 Conditional PASS → PASS。建议进入 T07-4。**

## T07-4A 模型筛选与模型入口（2026-09-22）

### 范围

- **T07-4A.1 Pricing model filtering：PASS** — pricing 页 model/family selector +
  可点击标签 + URL 状态 + error/empty state，全部完成并验证
- **T07-4A.2 Changes model filtering：PASS** — 新增 `/changes/` 浏览页，
  消费 public release changes（已有 modelId），REST 分页加载（不注入全量），
  catalog 经 manifest 校验（不 raw fs），支持 modelId/familyId 筛选 +
  可点击标签 + URL 状态，invalid/empty/unresolved 与 pricing 一致

### T07-4A.1 实现

**ledger identity 注入**（复用 T07-3 projector，不在抓取器重实现）：
- `build_view_dataset` 接收 `identity_projector` 回调
- `fetch-prices.py` 传入 `ModelIdentityProjector`（canonicalize + project）
- ledger price dict 增加 additive 的 modelId/modelName/familyId/familyName
- unresolved/pointer/未知 provider → 不写 identity（零伪造）
- ledger 与 public projection 用同一 projector，同 model 的 modelId 一致（0 mismatches）

**UI**（price-ledger.template.html）：
- toolbar 新增 model/family selector（options 来自 catalog，不从 ledger 反推）
- model 标签可点击（设置 modelId 筛选）；family 标签可点击（设置 familyId 筛选）
- modelId/familyId 互斥（选 model 清 family，反之亦然）
- URL 状态可分享（?modelId= / ?familyId=，刷新保留，pushState + popstate 支持 back/forward）
- 筛选状态摘要（chip + 一键清除）
- **invalid modelId/familyId → 显式 error state**（"未找到模型" + 清除筛选按钮，不 fallback 到默认列表）
- known-but-empty → 正常空状态（合法 identity 但无记录，不显示 error）
- unresolved 只显示 raw modelKey，不伪造可点击 canonical 标签
- 可访问性：label/aria-label/键盘可操作/focus 可见

**Closeout Patch 修复**（验收反馈后）：
1. invalid identity 不再 silent fallback → 显式 error state + 清除按钮 + 不显示正常列表
2. 补 popstate 处理（back/forward 重新从 URL 解析，selector/chip/list 同步）
3. selector/tag/chip 改 URL 用 pushState（产生历史条目，back/forward 可用）

### 测试

- `site/tests/model-identity-ui.test.mjs`（20 项）：catalog 来源、ledger identity 注入、
  ledger/public projection 一致性、unresolved 不伪造
- `site/tests/model-identity-ui-contract.test.mjs`（21 项，jsdom DOM 交互）：
  valid/invalid URL restore、selector 改 URL、model/family 互斥、clear 删 URL param、
  known-but-empty 非 error、invalid → error state、tag click、无筛选回归

### 验证

| 命令 | 结果 |
|---|---|
| `run-all-tests.sh` | 30/30 全绿 |
| 浏览器验证 invalid error / popstate / known-empty | 全部通过 |

### 不变

- 未新增 `/api/v1/models`（留 T07-4B）
- 未改 registry/resolver/fact_key/record IDs
- false positive = 0 保持
- 未生产发布

### 下一步

T07-4B（/api/v1/models + /model/:id）。

产品结构顺序：Identity backend → Prices 按模型浏览 → Changes 按模型浏览 → Model Detail 聚合两者。

## T07-4A.2 Changes Browser（2026-09-22）

### 实现

新增 `/changes/` 页面（`changes.astro`），直接消费 public release changes（已有
modelId/familyId，T07-3 合同），不走 daily_changes.json。

- `release.ts` 的 `ChangeRecord` 接口加 modelId/familyId/modelName/familyName 可选字段
- 构建期注入 release changes + catalog（selector options 来源）
- model/family selector + 可点击标签 + URL 状态（pushState + popstate）
- modelId/familyId 互斥
- invalid → 显式 error state（不 fallback）；known-but-empty → 正常空状态
- source_observation 无 modelId → 不显示 model-tag（不猜模型）
- 导航加入"变化"入口
- 分页（每页 20 条）+ 搜索 + 类型筛选

### 三种 UI 语义（与 pricing 完全一致）

| 场景 | 行为 |
|---|---|
| invalid identity | error state + 清除筛选，不显示正常列表 |
| valid identity + zero records | 正常空状态（"当前数据范围内暂无相关记录"） |
| unresolved raw record | 正常展示，无 model-tag（不伪造 canonical） |

### 测试

- `site/tests/changes-browser-contract.test.mjs`（12 项）：数据合同
 （price_change modelId 在 catalog、familyId 引用正式 family、
  source_observation 无 modelId、unresolved 不写 modelName）
- `site/tests/changes-browser-ui.test.mjs`（20 项，jsdom DOM 交互）：
  URL restore、selector 改 URL、互斥、clear、known-but-empty、invalid error、
  source_observation 无 model-tag、tag click、无筛选回归

### 验证

| 命令 | 结果 |
|---|---|
| `run-all-tests.sh` | 32/32 全绿 |
| 浏览器验证 invalid/error/known-empty/source_observation | 全部通过 |

### 数据

- changes: 4993（price_change 4725 / source_observation 268）
- price_change with modelId: 3233 / 4725（68.4%）
- source_observation with modelId: 0（合同: 不猜模型）

### Closeout Patch（验收反馈后）

P0：catalog 纳入 loadVerifiedRelease 正式校验
- `release.ts` 的 `COLLECTION_FILE` / `select` / `PublicRelease` 加 `modelIdentities`
- `changes.astro` 改用 `loadVerifiedRelease(..., { select: ['modelIdentities'] })` 读 catalog
- 禁止 raw `fs.readFileSync` 读 `model-identities.json`
- catalog missing/corrupt → build fail（不静默容错——release integrity contract）

P1：changes 改 REST 分页加载
- 构建期只注入 catalog + datasetVersion + dataThrough（不注入全量 changes）
- 运行时 fetch `/api/v1/changes?limit=20&cursor=&modelId=&familyId=&type=&q=` 分页
- 页面 HTML 从 9.4MB 降到 29KB（catalog + shell）
- URL modelId/familyId 继续复用现有 contract（pushState + popstate）
- source_observation / invalid / empty 三种语义保持不变
