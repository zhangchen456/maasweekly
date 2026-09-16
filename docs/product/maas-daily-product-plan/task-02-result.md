# Task 02 交付报告：结构化价格变化与证据回查

日期：2026-09-15。执行依据：[task-02-price-evidence.md](./task-02-price-evidence.md)，盘点见 [task-02-inventory.md](./task-02-inventory.md)。

## 1. 交付文件

| 文件 | 角色 |
| --- | --- |
| `pipeline/pricing/archive.py` | 持久化核心：稳定 ID（psnap_/ev_/pfv_/price_）、不可变写入、证据完整性评估、版本比较、事件归档/修订/撤回、索引、全量校验、current 重建 |
| `pipeline/scripts/archive-price-evidence.py` | 离线回放入口（`--check`/`--dry-run`/`--since`/`--until`/`--only`/`--history-dir`/`--snapshot-dir`/`--archive-root`/`--index-dir`），零联网 |
| `pipeline/scripts/validate-price-archive.py` | 构建门禁（npm prebuild 链式调用），悬空引用/hash 篡改/修订链断裂 → 非零退出 |
| `pipeline/scripts/fetch-prices.py` | 在线链路接入：每来源持久化快照/证据/版本/事件；失败沿用与日基线分离；`--only` 未运行来源保留；零事件撤回；事件带稳定 id 与真实单位 |
| `pipeline/pricing/view_data.py` | `fact_to_dict` 补 `effective_at`；dataset 新增 `evidence_link` |
| `pipeline/pricing/extractors.py` | anthropic 5m/1h cache write 用 time_condition 区分（修复同 fact_key 双事实静默覆盖） |
| `site/src/pages/evidence/[id].astro` | 证据详情页：来源、摘录（安全文本化）、关联事实、完整性、复制 |
| `site/src/pages/item/[id].astro` | 双类型路由：price_ 事件渲染前后金额/百分比/条件/前后证据链接 |
| `site/src/pages/daily/[week].astro` | 周路由并集加价格索引（T12）；价格变化条目加详情入口 |
| `site/src/pages/index.astro` | 首页价格事件加详情入口 |
| `site/src/data/pricing/price-ledger.template.html` | 台账详情弹窗：evidence_link 优先，回退 source_url |
| `tests/test_price_archive.py` | 30 个隔离测试（T01–T18 核心场景 + 三入口中断恢复 + --only 台账组装 + 篡改拒绝） |
| `site/package.json` | prebuild 链式 validate-archive + validate-price-archive |

## 2. 命令与退出码（实际执行）

| 命令 | 退出码 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_price_archive.py'` | 0（30 tests OK，含三入口中断恢复与 --only 台账组装） |
| `python3 tests/test_pricing_extractors.py` | 0（八家 × 双格式全过） |
| `python3 -m unittest discover -s tests -p 'test_record_archive.py'` | 0（Task 01 无回归） |
| `python3 pipeline/scripts/archive-price-evidence.py --check` | 0 |
| `python3 pipeline/scripts/validate-archive.py` | 0 |
| `python3 pipeline/scripts/validate-price-archive.py` | 0 |
| `cd site && npm run build` | 0（1306 价格详情页 + 2365 证据页） |
| `node --test tests/records.test.mjs` / `pricing.test.mjs` / `leaderboards.test.mjs` / `platform-logos.test.mjs` | 全部通过 |

## 3. 迁移结果（仓库现有 7 天数据回放）

事实：8642 条历史 → 8415 匹配（97.4%）；证据 2365 份；事件 1306 条（首日 newly_observed 1262 + 真实变化 44）。

| 指标 | 数量 | 说明 |
| --- | --- | --- |
| evidence complete | 8275 | 金额+单位+条件齐备 |
| evidence partial | 140 | 表头/缺项摘录（reasons 列明） |
| evidence unavailable | 227 | glm 2026-09-06/07 旧版页面无法用新 extractor 回放（108）；anthropic 旧 key cache_write 历史事实（119）——均保留历史金额不覆盖，证据降级披露 |

事件校验：09-08:22 / 09-09:5 / 09-10:3 / 09-11:12 / 09-12:2，与既有 daily_changes.price_changes 逐日一致；09-12 `gemini-2.5-computer-use-preview output 10→5 (−50.00%)` 等样例人工核对通过。

台账 evidence_link：2608/2642（98.7%）关联成功，34 条如实无链接（降级显示原 source_url）。

## 4. T01–T18 验收对照

