# Task 01：稳定变化条目、持久归档与永久链接

状态：待实现。属于 P0-1 的第一个可独立验收任务，不等于整个 P0-1 完成。

## 1. 任务目标

让用户可以从首页的一条来源变化进入独立详情页，复制链接用于引用；同日重跑、摘要修改、近期列表滚动后，链接仍指向同一条记录。

本任务只处理 `data/diff/*.json` 中的通用来源变化。定价网页的文本变化仍可收录，但必须称“来源更新”，不能当成已验证调价。`price_changes` 结构化价格事件和价格证据补齐安排在 Task 02。

交付效果：

> 首页“今日信号明细” → “查看详情” → `/item/obs_.../` → 查看来源增删、观察日期、摘要与限制 → 复制固定链接。

## 2. 开始前必读与工作边界

- 产品依据：[产品规划 F03 与核心业务规则](./product-plan.md)、[用户故事 US-04、US-11](./user-stories.md)。
- 读取当前生效的 AGENTS.md、`site/AGENTS.md`、README、HANDOFF。
- 检查 git 状态，保留既有未提交内容；目前存在 `.workbuddy/`、`docs/product/`、演进研究文档等未跟踪内容，不清理、不顺手提交。
- 阅读 `sync-diff-to-site.py`、`diff_clean.py`、`index.astro`、`daily/[week].astro` 和现有测试，再动手。
- 只在本地实现、回填、构建和验证。未经后续指示，不 push、不部署、不安装全局 Skill、不抓取线上数据、不调用付费 LLM。
- 不进行首页重设计，沿用现有 Layout、颜色、排版和交互。

## 3. 范围

### 必须完成

- [ ] 为来源建立稳定 source_id，映射当前来源名称／类型／URL。
- [ ] 为来源日变化生成稳定条目 ID。
- [ ] 独立保存条目及修订记录，不依赖 `KEEP_DAYS`。
- [ ] 回填仓库已有的所有合法日期 diff 文件。
- [ ] 给近期 `daily_changes.json` 的 changed 条目补充 `id` 和 `permalink`。
- [ ] 新增独立详情页并从首页来源明细进入。
- [ ] 从每日周归档进入当周的来源条目，旧周详情有稳定入口。
- [ ] 实现复制链接、状态提示和基本修订展示。
- [ ] 接入现有同步和构建流程，完成必要测试及交付记录。

### 不在本任务范围

价格 fact / evidence 持久化、`/evidence` 页面、API、MCP、RSS、安装器、事件聚类、影响说明、模型别名体系、发布架构改造。

不要求本任务重建完整历史周度串讲。必须保住条目详情及周级条目入口；历史周报正文与现有 LLM 周串讲保持兼容。

## 4. 数据规则：按此实现，不另行猜测

### 4.1 source_id

新增 `pipeline/config/source_registry.json`，每个来源记录固定 ID、展示名称、source_type 和已知 URL 别名。能复用的现有平台 ID 应复用，但平台 ID 不等于 source_id。

来源 ID 一旦分配，不随平台改名或 URL 更新变化；这些变化通过 registry 的显式别名映射处理。不要用当前 URL 每次重新生成身份。回填前扫描所有现有 diff 的来源组合，确保能够唯一映射。行业来源也必须支持，不强行映射成模型供应商。

未映射或有歧义的来源明确报错并给出待补配置，不静默分配新身份。新增来源的维护说明必须包含 registry 更新步骤。同日同 source_id 出现多条输入时拒绝静默覆盖，报告冲突供维护者处理。

### 4.2 条目身份与收录

- 粒度：**一个 source_id 在一个上海日历日期的来源变化**。
- ID：`obs_` + SHA-256；输入为 UTF-8 编码的规范 JSON 数组 `[source_id, date]`，使用紧凑分隔符、保留 Unicode，完整 64 位十六进制摘要。
- 不把摘要、增删行内容、当前时间、平台展示名称或 URL 放进 ID。
- 所有 `status=changed` 的来源均可归档，包括 jitter；默认页面只列 substantive，jitter 详情标明“常规页面波动”，防后续分类变化造成旧链接丢失。
- first_fetch、unchanged、fetch_failed 不新建变化条目。
- 同日重跑修改已有记录；跨日再次变化生成不同记录。
- 若同一日期同一来源在新输入中明确为 unchanged，且已有条目，则保留原链接并标 withdrawn，原因说明“重新计算后未识别到变化”。
- 来源输入缺失、文件滚出窗口、局部抓取未包含该来源、抓取失败，都不能自动撤回既有条目。
- 撤回后再次确认 changed，允许恢复 active，留下新的修订和原因。

### 4.3 最小记录结构

