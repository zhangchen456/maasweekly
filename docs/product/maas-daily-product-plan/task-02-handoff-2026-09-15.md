# Task 02 第二轮修复交接（2026-09-15 重启前快照）

> 交接背景：第一轮交付被验收驳回（[task-02-acceptance-2026-09-15.md](./task-02-acceptance-2026-09-15.md)，三项 P1 + 三项 P2 + 测试缺口）。本文件记录第二轮修复的**当前进行时状态**，供重启后继续。

## 一、环境注意事项（重启后先看）

1. **git 暂不可用**：Xcode license 过期导致 `/usr/bin/git` 报 "You have not agreed to the Xcode license agreements"。重启后需先执行 `sudo xcodebuild -license`（或 `sudo xcodebuild -license accept`），否则所有 git 操作失败。本机无 homebrew git。
2. **工作区未提交**：Task 02 全部变更（第一轮 + 第二轮修复）都在工作区，未 commit。约 31 个文件（13 个修改 + 18 个新增目录/文件，含 34MB `data/price-*` 归档）。重启不影响（都在磁盘上），但**不要在修完前误清理**。
3. 全部测试在重启前刚跑过：`test_price_archive.py` 34 项 OK、extractor 回归 OK、`archive-price-evidence.py --check` 通过、四个 py 文件语法 OK。

## 二、六项验收问题的修复状态

| # | 验收问题 | 状态 | 关键改动 |
| --- | --- | --- | --- |
| A1 (P1) | 同日重跑用错误日基线 | ✅ **已完成并验证** | `_baseline_before` cutoff 改为目标日上海零点（两入口同步）；入口级验证：同日 5→10→8→9 始终与前日基线 5 比（-10% 而非 8→9 的 +12.5%），回到基线无事件；2 个测试固化（`TestSameDayFixedBaseline`） |
| A2 (P1) | 契约错误被吞掉继续提交 | ✅ **已完成并验证** | 在线入口改两阶段：`_plan_provider_archive`（内存构建）→ `_commit_archive_plan`（全量预检零写入 → 统一落盘）；`except pa.ArchiveError: raise` 直通不再降级为抓取失败；测试 `TestTwoPhaseCommit`（后源冲突零写入 + 幂等重放） |
| A3 (P1) | complete 不证明证据支持事实 | 🔶 **进行到一半** | 详见下节 |
| A4 (P2) | 证据页构建重复全库扫描 | ⬜ 未开始 | |
| A5 (P2) | 门禁一致性盲区 | ⬜ 未开始 | |
| A6 (P2) | 证据页"未知时间" | ⬜ 未开始 | |

## 三、A3 当前状态（重启后从这里继续）

**已完成的改动**：

1. `archive.py` 新增 `verify_evidence_for_fact(excerpt, fact)`：绑定事实验证（模型/金额+币种紧邻/单位三要素可复核），`fact_evidence_status()` 组合形态级+事实级判定。金额匹配已修复为「币种符号紧邻」正则（`$10`/`¥10`/`10 元`），修掉了任意数字误命中。
2. 两入口已接线：`fetch-prices.py` `_plan_provider_archive` 与 `archive-price-evidence.py` 回放路径都在形态 complete 后追加 `pa.fact_evidence_status(new_evid, f_dict)`。
3. `extractors.py` 新增 `_with_heading_context()`：表前置标题（sourceline 距离 <30 行）并入证据摘录 `<p>标题</p>前缀`——解决 google 模型名在表外的问题。
4. `archive.py` `html_excerpt_to_text()` **刚改完**（重启前最后一个 Edit）：保留摘录中的 `<p>/<h1-4>/<caption>` 标题文本行，再接表格行。**此改动尚未跑过全量验证**。

**验证数据**（标题并入 html_fragment 后、html_excerpt_to_text 修复前）：

```
anthropic: complete 85
glm:       complete 15, partial 16
kimi:      complete 12
qwen:      complete 1883, partial 141（unit_not_in_excerpt）
google:    partial 75（model_not_in_excerpt——html_excerpt_to_text 丢标题导致，刚修）
openai:    partial 140（unit_not_in_excerpt：表内金额行无 'token' 字样，单位在页面表外说明——真实证据粒度缺口）
deepseek:  partial 12、doubao: partial 268（未细查原因）
TOTAL: complete 1995 / partial 652
```

**重启后的下一步**：