| # | 场景 | 结果 | 验证方式 |
| --- | --- | --- | --- |
| T01 | 同输入两次运行字节不变 | ✓ | 沙箱 7 天回放三次 tree-hash 全等 |
| T02 | 同值新观察不产生事件 | ✓ | 沙箱 09-12→09-13 同值 0 事件 |
| T03 | 10→8 输出 −20% | ✓ | 单测 test_amount_down_20_percent |
| T04 | 旧值 0/币种/区域变化不输出百分比 | ✓ | 三个单测（terms_changed/percentUnavailableReason） |
| T05 | 同日修订、撤回恢复 | ✓ | 单测 test_event_id_stable_across_reruns / test_withdraw_and_reactivate |
| T06 | 失败沿用不前移不回退 | ✓ | latest_history(include_today) + stale_backtrack（kimi 09-12 回退 09-11 快照） |
| T07 | --only 保留未运行来源 | ✓（修订） | 初版只保留来源状态。复审发现未运行来源的既有事实未合回台账（局部调试会覆盖全站台账）→ 修复：not_run 来源事实以 stale(not_run_kept) 合回 all_facts 与 ledger_history；diff 范围限定本次运行厂商，避免假 missing；新增台账组装测试 |
| T08 | 坏 JSON/身份冲突非零退出 | ✓ | _write_immutable 拒绝；validate 系列非零 |
| T09 | 各阶段中断重跑恢复 | ✓（修订） | 初版只测了 current 重建。复现 P1（修订已写、current 未替换中断 → 重跑时间戳冲突）后修复：merge/withdraw 入口先 restore_event_from_revisions；新增新建/更新/撤回三入口真实中断测试（注入 current 写入失败，验证重跑幂等且历史修订字节不变）+ 时钟推进稳定性 + 篡改拒绝（含 restore 校验漏洞修复：current 与对应修订签名分叉时无论是否 top 均拒绝） |
| T10 | 表头摘录降级 | ✓ | 单测 test_header_only_is_partial |
| T11 | 历史不可恢复不补造 | ✓ | 227 条 unavailable 如实披露，历史金额保留 |
| T12 | 只有价格事件的旧周可达 | ✓ | 周路由并集加 price-index；dist 验证 |
| T13 | 门禁非零退出 | ✓ | 悬空引用/hash 篡改实测拦截 |
| T14 | script/恶意 HTML 转义 | ✓ | 单测 + 构建产物抽查无 script 节点 |
| T15 | 台账证据入口 | ✓ | evidence_link 渲染；弹窗链接到 /evidence/ |
| T16 | workflow 顺序回放 | 部分（见 §6） | sync 逻辑未改（price_changes 保留规则已有）；fetch→build 链路构建验证 |
| T17 | --check/--dry-run 零写入 | ✓ | --check 只读校验；--dry-run 不建目录不落快照 |
| T18 | 新鲜度与完整性独立 | ✓ | 单测 test_fresh_vs_completeness_independent |

## 5. 浏览器验证（本地预览，2026-09-15）

- 价格事件页 `/item/price_768c…d72523/`：Google gemini-2.5-computer-use 输出价 10→5，−50.00%，前后证据两个链接可点 ✓
- 证据页 `/evidence/ev_ebed…b4d898c/`：Google 定价表摘录渲染（Free Tier / $1.25 per 1M tokens 等），无 script 节点 ✓
- 周归档 `/daily/2026-W37/`：价格台账变化 2 条 + 详情入口 ✓

## 5.1 交付后修复（2026-09-15 复审）

复审发现两个真实缺陷并已修复（变更见 git log）：

1. **P1 中断恢复冲突**：价格事件「修订已写、current 未替换」中断后，隔秒重跑因新 `revisedAt` 与已落盘修订冲突而失败。修复：`restore_event_from_revisions` 校验修订链并恢复 current；`_commit_event` 对已存在修订按签名（排除时间戳）幂等，保留原时间戳。原 T09 标注不实——测试只覆盖 current 重建，未测真实入口中断；现补齐新建/更新/撤回三入口测试。
2. **--only 台账覆盖**：未运行来源只保留状态、事实未合回，`--only openai` 局部调试会把全站台账覆盖成只剩 openai。修复：not_run 来源既有事实以 stale 合回 all_facts/ledger.json/ledger_history；diff 限定运行范围防假 missing。
3. **顺带修复 restore 校验漏洞**：current 与对应修订签名分叉时原实现仅在非 top 修订时拒绝——篡改 top 修订可被放过。现无论是否 top 均拒绝，配篡改测试与真实归档扫描（1306 条零分叉）。

## 5.2 第二轮修复（2026-09-16，验收六项问题）

第一轮交付被验收驳回（[task-02-acceptance-2026-09-15.md](./task-02-acceptance-2026-09-15.md)：A1–A3 三项 P1 + A4–A6 三项 P2）。第二轮全部修复：

