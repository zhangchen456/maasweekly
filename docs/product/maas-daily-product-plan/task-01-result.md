# Task 01 交付报告（R1–R5 修复版）

日期：2026-09-12。针对 task-01-acceptance.md 五项阻断问题的修复交付。本地实现，未 push、未部署、未进入 Task 02。

## 1. R1–R5 修复对照

### R1 [P1] 构建门禁 — 已修复

- 新增 `pipeline/scripts/validate-archive.py`，接入 `site/package.json` 的 `prebuild`（npm 钩子，所有 `npm run build` 入口必经，不依赖先跑 sync）
- 校验内容：归档目录存在性、索引↔归档**双向字段级比对**（id/date/platform/sourceId/kind/status/title/permalink，不只数量）、JSON 逐条解析、ID 派生关系、修订链逐版本
- `item/[id].astro` 两处空 catch 改为显式 throw（归档缺失/损坏/空目录/id 不一致均中止构建）
- **五场景复验**（全部 exit 非零，正常构建 exit 0，故障后归档字节与故障前完全一致）：
  1. 缺失归档目录 → 1 ✓
  2. 损坏单条记录 → 1 ✓
  3. 缺失索引 → 1 ✓
  4. 索引悬空（引用不存在记录）→ 1 ✓
  5. 缺失修订 → 1 ✓

### R2 [P1] 输入预检统一 — 已修复

- 公共管线移入 `record_archive.py`：`validate_diff_entry` / `load_and_validate_diff` / `plan_records` / `apply_plan` / `plan_and_apply`——**两个入口（sync 与离线回填）共用同一套规则**，不再维护两份
- `plan_and_apply` 两阶段：先**全部**读取+校验+计划（零写入），全部通过后一次性应用
- sync 的未映射来源从"告警跳过"改为**硬失败非零退出**——不产生无稳定 ID 的"成功"站点数据
- **验收复现**（错误在已存在条目更新之后/第二个文件/列表末尾三种位置）：未映射、损坏 JSON、同日冲突均拒绝且**零写入**（Python 单测 R2PlanAndApplyTest 三项 + 脚本级复现通过）
- first_fetch / fetch_failed / 局部缺失不撤回（T06EntryBehavior 经真实入口验证）

### R3 [P1] 修订写入与校验 — 已修复

- **写入顺序反转**：`_commit` = 预检修订可写 → **先写修订 → 后写当前记录**。修订冲突时当前记录保持旧版完好（复现A：预置冲突 r2 → merge 拒绝，当前仍 rev1 原内容）
- **中断恢复**：`restore_current_from_revisions`——当前记录丢失但修订在时，从最新修订恢复后正常比较（重跑幂等，不产生新修订）
- `validate_archive` 增强：修订逐版本 JSON 解析、版本号连续性、id 匹配、**最新修订内容与当前记录一致**（排除程序辅助字段）、**孤立修订检测**（修订版本超过当前 revision）
- **验收复现**：修订冲突 ✓（单测 test_revision_conflict_keeps_current）、修订 JSON 损坏 ✓（test_validate_catches_corrupt_revision）、版本内容不匹配 ✓（test_validate_catches_current_revision_mismatch）、模拟写入中断 ✓（test_restore_current_from_revisions：删当前记录→重跑恢复→unchanged）

### R4 [P2] 摘要降级 — 已修复

- 摘要保留规则（`_merge_summary`）移入 `merge_record` 公共逻辑：新输入无摘要 → 保留已有；rule 输入与已有 llm 不同 → 保留 llm（不降级）；显式新 llm → 更新
- 另修正：`provenance`（内部字段）从公开内容比较中排除——离线回填同一输入不再因 diff 文件路径触发无意义修订
- **验收复现**：归档 r1（rule）→ llm 注入 r2 → 离线回填同 diff → 摘要仍 llm、revision 仍 2 ✓（单测 test_rule_input_after_llm_keeps_llm / test_none_summary_input_keeps_existing + 脚本级场景）

### R5 [P2] 索引独有周日期偏移 — 已修复

- ISO 周一算法：1 月 4 日所在周为第一周，周一 = 该周四减 3 天（替换错误的"1月1日加周数"算法）
- **验证**：2026-W36 周一 = 2026-08-31 ✓；跨年 2026-W01 周一 = 2025-12-29 ✓；4 年（1460 天）日期↔周往返验证 0 失败
- 索引独有周不再显示伪造的"0 项变化"四统计：改为真实条目数（recordCount）+ "已滚出近期窗口，分类统计不可用"提示
- **集成复现**：窗口截短构建（W36 完全滚出 daily_changes/weekly-digest）→ W36 索引独有页生成，标题 8.31—9.6，45 条来源记录链接，indexOnly 提示正确 ✓

## 2. 验收要求的测试修正

