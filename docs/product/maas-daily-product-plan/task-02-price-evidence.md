# Task 02：结构化价格变化与证据回查

状态：待实现，可作为 coding agent 执行任务。日期：2026-09-12。

前置：Task 01 稳定来源记录已实现，用户已确认部署完成。本任务继续 P0-1 的“信息可核对”，不代表查询服务、Agent 接入或整个 P0 已完成。

## 1. 目标与用户体验

用户从价格台账或每日价格变化进入详情，能够核对：哪个平台的哪个模型、哪种计费条件、原币种金额与单位、前后变化，以及当时保存的来源依据。

两条必须打通的路径：

1. 价格台账 → 某个具体计费项的“证据” → `/evidence/{id}/` → 当时摘录、完整条件、官方来源、观察时间。
2. 首页或每日周归档的价格事件 → `/item/price_.../` → 前后金额与条件 → 分别打开前后证据。

定价网页文字更新仍是 Task 01 的“来源更新”。只有同条件下的结构化金额比较，才能称为价格上涨或下降；新增价格事实只称“新增收录价格”，不能据此断言模型刚上架。

产品依据：[产品规划 F04 与业务规则](./product-plan.md)、[US-03、US-05、US-08、US-11](./user-stories.md)。复用 [Task 01](./task-01-stable-records.md) 的稳定链接、修订和失败恢复原则。

## 2. 工作边界

- 开始前读取当前 AGENTS.md、`site/AGENTS.md`、README、HANDOFF，检查工作区和当前代码；文档里的现状是本次编写时的观察，执行时须复核。
- 本任务文档授权范围为本地实现、已有快照回放、测试和预览。不包含自动提交、push 或部署；发布阶段等待用户明确指示。此前 Task 01 的上线指示不自动延伸为 Task 02 发布许可。
- 优先使用已有价格提取、校验、台账及静态站架构。正常开发验证不依赖联网抓取或付费 LLM。正式启用门槛见第 8 节。
- 不重设计首页，不引入数据库、账户、价格推荐、成本估算、模型别名工程、API、MCP、RSS或发布系统重构。
- 不发布来源全文或原始 HTML；网页只展示核价必要摘录。内部快照用于追溯，不从本地文件路径生成外链。
- 不将无关工作区文件纳入修改、提交或清理。所有故障注入在临时目录或隔离工程中进行。

## 3. 已有实现与真实缺口

| 位置 | 当前能力 | 本任务要补齐 |
| --- | --- | --- |
| `pipeline/pricing/base.py` | ContentSnapshot、Evidence、PriceFact、稳定 fact_key | 版本与证据持久化契约；统一时间单位 |
| `pipeline/pricing/extractors.py` | 产生证据 ID、locator、excerpt | 检查摘录能否支持具体金额及条件；处理 HTML 表格和多页来源 |
| `pipeline/pricing/normalize.py` | 检查事实引用的 Evidence 在内存中存在 | 校验持久证据、摘录及快照关联，不以 ID 存在代替证据充分 |
| `pipeline/pricing/factdiff.py` | new / changed / missing 比较 | 严格比较口径；来源完整性约束；身份变化不冒充涨跌 |
| `pipeline/pricing/view_data.py` | 价格事实序列化与展示归一化 | 保留原始单位、effective_at、版本及证据引用；兼容现有显示 |
| `pipeline/scripts/fetch-prices.py` | 抓取、失败沿用、台账、每日 history、price_changes | 保存证据和不可变事实版本；正确基线、局部更新、零事件重算及恢复 |
| `pipeline/scripts/record_archive.py` 与 `validate-archive.py` | 来源归档、修订恢复与构建门禁 | 接入价格记录和证据校验，同时保持 `obs_` 契约不变 |
| `site/src/pages/pricing.astro` 与价格模板 | 已有台账 | 精确到计费项的证据入口与数据状态 |

必须显式处理的现状：