### A1（P1）同日基线 — ✅
`_baseline_before` cutoff 改为目标日上海零点，同日重跑始终与前日基线比较（5→10→8→9 场景验证：10→9 计 −10% 而非 8→9 的 +12.5%；当日回到基线值不产生事件）。两入口（fetch-prices / archive-price-evidence）同步。测试 `TestSameDayFixedBaseline`。

### A2（P1）契约错误零写入 — ✅
在线入口改两阶段提交：`_plan_provider_archive`（内存构建）→ `_commit_archive_plan`（全量预检零写入 → 统一落盘）；`except pa.ArchiveError: raise` 直通不再降级为抓取失败。后源冲突实测零写入。测试 `TestTwoPhaseCommit`。
顺带修复：测试沙箱此前未隔离 run 记录目录，`_commit_archive_plan` 硬编码真实归档路径写 `data/price-runs/`——A5 门禁落地后立即暴露（fetch-2026-09-13.json 引用 12 个不存在版本）。现 `runs_root` 可注入，测试传沙箱。

### A3（P1）complete 必须绑定事实 — ✅
新增 `verify_evidence_for_fact`（模型 + 金额币种紧邻 + 单位三要素可复核）与 `fact_evidence_status`（形态级 × 事实级组合），两入口接线。摘录侧补 `_with_heading_context`（表前置标题并入）与 `html_excerpt_to_text` 标题行保留——解决模型名在表外的页面（google/deepseek）无法独立核价的问题。
八家快照全量重放质量：**complete 2359 / partial 288**（修复前 1995/652）。剩余 partial 均为真实证据粒度缺口（摘录内确实无该要素）：openai 140（表内裸 `$10.00` 无单位说明，单位在表外）、qwen 141 / doubao 3（图像模型「元/张」vs fact 记为 `/1M token`——extractor 单位归类问题，见下「已知问题」）、glm 4（行内写法无单位）。
测试 `TestFactEvidenceBinding`：三类反例（错金额/错模型/共享表串证据）+ 真实页面形态 + 组合逻辑。
**注意**：标题并入使摘录变化 → 新证据 ID。旧证据不可变保留，重放产生新证据，同一快照两套证据并存（预期行为）。

### A4（P2）证据页构建重复全库扫描 — ✅
`getStaticPaths` 一次性扫 `price-facts/versions/` 建 `evidence_id → facts[]` 索引，经 `props` 传入；页面删除逐页扫描。复杂度 O(pages × versions) → O(pages + versions)。
实测：**7352 页 28 分 48 秒 → 11.6 秒**（同一台机器、同一数据集、三次构建中最差与最好对比）。

### A5（P2）门禁一致性盲区 — ✅
`validate_price_archive` 补五项：(1) 高于 current.revision 的额外修订文件；(2) 证据 id 从五要素重算比对；(3) 证据 ↔ psnap 内容关联；(4) current.fact_key 对应关系与最新版本指向（并列 observed_at 时指向任一最新版本均合法）；(5) run 记录 state 只能 committed/prepared、committed 版本引用存在、prepared 残留检测。三 CLI 入口均传 runs_root。
落地即在真实归档抓到问题：测试污染的 run 记录（见 A2）。测试 `TestValidationGateBlindSpots`（9 项篡改反例）。

### A6（P2）证据页「未知时间」 — ✅
证据是内容身份、无观察时间。删掉「未知时间」标签：页首显示「关联事实观察于 {最早–最晚}」范围（无关联事实时显示「证据内容身份（与观察时间无关）」），摘录卡片注明观察时间见关联事实。全站 dist 零「未知时间」残留。

### 第二轮测试与验证汇总

- `test_price_archive.py`：34 → **56 项**（+A2 两项 +A1 两项 +绑定 13 项 +盲区 9 项），全绿
- 八家 extractor 回归、record 归档测试（18 项）全绿
- 真实归档重放（7 日 × 8 家，2647 事件）+ `--check` + 构建门禁全过
- 全站构建：7352 页 / 11.6 秒，产物抽查（关联事实数、观察时间范围、无未知时间、无 script 节点）通过

### 已知问题（如实声明，超出本轮范围）

- **extractor 单位归类**：图像模型「元/张」定价被 `_make_fact` 硬编码 `unit_name="token"` 记为 `/1M token`（qwen 141 + doubao 3 条 partial 的根因）。事实身份（fact_key）含单位，修复需迁移历史版本，应在独立任务处理。当前 partial 判定如实反映了「摘录无法按 token 单位复核」的事实。
- 同一快照新旧两套证据并存（A3 摘录改进所致，证据不可变设计下的预期行为）。