字段命名可直接采用下表，不引入完整 API 框架：

| 字段 | 要求 |
| --- | --- |
| schemaVersion | 固定 1 |
| id / sourceId / date | 固定身份；date 来自原始 diff 的业务日期 |
| recordType / changeType | 固定 source_observation / source_updated |
| revision / status | revision 从 1 开始；status 为 active 或 withdrawn |
| platform / sourceType / sourceUrl | 展示元数据；URL 必须为有效 http/https 才生成外链 |
| title | 规则生成，例如“火山方舟 · 定价来源更新”；不由 LLM 推断具体事件 |
| summary / summaryOrigin | 可选，优先已有同来源 llm_summary，其次 signal_preview；分别标 llm/rule |
| observedAt / timePrecision | 能从该来源快照可靠取得抓取时间才填 observedAt；否则 null，精度 date，仅展示观察日期 |
| revisedAt / revisionReason | 记录何时修订、为何修订；无变更不更新时间 |
| kind | substantive 或 jitter，沿用现有降噪规则 |
| diff | 保存可用的 pairs、added_lines、removed_lines，以及原始计数，不再次为页面显示而截断存储 |
| evidenceLevel / diffCompleteness | 本任务 evidenceLevel=source_diff；diffCompleteness=truncated/unknown，不冒充完整证据 |
| provenance | 原始 diff 文件与来源定位信息，仅作为内部可追溯字段；不直接生成裸文件网页链接 |
| permalink | `/item/{id}/`；复制时与 Astro.site 组合成完整地址 |

原始 diff JSON 本身有增删行数量上限。超过已保存行数可判 truncated；无法判断时为 unknown。本任务不重算全量原始 diff、不发布 HTML 快照；详情使用“已保存的变化摘录”，不是“完整证据”。

父级 `fetched_at` 是整批运行时间，不直接当逐源观察时间；能确认旧时间无时区但来自设置 TZ=Asia/Shanghai 的采集记录时才按上海时区解释，否则保留日期精度。不得把回填当天写成事件发生时间。

### 4.4 修订与幂等

当前记录保存在 `data/records/<id>.json`；每个版本保存在 `data/record-revisions/<id>/<revision>.json`。旧版本不可覆盖。

以实际公开内容比较是否修订；比较时排除本次处理时间和程序生成的辅助字段。相同输入重复运行，归档文件内容与 revision 不变。

摘要、展示信息、变化内容或状态改变时沿用 ID、revision 加 1、记录原因。旧日期的摘要不因退出 daily_changes 窗口而被清空；没有新的摘要输入时保留已有值。LLM 解释与原始差异分开保存，避免摘要覆盖证据。

全部输入先校验、形成变更计划，再落盘；至少保证单文件原子替换和失败可幂等重跑。输入损坏、身份冲突时非零退出，不删旧档案、不生成半套站点数据。已有归档读取失败不允许当成空库重新初始化。

## 5. 开发步骤与文件清单

### 步骤 A：归档模块及离线入口

- [ ] 新增 `pipeline/scripts/record_archive.py`：source 映射、ID、校验、归档、修订与归档索引的纯逻辑。
- [ ] 新增 `pipeline/scripts/archive-source-changes.py`：离线回填与校验入口。
- [ ] 支持 `--diff-dir`、`--archive-root`、`--registry`，测试可在临时目录运行；默认使用仓库路径。
- [ ] 支持 `--check`：检查输入、身份、归档和版本引用，绝不写入；常规运行扫描全部合法日期输入并幂等合并。
- [ ] 非日期命名 JSON 跳过；合法日期但内容损坏明确失败。
- [ ] 新增来源 registry，并完成历史来源映射。

### 步骤 B：接入当前同步链路

- [ ] 修改 `sync-diff-to-site.py`，在保留已有 highlights / llm_summary 后完成归档合并；归档扫描全部历史 diff，近期列表仍维持现有窗口。
- [ ] 对近期 changed 注入真实归档 ID／permalink，不改变现有消费者字段。
- [ ] 生成 `site/src/data/record-index.json`，只作为可重建索引；持久源仍为 data/records 和 revisions。
- [ ] `record-index.json` 至少包含 id、date、platform、sourceId、kind、status、title、permalink，并稳定排序。
- [ ] daily workflow 前后两次 sync 不产生无意义修订；已有 highlights、price_changes 和周 story 不被删除。
- [ ] 检查 daily/weekly 的 `git add data/ site/src/data/` 已覆盖新产物；仅确有缺项时修改流程，不重做部署。
- [ ] 构建前验证索引与归档一致；缺失索引或引用时报可操作错误，不构建一个“成功但没有详情”的站点。纯部署构建不得抓网或调用 LLM。