- `fetch-prices.py` 当前只把 Evidence 映射成官方 URL，没有把 Evidence 对象保存下来；`ledger_history` 内的 evidence_id 不能直接视为可公开访问的证据。
- `events_from_diff` 当前固定输出 `unit=per_1m_tokens`，不能照搬到新事件。必须保存并展示真实 `unit_quantity` 和 `unit_name`。
- `ContentSnapshot.fetched_at`、`PriceFact.observed_at` 注释写 epoch ms，但 provider 使用 `time.time()`，当前链路实际以秒传递。需检查全部生产者和消费者后统一，不能直接按注释转换历史值。
- `fact_to_dict` 当前遗漏 `effective_at`；它只能来自官方来源，未知值为 null，不用观察日期补齐。
- 当前历史基线跳过今天，失败沿用也使用该基线；同日先成功后失败可能回退到昨天。最新成功状态与日变化基线必须分开。
- 当前每日快照同名覆盖，无法承载同日多个版本；现有历史 JSON 仅作为兼容数据，不能是新证据的唯一持久源。
- 当前零事件时不会覆盖 `price_changes`，可能遗留已失效事件；局部抓取不能清空未运行来源。
- 部分 excerpt 是 HTML 整表或仅表头；仅将其写成 JSON 不满足核价要求。

## 4. 数据契约

### 4.1 稳定身份和不可变版本

保留现有 `fact_key` 八维身份：provider、model、component、region、billing_mode、service_tier、context_band、time_condition。不要迁移既有 fact_key 算法；本任务新增版本 ID，与 fact_key 区分。

新增 ID 统一采用前缀加完整 SHA-256，规范 JSON 使用 UTF-8、保留 Unicode、对象键排序、紧凑分隔符。Decimal 金额规范化后再计算身份，`1.0` 与 `1.00` 不应产生价格变化。

| 对象 | 建议身份输入 | 存储与用途 |
| --- | --- | --- |
| 快照内容 | `[source_key, content_sha256]`，前缀 `psnap_` | 同内容复用；快照观察时间放在事实观察中，不覆盖旧观察 |
| 公开证据 | `[snapshot_content_id, locator_type, locator, excerpt_hash, extractor_version]`，前缀 `ev_` | 不可变，摘录或定位变化产生新 ID；上游短 ID 仅作 provenance |
| 事实版本 | `[fact_key, 原币种金额与单位, 全部条件, effective_at, observed_at, evidence_id]`，前缀 `pfv_` | 不可变；引用准确的观察与证据。新抓取即使价格相同也可产生新观察版本，但不产生价格事件 |
| 每日价格事件 | `[fact_key, 上海日历日期]`，前缀 `price_` | 同日稳定 URL，与 Task 01 一样 revision 递增；跨日不同 |

哈希字段的具体规范化函数须集中实现并测试，禁止不同入口各自拼接。amount 用 Decimal 字符串，禁止二进制浮点参与比较或百分比计算。单位、币种不在现有 fact_key 内，变化时保留事实身份，但比较结果不得误称涨跌。

建议持久目录：

- `data/price-facts/versions/<pfv_id>.json`：不可变事实版本。
- `data/price-facts/current.json`：fact_key → 最新已接受版本 ID，可重建；失败状态单独保存，不能修改旧版本。
- `data/price-evidence/<ev_id>.json`：证据正文及快照元数据。
- `data/price-snapshots/<psnap_id>/`：内部内容及元数据，新快照不覆盖旧快照。
- `data/price-runs/<date>/<run_id>.json`：来源范围、成功／失败／未执行、完整性、接受的事实版本、基线及提交状态。
- `data/price-records/<price_id>.json`、`data/price-record-revisions/<price_id>/<revision>.json`：价格事件当前版和历史。
- `site/src/data/price-record-index.json`、`price-evidence-index.json`：可重建展示索引。

价格记录与 `obs_` 分目录，避免现有恢复器和验证器假定身份字段造成冲突。可抽出通用原子写入／修订逻辑，但不得直接把 PriceFact 塞进只接受 source_observation 的函数。`/item/[id].astro` 从两个索引生成路由，按类型渲染。

### 4.2 价格事实必存字段

保留 fact_key、provider_id、model_key、component、amount、currency、unit_quantity、unit_name、region、billing_mode、service_tier、context_band、time_condition、effective_at、observed_at；增加 version_id、source_key、evidence_id、evidence_status、schemaVersion 和 provenance。