### 第三轮（2026-09-16 复验后）：Kimi 迁移 + 退出码 + 八家全量在线采集

- **Kimi**：官网迁移 platform.kimi.com（registry 升 kimi-2），`KimiPlaywrightProvider` 适配新文档结构（模型集中在 chat 单页，功能页 batch/hosted-agents/websearch 排除），model_key 与既有归档无缝衔接。端到端 24 facts / 4 models / 8 evidence 全 complete。
- **退出码**：全来源失败 → 退出码 2（有历史沿用也不再返回 0）；部分失败 → 0；统一 `RUN-STATUS:` 状态行（含 dry-run 路径）。
- **八家全量在线采集**：`fetch-prices.py` 退出码 0，RUN-STATUS ok 8/8（anthropic 85 / deepseek 12 / doubao 301 / glm 27 / google 70 / kimi 24 / openai 140 / qwen 2032 facts），39 事件，ledger 2691 条；归档校验、归档门禁（3001 事件 / 5282 证据）、56 项测试、八家 fixture 回归、全站构建（8456 页 / 9.71 秒）全绿。「真实在线抓取一次」验收项关闭。


## 6. 未完成项（如实声明）

（无。T16 已于 2026-09-16 本地完整执行，见 §5.3；部署与回仓提交步骤属 CI 专属，本地等价验证到构建产物为止。）

## 5.3 T16 完整 workflow 本地执行（2026-09-16 13:21）

按 daily-update.yml 步骤顺序本地等价执行（部署/SSH/回仓提交为 CI 专属，本地验证到 dist 产物）：

| 步骤 | 命令 | 退出码 | 产物 |
| --- | --- | --- | --- |
| 信源抓取 | `python3 pipeline/scripts/fetch_sources.py` | 0 | 09-16 diff（68 信源：39 成功 / 29 失败，全 first_fetch——09-13~15 无抓取记录超出 3 天回溯窗，如实表现） |
| 同步 diff | `python3 pipeline/scripts/sync-diff-to-site.py` | 0 | 11 天 / 139 changed / 3 周 |
| 价格抓取 | `python3 pipeline/scripts/fetch-prices.py` | 0 | RUN-STATUS ok 8/8；39 price_changes；ledger 2691 条 |
| LLM 要点 | `LLM_API_KEY=… python3 pipeline/scripts/llm-digest.py` | 0 | 09-16 highlights 1 组（Anthropic cache_write 3 条要点） |
| 重同步 | `sync-diff-to-site.py`（二次） | 0 | highlights 保留并聚合进 weekly-digest（W38 09-16 pricings=3） |
| 归档校验 | `archive-price-evidence.py --check` | 0 | 通过 |
| 构建门禁 | `validate-price-archive.py` | 0 | 3001 事件 / 5612 证据 |
| 全测试 | 三套测试 | 0 | 56 项 + 八家 fixture + 18 项 record |
| 全站构建 | `npm run build` | 0 | **8786 页 / 10.18 秒** |

dist 抽查：首页含今日 Anthropic 要点 ✓、W38 周页 09-16 pricings 渲染 ✓、价格台账入口 ✓。

T16 过程中修复两个真实缺陷：

1. **llm-digest latest 选取错误**：`latest = days[0]`，但 days 不保证按日期排序（实测 days[0] 是 09-02）——无参调用会把无内容的旧条目当最新日处理，真正有 price_changes 的当日被跳过。改为 `max(days, key=lambda d: d["date"])`。
2. **（确认既有行为）** sync 重建 days 后，不在 `data/diff/` 中的日期条目会消失（含其 price_changes/highlights）。CI 顺序（fetch_sources 先跑）下不触发；本地跳过信源抓取直接跑 sync 会清掉当日价格数据——本次按正确顺序重跑恢复。
- **T16 完整 workflow 回放未做**：需要 LLM_API_KEY 的 llm-digest 环节未在本地重放；sync 的 price_changes 保留逻辑未改动（既有实现按日期幂等保留）。
- **deploy.yml paths 已含 data/** 与 site/src/data/**（推送自动触发链路不变）。
- 34 条台账价格无 evidence_link（glm 旧版页面 + anthropic 旧 key 历史）——不伪造，回退显示官方 URL。

## 7. 维护命令（新增）

```bash
# 每日自动（daily-update.yml 内 fetch-prices.py 已接入归档）
python3 pipeline/scripts/fetch-prices.py          # 在线抓取 + 归档
python3 pipeline/scripts/archive-price-evidence.py --check   # 归档校验
python3 pipeline/scripts/validate-price-archive.py           # 构建门禁
python3 -m unittest discover -s tests -p 'test_price_archive.py'  # 单测
```