1. 跑 `python3 -m unittest discover -s tests -p 'test_price_archive.py'` + `python3 tests/test_pricing_extractors.py` 确认 `html_excerpt_to_text` 改动无回归（`TestHtmlSafety.test_html_excerpt_strips_script` 可能受影响，注意 `<p>` 保留与 script 剥离的交互）。
2. 重跑上面的八家绑定质量评估脚本（在对话历史里有，或按 `data/snapshots/2026-09-11/pricing__<p>.html` 全家重放），确认 google 75 条 model 问题随标题保留而解决。
3. 对 openai（140 unit 缺失）、deepseek（12）、doubao（268）逐家判断：真实证据粒度缺口 → 如实 partial 是正确行为（验收要求"绑定到事实"，不在摘录内的单位不能算可复核）；若发现是误判（如单位线索其实在某行但没匹配上）再修 verify 逻辑。
4. **注意**：`_with_heading_context` 改变了 `html_fragment` → 证据 excerpt 变化 → **证据 ID（ev_）会变**。真实归档 `data/price-evidence/` 里已落盘的旧证据不可变保留；重放会产生新 ID 证据。这是预期行为（证据不可变，新摘录=新证据），但会导致「同一快照两套证据并存」。可接受，但交付报告需说明。
5. 真实归档重放（A3 完成后）：`python3 pipeline/scripts/archive-price-evidence.py`（全量重跑，幂等），更新索引，再跑 `--check`。

**A3 完成判据**：验收要求的三类反例测试——错金额、错模型、共享表串证据——不误判 complete。需补进 `test_price_archive.py`（建议类名 `TestFactEvidenceBinding`）。当前 `verify_evidence_for_fact` 的模型/金额/单位检查已具备判定基础，直接写测试即可。

## 四、未开始项的操作要点

**A4（证据页构建性能）**：`site/src/pages/evidence/[id].astro` 的 `getStaticPaths` 里一次性扫 `data/price-facts/versions/` 建 `evidence_id → facts[]` 索引，通过 `props.relatedFacts` 传给页面（页面删掉现在的逐页全库扫描）。优化前先记录完整构建时间做基线（当前分钟级，实测单证据路由 185-205ms）。

**A5（门禁盲区）**：`archive.py` `validate_price_archive` 补五项——(1) 高于 current.revision 的额外修订文件（现有循环只查 1..top）；(2) 证据 ID 从 `[snapshotContentId, locatorType, locator, excerptHash, extractorVersion]` 重算比对；(3) 证据 ↔ psnap 内容关联（snapshotContentId 存在性）；(4) current 的 fact_key 对应关系与最新版本指向；(5) run 记录 state 只能是 committed/prepared、prepared 残留检测。每项配一个篡改 fixture 的失败测试。

**A6（证据页时间）**：证据记录没有 observedAt（内容寻址设计，时间在事实版本里）。两个选项：(a) 证据页删掉"未知时间"标签，改为说明"证据内容身份与观察时间无关，观察时间见关联事实"；(b) 从关联事实取时间范围展示。建议 (a)+(b) 组合：删除标签、在关联事实区展示各事实观察时间（已有）。

## 五、文件清单（本轮全部变更）

修改：`pipeline/pricing/archive.py`（verify_evidence_for_fact/fact_evidence_status/restore_event_from_revisions/_commit_event 签名幂等/html_excerpt_to_text 标题保留）、`pipeline/pricing/extractors.py`（anthropic 5m/1h time_condition、_with_heading_context）、`pipeline/pricing/view_data.py`（effective_at/evidence_link）、`pipeline/scripts/fetch-prices.py`（两阶段提交/前日基线/--only 合回/sh_today）、`pipeline/scripts/archive-price-evidence.py`（前日基线/fact_evidence_status 接线）、`site/src/pages/item/[id].astro`、`site/src/pages/evidence/[id].astro`、`site/src/pages/daily/[week].astro`、`site/src/pages/index.astro`、`site/src/data/pricing/price-ledger.template.html`、`site/package.json`、HANDOFF.md、`site/src/data/pricing/ledger.json`（evidence_link 迁移）

新增：`pipeline/scripts/validate-price-archive.py`、`tests/test_price_archive.py`（34 测试）、`data/price-{facts,evidence,snapshots,runs,records,record-revisions}/`、`site/src/data/price-{record,evidence}-index.json`、本文档、task-02-inventory.md、task-02-result.md（需在全部修复后更新 §4/§5.1）

## 六、验收复验标准（全部完成后自查）

按 task-02-acceptance-2026-09-15.md §复验通过标准：

- [ ] A1/A2/A3 三项 P1 修复且有入口级失败/恢复测试
- [ ] A4 构建优化 + 记录前后构建时间
- [ ] A5 五个门禁盲区各有反例测试
- [ ] 真实在线抓取一次（新采集验收）——**需要你确认时机**，fetch-prices 全量跑一次约几分钟
- [ ] T16 完整 workflow（含 llm-digest，需 LLM_API_KEY 环境）
- [ ] Task 01 回归 / extractor 回归 / Task 02 单测 / 三归档校验 / 全站构建全绿
- [ ] 更新 task-02-result.md（如实记录第二轮修复过程与数据）

## 七、重启后的快速恢复命令

```bash
sudo xcodebuild -license accept          # 恢复 git
python3 -m unittest discover -s tests -p 'test_price_archive.py'   # 34 项应全绿
python3 tests/test_pricing_extractors.py                            # 八家回归
python3 pipeline/scripts/archive-price-evidence.py --check          # 归档校验
# 然后从「三、A3 当前状态 → 重启后的下一步」继续
```