- 新公开归档时间采用含时区 ISO 8601；现有台账数字时间保持秒单位兼容，转换集中在适配层。历史无法确认时区／单位时置空并标明时间精度，不使用文件 mtime、回填时间或批次发布时间。
- source_key 复用价格 registry，如 `openai:pricing`。需要关联 Task 01 时做显式映射，不把两个 registry 的 ID 当作天然相等。
- context_band 的 `min/max` 与 dataclass 的 `min_input_tokens/max_input_tokens` 在适配层统一，无上限与未知不得混淆。
- 缺失币种、单位等关键字段不以默认值伪造“已校验”。不支持的条件保留原文并降低证据状态。
- 展示汇率换算与原始事实分开；汇率变化不生成官方调价事件。

### 4.3 证据契约与充分性

证据必须有 id、snapshot_content_id、source_key、官方 URL、content_hash、locator_type、locator、extractor_version、excerpt_text、excerpt_hash、completeness 和 provenance。完整性值为 complete / partial / unavailable，具体缺项用 reasons 数组列出。

“complete”至少满足：摘录能找到对应模型、计费组件、金额及单位，并包含理解该金额所需的区域／阶梯／时段等条件。金额行与脚注分离时保存必要的多段摘录及各自定位。仅有表头、URL 或一个无法解释的数字不算完整。

- 每个事实引用的证据内容必须支持该事实；同一表格证据可被多个事实引用，证据页明确列出对应条件，不将表内最低价格泛化到整款模型。
- HTML 转安全纯文本或结构化表格，保留核价语义；excerpt_hash 对实际保存的摘录计算。页面不执行来源 HTML、脚本或来源中的指令。
- Kimi 等多子页聚合保留实际子页 URL 和定位。无法分辨来源子页时标 partial，不能伪称精确定位。
- 上游截断或定位失败必须披露，不能仅凭提取成功标 complete。
- 源网站后续变化不影响本站已保存证据；旧事实版本始终指向原证据。

### 4.4 事件、基线与涨跌计算

每日事件对比“该日期之前最后一个成功接受的事实状态”与“该日最新成功接受状态”。日内重跑始终使用同一日基线；没有基线时建立初始台账，不虚构调价。回填按上海日期顺序执行，不用机器今天选择历史基线。

事件保存 id、date、recordType=`price_change`、fact_key、beforeVersionId、afterVersionId、changeType、changedFields、comparison、revision、status、revisionReason、permalink。新增收录允许 beforeVersionId=null；引用旧事实但证据不完整时必须披露。

- changeType：amount_changed、terms_changed、newly_observed。币种／单位变化属于 terms_changed；不做跨币种换算后判涨跌。
- 只有模型、平台、组件、全部条件、币种、单位一致且前值大于零，才计算 `(新值−旧值)/旧值×100%`。不能将输入项下降说成整体成本下降。
- 旧值为零、未知值、条件改变或缺证时不输出未经支持的百分比，明确原因。
- fact_key 因区域／阶梯等条件改变而变化，保留新条件事实；没有可靠映射时不自动配对旧事实，不将现有 identity_migrated 启发式当作已确认迁移或下线证据。
- 来源成功、覆盖完整且明确重算后无事件：撤回该日该范围既有事件，保留链接与原因；恢复变化时新增修订。同日一度涨价后回到基线也遵循此规则。
- 来源失败、未执行、抽取局部缺行、历史输入缺失均不自动撤回。缺失价格行不等于模型下线。
- 兼容已有 price_changes 的 provider/model/component/previous/current 等消费者字段；新增稳定 id、permalink、真实单位及版本引用。只更新本次完整处理范围，不能清除未运行来源事件。

### 4.5 失败、部分结果与原子写入

来源最新成功状态用于失败沿用；日期之前的状态用于日比较，两者必须独立保存。`--only` 没有执行的来源保留其现有状态与事实，不能从全站台账消失，也不能标为本次抓取失败。

来源级状态保存 latest_attempt_at、last_success_at、status、reason、coverage。抓取失败沿用最新成功的事实版本及证据，保留 observed_at；stale 是当前使用状态，不重新写成今天观察的事实。全部失败且有历史时明确显示沿用旧数据；没有历史时明确失败，保留原产物，不生成正常空台账。

抽取部分成功也需处理缺行／拒绝事实。无法证明来源全量覆盖时标 partial，不据此删除旧事实或撤回事件。重复 fact_key 若内容冲突必须报错，禁止用字典最后一项静默覆盖。