### 步骤 C：详情页和页面入口

- [ ] 新增 `site/src/pages/item/[id].astro`：静态路由由全部持久记录生成，不从 daily_changes 生成。
- [ ] 使用现有 Layout。展示来源、日期、摘要、已保存的前后／增删摘录、完整性提示、修订列表、官方链接。
- [ ] 复制按钮复制完整永久链接；成功有反馈，失败可手动复制。
- [ ] withdrawn 或 jitter 清晰显示状态，旧页仍有内容。
- [ ] 外部文本按文本转义，禁止 `set:html` 直接注入来源行或摘要；长行自动折行。
- [ ] 首页只在“今日信号明细”的具体 source 条目增加“查看详情”；不把某一条来源记录强行关联到跨来源 LLM 要点。
- [ ] 每日周归档增加按日期组织的“来源变化记录”链接列表。
- [ ] 周路由集合取现有 weekly-digest 与 record-index 周标识的并集；索引独有的旧周提供日期与来源链接即可，缺少 LLM 串讲时不伪造。保证已归档条目不因周索引滚动而失去站内入口。
- [ ] 可返回所属周归档；正式周报路径不改。

### 步骤 D：回填、验证和文档

- [ ] 用仓库现有数据进行一次离线回填，再运行第二次核对幂等。
- [ ] 新增 `tests/test_record_archive.py`，核心用例见下一节。
- [ ] 新增 `site/tests/records.test.mjs`，检查构建详情数量、链接和转义／状态输出。
- [ ] 使用可用本地浏览器抽查首页→详情→周归档、复制按钮、移动端长行；无法完成的客户端检查如实标明。
- [ ] 更新 README/HANDOFF 中本任务涉及的归档说明、执行命令和新增来源步骤；不要顺手重写其他部署事实。
- [ ] 输出 `task-01-result.md`，记录改动、执行命令、测试结果、生成数量、真实可预览样例和剩余限制。

## 6. 必须通过的测试

| 编号 | 输入／操作 | 预期 |
| --- | --- | --- |
| T01 | 同 source 同日重复归档 | ID、revision、文件字节不变 |
| T02 | 同 source 跨日变化 | 不同 ID |
| T03 | 改摘要、显示名或经 alias 映射的 URL | ID 不变，有意义内容变化才新修订 |
| T04 | 65 个合法日期，近期列表只取 60 个 | 最早条目和所属周入口仍构建，索引覆盖全部 |
| T05 | 重跑某日明确 unchanged | 原条目 withdrawn，旧链接可读；恢复 changed 有新修订 |
| T06 | 文件缺失、来源未包含或抓取失败 | 不撤回、不删除旧记录 |
| T07 | 历史摘要不在近期窗口 | 不清空旧摘要，不无故增加 revision |
| T08 | 新来源未映射、重复来源冲突、JSON 损坏、归档损坏 | 明确失败，旧档案完好 |
| T09 | 输入只有日期、行被截断 | 不伪造抓取时刻，提示摘录限制 |
| T10 | 含 script 标签的增删行、非法外链协议 | 按文本展示，不执行；非法 URL 不成为可点击外链 |
| T11 | sync 前后两次运行 | 不丢 highlights、price_changes、story；无输入变化不增归档版本 |
| T12 | 索引引用不存在的记录或修订 | 校验／构建失败，不生成悬空页面 |

建议验证命令（coding agent 应提供对应可执行入口）：

```bash
python3 -m unittest discover -s tests -p 'test_record_archive.py'
python3 pipeline/scripts/archive-source-changes.py --check
python3 pipeline/scripts/sync-diff-to-site.py
cd site
npm run build
node tests/records.test.mjs
node tests/platform-logos.test.mjs
```

其余现有测试按改动影响运行，不需要联网或真实抓取来测试归档逻辑。新依赖若确有必要，更新锁文件并说明用途。

## 7. 完成定义与交接

全部满足才结束任务：

1. 当前仓库可回填的 changed 来源全部有稳定记录，失败和跳过项数量清晰。
2. 首页至少一条真实来源记录可进入详情，并复制完整 URL。
3. 旧条目在 65 日期测试中仍有详情页和站内入口。
4. 修订／撤回／重新激活／损坏输入均有测试，不只测正常路径。
5. 归档、索引与页面构建校验通过；未改动与本任务无关的数据和界面。
6. 交付报告明确：本任务是“可长期引用的来源变化摘录”，尚未实现完整价格证据或 Agent 接入。

报告应附：文件清单、测试命令和结果、记录／修订数量、一个真实详情路径、是否做过浏览器检查、后续 Task 02 需要复用的字段。遇到不可恢复历史数据保留限制，不用臆造内容凑验收。