| 验收指出 | 修正 |
| --- | --- |
| T06 未送真实入口 | 新增 T06EntryBehavior：fetch_failed/first_fetch/来源缺失经 `plan_records` 真实入口验证（不建条目、不撤回） |
| T07 未传无摘要输入 | 新增 T07NoSummaryInput：rule 输入在 llm 之后、完全无摘要输入两个场景（R4 复现） |
| T04 未覆盖旧周页面日期 | 集成测试：截短窗口构建 W36 索引独有页（日期/链接/提示断言）+ Node 端周日期由同一算法计算 |
| Node 转义判断无效 | 重写为**恶意 fixture**：构造含 `EVIL<script>alert("xss-marker-9f3a")</script>END` 的记录（合法派生 ID），实际构建后断言文本以 `&lt;script&gt;` 转义出现、无未转义执行节点 |
| withdrawn 断言恒成立 | 新增真实 withdrawn fixture（合法 ID，r1 active + r2 withdrawn 修订链），实际构建后断言：页面可访问、显示"已撤回"与原因、变化摘录保留、永久链接在 |
| 报告表述过强 | 本报告"构建前校验完成"改为如实的五场景清单；T01–T12 映射表逐项注明实际覆盖方式 |

## 3. 测试命令与结果

```bash
python3 -m unittest discover -s tests -p 'test_record_archive.py'
# → OK（25 tests：T01–T09 + R2 零写入×3 + R3 修订冲突/损坏/不匹配/中断恢复 + 入口行为×2 + 无摘要输入×2 + ID 规范 + 校验×2）

python3 pipeline/scripts/archive-source-changes.py --check
# → ✓ 校验通过：9 个日期输入可映射，123 条归档一致

python3 pipeline/scripts/sync-diff-to-site.py
# → Done: 9 days, 123 changed items（幂等；未映射等输入错误时非零退出零写入）

cd site && npm run build
# → ✓ 构建门禁通过：123 条记录 / 索引 123 条一致，修订链完整
# → 154 page(s) built

node tests/records.test.mjs        # 连续两次运行均通过
# → 全部通过 ✓（16 项：索引一致/无悬空/复制按钮/恶意 fixture 转义/周入口/withdrawn fixture）

node tests/platform-logos.test.mjs
# → 既有失败（Freebuff 缺 logo，与本任务无关，git stash 对照确认）
```

R1 五场景脚本级复现（缺失目录/损坏记录/缺失索引/索引悬空/缺失修订 → 全部 exit 1；正常 → exit 0；故障后归档字节一致）见本报告第 1 节。

## 4. 归档现状

- 记录 123 / 修订文件 226 / 索引 123（恢复验证后经 sync 重建，字节幂等）
- 修订链校验：validate_archive 全量通过（含最新修订↔当前一致、无孤立修订）

## 5. 真实可预览样例

- `/item/obs_20c849f249df924b5a65af7d393417a5f9efdc86054afd931708a33a9ed95d23/`（DeepSeek · 模型列表来源更新，31 行摘录，2 版修订历史）
- 周归档 `/daily/2026-W37/`（来源变化记录区块）

## 6. 剩余限制（如实）

1. platform-logos 既有失败（Freebuff 缺 logo）未顺手修——非本任务范围
2. observedAt 全部 date 精度（上游 diff 无逐源抓取时刻）
3. 索引独有周的"分类统计不可用"是如实披露而非补算——daily_changes 窗口外的分类计数已不可得
4. 浏览器抽查（复制按钮/移动端）以开发方上次 Task 01 记录为准，本轮修复未重复浏览器操作（后端行为全部有自动化断言覆盖）

## 7. 定位声明

本任务交付**可长期引用的来源变化摘录**：稳定 ID、永久链接、修订可追溯、重跑幂等、历史不丢、构建门禁保证不出现悬空链接站点。尚未实现价格证据链（Task 02）、API/MCP/RSS（后续任务）。


## 2026-09-12 直接修复与最终复验

此前复验的 R2、R3 阻断已修复，本节取代此前“仍未通过”的当前状态；此前复现过程保留作追溯。

- R2：sync 先读取、校验和规划全部日期，LLM 摘要也并入同一计划。公共 apply_plan 在临时副本上恢复并校验已有归档、执行完整计划和校验结果，通过后才应用到真实归档。离线入口同样使用此流程。坏 JSON、未映射来源、非法条目、已有归档损坏均在真实写入前失败。
- R3：恢复前逐一检查修订身份、连续版本、修订元数据及当前记录与对应历史内容的一致性。缺失或落后的 current 从最新合法修订恢复，复用其 revisedAt；merge 与 withdraw 都使用该逻辑。损坏或冲突修订不允许用于恢复。
- 新增真实入口回归：sync 后续文件坏 JSON/未知来源/列表非法项零写入；已有归档损坏零写入；sync 与 offline 分别覆盖新建、更新、撤回时修订已落盘而 current 替换失败。重试时将时钟推进至 2030 年，确认仍复用原修订，文件字节不变且无多余版本。另验证损坏、错误身份及断链修订恢复失败时零写入。
- 验证：Python unittest discover 31 项通过；现有 123 条归档与索引门禁通过；完整临时工程副本中 sync 成功（9 天 / 123 条）、npm run build 成功（154 页）、records.test.mjs 所有断言通过（包括恶意文本和撤回 fixture）。临时工程已自动清理，未重写真实业务数据。

边界：输入及已有归档预检失败保证零写入；真正磁盘写入阶段的 I/O 中断允许已有部分修订提交，通过重跑恢复，不是整个批次的事务回滚。延续现有单写入进程运行方式。本轮未提交、部署或改动前端；既有非本任务限制仍以交付报告为准。