全部输入、已有归档、引用和计划在真实写入前预检。先保存不可变证据及事实版本，再提交运行记录与当前引用，最后生成派生台账／事件／索引。中断后按已提交版本恢复，不能生成不同时间戳而冲突。运行记录应区分 prepared / committed，消费者只读取 committed；允许保留尚未引用的已校验准备文件，不把半次写入作为有效发布。

提供真实的 `--check` 和 `--dry-run`：不得创建目录、快照或改写文件。现有 fetch 的 dry-run 仍会保存快照，需要修正或提供明确隔离的替代入口。I/O 中断可恢复不等于全批次事务回滚，交付说明不得混称。

## 5. 页面要求

### 证据详情

`/evidence/{ev_id}/` 由持久证据生成，显示来源、观察关联、摘录、相关事实和计费条件、完整性提示、官方链接与复制入口。相同证据被多次观察复用时，列出关联观察时间或明确时间来自所选事实，不把证据内容身份误当唯一抓取时刻。

不完整历史证据有可读说明；完全无法恢复时事实 evidence_id=null，页面不生成虚构的证据链接。已有公开证据不能因近期列表滚动消失。

### 价格台账与事件详情

- 台账每个可核价组件提供正确证据；如果一行合并多个组件／档位，应能选择对应事实，不能整行随意指向第一个 evidence。
- 修改 `price-ledger.template.html` 等源模板和数据适配，不只修改构建生成的 fragment/rendered 文件。
- 价格事件展示前后金额、单位、条件、各自观察时间和证据；与 source_observation 使用不同标题和标签。
- 首页现有价格变化块与每日周归档补“详情”入口。周路由集合加入价格索引，测试只有价格事件的旧周仍可访问。
- 保留旧 source_observation 详情、来源外链、摘要、周 story 和价格台账现有筛选／币种展示能力。
- 桌面与移动端长摘录可读；来源文本转义，非法 URL 协议不可点击；复制成功有反馈，失败可手选文本。

## 6. 开发顺序与交付文件

按以下顺序推进；每阶段完成后继续下一阶段，不以数据结构写完作为任务结束。

1. **盘点和契约**：统计现有事实、来源和快照覆盖；列出时间单位、证据充分性及无法恢复样例。固定 ID、时间和目录规则，输出到本任务交付报告。
2. **持久化模块**：建议新增 `pipeline/pricing/archive.py`，封装事实版本、证据、运行记录、预检和恢复；新增 `archive-price-evidence.py` 离线入口，支持 `--history-dir`、`--snapshot-dir`、`--archive-root`、`--check`、`--dry-run` 及日期范围。
3. **采集与比较接入**：修改 fetch、normalize、factdiff、view_data 及必要 extractor；所有生产和离线入口共用规则，修正失败沿用、局部范围与日基线。
4. **迁移已有数据**：回放仓库现有快照，核对重提取结果与原历史事实。只对能验证一致的事实建立证据关联；不要用新版 extractor 的不同结果无声覆盖历史金额。输出 complete / partial / unavailable 数量与原因。
5. **页面与同步**：新增证据页、价格类型详情和索引；台账、首页、周归档连通；sync 与 LLM 处理不能丢引用或覆盖事实。
6. **构建门禁与工作流**：在现有 npm prebuild 扩展验证；检查 daily/weekly 的产物提交覆盖所有持久数据。只构建的 deploy 流程不得抓网、补证或静默修复损坏数据。
7. **验收和交付**：运行第 7 节测试，打开真实本地样例，输出 `task-02-result.md`；更新 README/HANDOFF 的维护命令和数据目录，保留未完成项的明确状态。

旧 history 可继续供既有消费者读取，但新持久归档成为事实与证据的追溯源。新旧结构通过适配层连接，不要求一次重写全部价格系统。

## 7. 必须通过的验收

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T01 | 同一离线输入运行两次 | 证据、事实版本、事件 ID／revision 与归档字节不变 |
| T02 | 新观察，价格和条件不变 | 更新有效观察关联，不新增价格事件；旧观察与证据仍保留 |
| T03 | 同条件价格 10→8 | 输入组件明确下降 20%，前后证据均指向真实事实 |
| T04 | 旧值 0、币种或单位变更、区域／阶梯不同 | 不产生无效百分比或跨条件配对 |
| T05 | 同日多次更新及返回日基线 | URL 不变，修订正确；回到基线撤回，恢复变化重新激活 |
| T06 | 同日成功后失败、跨日失败 | 沿用最新成功事实与证据，观察时间不前移也不回退到更早基线 |
| T07 | --only、单源失败、部分抽取、全部失败 | 未运行来源保留；缺行不当下线；全失败正确提示而非正常空数据 |
| T08 | 后续文件坏 JSON、重复身份冲突、已有归档损坏 | 真实生产／离线入口非零退出，真实业务文件零写入 |
| T09 | 写完证据／事实、提交运行、替换 current、生成派生数据各阶段中断 | 重跑恢复；无悬空引用、不改旧版本；推进时钟重试仍稳定 |
| T10 | 证据仅表头、摘录缺金额／单位／脚注、聚合页定位未知 | 降低完整性，不能标结构化已校验；给出具体原因 |
| T11 | 历史缺快照、旧时间未知、重提取金额不匹配 | 不补造证据或时间，不篡改原事实；报告恢复覆盖 |
| T12 | 超过 60 天及只有价格事件的旧周 | 事件、证据、所属周入口仍构建可达 |
| T13 | 缺证据、事实版本缺失、索引悬空、hash 不符、修订链损坏 | 实际 npm run build 非零退出；已声明缺证的历史记录正常展示限制 |
| T14 | 含 script／恶意 HTML／非法 URL 的 fixture | 证据页和台账安全转义，无执行节点，非法外链不可点击 |
| T15 | 台账多组件、多档位、移动端长行、复制 | 每个入口对应正确事实；内容可读，复制内容正确且反馈有效 |
| T16 | 正常 workflow 顺序回放：sync→fetch fixture→LLM 数据保留→sync→build | highlights、story、来源记录、价格证据引用均保留，无重复修订 |
| T17 | --check 与 --dry-run | 目录与文件逐字节比较无变化，不抓网执行离线验证 |
| T18 | 新鲜／过期与证据完整性组合 | 两类状态独立：完整证据可以是旧价格，新观察也可能缺证 |

测试必须覆盖真实入口，不能只调用内部 helper。新建、更新、撤回至少各覆盖一次 current 写入前中断，并确认历史文件保留原字节。页面安全和失败恢复使用隔离 fixture，不修改真实记录模拟故障。

建议实现以下验证入口，命令在交付时必须实际可执行：

```bash
python3 -m unittest discover -s tests -p 'test_price_archive.py'
python3 -m unittest discover -s tests -p 'test_pricing_extractors.py'
python3 -m unittest discover -s tests -p 'test_record_archive.py'
python3 pipeline/scripts/archive-price-evidence.py --check
python3 pipeline/scripts/validate-archive.py
cd site
npm run build
node --test tests/price-evidence.test.mjs
node --test tests/records.test.mjs
node --test tests/pricing.test.mjs
```

推荐新增文件名是实施要求中的目标入口，当前尚不存在，不得在未实现时报告执行成功。已有无关测试失败单独列明，不顺手扩大范围修复。

## 8. 完成定义与上线门槛

本地实现完成须满足：

- [ ] 台账→证据、价格事件→详情→前后证据，两条链路用真实已存数据可体验。
- [ ] 新标为“结构化已校验”的价格 100% 有 complete 且可访问的证据；缺证者明确降级，不借用其他事实证据凑覆盖率。
- [ ] 现有价格 registry 的全部来源均有 fixture 回放结果，逐来源报告证据完整率和缺项；至少覆盖输入／输出、缓存、区域或上下文阶梯、时段等不同条件。
- [ ] 历史回填范围以仓库现有文件为限，全量扫描并报告恢复率；不要求凭空补齐全量历史。
- [ ] T01–T18 通过，Task 01 归档、修订和网页入口没有回归。
- [ ] 临时文件清理，源码、文档、运行命令及可复现样例交付齐全。

正式启用前还需至少一轮新采集的完整链路验收，不能把旧快照回放称为新抓取验收。若当前只授权本地实现，应在报告中列为“待新采集验收／待发布”，交付其余结果；后续获得用户指示后执行现有正常采集与部署流程，不为此增加新的付费服务。

`task-02-result.md` 必须包含：文件清单、命令与退出码、每来源事实及证据数量、complete / partial / unavailable 分布、历史恢复限制、异常与中断验证结果、真实本地链接、浏览器验证情况、是否完成新采集验收及是否部署。不要把“所有 evidence_id 存在”写成“所有价格已核实”。
