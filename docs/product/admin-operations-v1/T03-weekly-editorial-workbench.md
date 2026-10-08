# T03 高质量周报生产工作台

优先级P0｜依赖T01；按任务顺序在T02后集成｜目标：运营从真实证据生产一份可审核、可出版、可追溯成本的Plus周报。

## 1. 首版交付范围

一个统一周报工作台，支持创建期次、固定素材、选题、独立模型生成、逐项证据核验、人工编辑、审核、出版及查看投递状态。首版手动触发，支持一个供应商适配与三种模型角色配置，不建设通用工作流编辑器。

网站可读版本是首版必交付；邮件入队为明确可选项、默认关闭。提供生产worker/service配置候选，但不安装定时任务。自动抓取新网站、自动部署、每用户自由生成长文、支付系统不在本任务范围。

## 2. 必须处理的现有内容边界

仓库有两种不同交付：

- `data/weekly` → 静态周报页面/受保护HTML，用于既有`/weekly/{date}/`。
- `pro_content` → 专业详解/专题/briefing，加上`pro_reports`按个人范围组合，在`/pro/`消费。

本任务以**pro_content为新内容唯一写入源**，不同时写静态Markdown和数据库两套正文。新统一周报作为kind=briefing发布，并新增首版消费者`/pro/weekly/?id=...`，使用静态页面壳及专业鉴权API读取；从`/pro/`添加明确的新周报入口。旧周报入口和历史归档保持现状，后续迁移另立任务，UI清晰区分新周报与历史归档。

现有`compose()`明确排除kind=briefing，仅组合非样例详解/专题。因此模型输出包必须包含：①一份统一周报briefing；②可按范围组合的explainer/comparison。两者来自同一冻结证据和审核包。现有个人简报继续组合②，不声称它已包含统一周报全文。数据不足允许减少条目，不强制凑齐内容类型。

现有`report()`保留selectedVersion但读取当前已发布版本，支持更正后的最新内容；本任务不宣称读者永远看到冻结旧正文。编辑工作台必须保存当次产出与发布版本，继续沿用既有更正/撤回语义。

## 3. 页面与流程

`/admin/weekly/`展示期次、窗口、覆盖、编辑状态、最新运行、费用和负责人；`/admin/weekly/detail/?id=...`为工作台，依次有素材、生成、编辑与证据、审核、出版五个视图。

创建期次输入统计结束周一、选题说明、模型配置、预算。窗口固定为北京时间`[上周一00:00，本周一00:00)`；日期必须是真实日历日期及周一，不能仅靠Date.parse自动归一。

抓取不完整时展示缺失来源和dataThrough，由运营明确选择normal/partial/failed。完全无法支持正文时不允许出版正常分析，可形成“覆盖不足”的编辑说明；不得伪造证据来满足已有contentSchema.min(1)。零证据说明保存在期次状态，不强行导入pro_content；既有空个人简报能力另按原规则使用。

编辑界面左侧正文/表格/公共预览，右侧引用证据与核验问题。明确标注事实、分析、待核对内容；原始文本按不可信内容转义/安全渲染，不将来源文字当作模型指令。

每次编辑形成新的workbench revision，原审核失效；编辑保存不直接占用pro_content正式版本。确认审核后锁定hash，出版时一次导入对应正式版本，再进行review/publish。不能靠每次键入调用ProStore.draft。

## 4. 数据结构

通过T01迁移新增以下实体；命名可随现有代码风格调整，语义不能省略：

| 实体 | 关键字段 |
| --- | --- |
| editorial_issues | id、periodEnd唯一、windowFrom/To、datasetVersion、coverage/Note、state、currentRevision、version、createdBy/At |
| editorial_inputs | issueId、snapshotId/hash、证据ID与版本、URL、observedAt、必要摘录/结构化数值、覆盖信息 |
| editorial_revisions | issueId/revision唯一、内容包JSON、inputHash、outputHash、createdBy/At、runId可空；不可覆盖 |
| editorial_reviews | issueId/revision、outputHash、检查清单、决策、意见、reviewerId、createdAt |
| editorial_runs | id、issueId、stage、state、attempt、leaseOwner/Until、fencingVersion、inputHash、modelConfigSnapshot、budget、usage、estimatedCost/actualCost、errorCode、created/started/finished |
| editorial_publications | issueId/revision唯一、contentRefs、publishedAt、actorId、compositionState、queueMail、结果摘要 |

素材快照保存在私有数据库或shared目录受控路径，不能置于可随release清理的临时路径；若存文件必须加入备份范围并验证权限。大正文与证据不进入admin_audit，审计只记录ID、版本、hash及动作摘要。

期次编辑状态：draft → in_review → approved → published；退回为draft，已发布的修改生成新revision进入新审核。任务状态与编辑状态独立：queued/running/succeeded/failed/cancelled/needs_review。取消任务不等于撤回内容。

## 5. 模型与任务执行

角色为curator（整理/选题）、analyst（深度分析）、reviewer（独立审稿）。模型ID与推理选项由服务端配置，保存每次运行快照；不在代码写死“最强模型”。实现一个明确的供应商适配接口以及确定性测试适配器，供应商SDK和模型参数实施时查阅官方文档再确定。

生成服务输入仅含冻结素材、结构化事实、选题及提示词版本；不传用户邮箱、会话、反馈截图或个人状态。模型工具首版无shell、数据库写入、任意URL访问权限。返回必须通过schema，事实引用必须指向快照内实际ID，不能信任模型自行给出的证据真实性。

worker作为独立进程轮询数据库领取任务，短事务获取租约，事务外调用模型；心跳续租，结果写入检查fencingVersion，防止过期worker覆盖重试结果。同一期同阶段同输入最多一个活动任务，重复HTTP触发返回已有runId。

阶段依次为prepare → curate → analyze → verify。prepare/结构核验可为确定性代码；reviewer只对问题清单提供辅助意见。保存每个阶段结果，重试只重跑选定失败阶段，输入变化使下游结果失效。

每次最多2次可重试失败（总3次），仅限确认可重试的限流/暂时错误；退避并记录尝试。超时但供应商执行状态未知的请求标记needs_review，不能盲目重发造成重复费用。服务重启后过期租约进入恢复核查；取消后拒绝迟到结果，已消耗费用照实保留。

预算为每期上限，运行前估算并预留本次最大消耗，包括已失败尝试；同时限制最大输入/输出token及运行时长。若供应商不支持可计算上界，只能提供token/调用次数硬限制和金额估算，界面不得声称金额绝不超支。价格配置记录币种、更新时间与来源；缺少价目显示金额未知，不当作免费。开发默认不真实调用。

## 6. 核验、出版与个人组合

机器检查：schema、证据ID/版本、模型归属、时间窗口、价格单位/币种/地区/档位/缓存条件、表格与正文数值一致性。对不能可靠自动验证的结论列为人工核对项，不能把程序通过当作事实已全部正确。

人工必须确认：来源与适用条件、关键结论证据、覆盖限制、公开预览、无未经证实的历史/模型归属。允许单管理员兼任作者与审核人，但记录两种动作。审核记录绑定revision/hash；前端修改或后端版本变化后出版409。

现有`validateEditorial()`仅在pro-cli publish路径显式调用；后台不得直接调用transition(publish)绕过它。抽出统一出版应用服务，由CLI和admin共同调用，加载有效Dataset并重新校验；冻结输入用于追溯，当前已撤回证据会阻止出版并要求复核。

出版包中全部内容需在一个短事务内导入草稿、review和publish、记录editorial_publications及管理员审计；拆出既有事务内方法，不嵌套BEGIN。若任一内容失败，整包不部分上线。重试出版返回原publication，不能新增正式版本。

发布后的个人compose作为显式后续步骤，复用原`compose(period, coverage, queueMail)`，默认queueMail=false。执行前显示本周期已有报告数、可新建数与选项；已有报告不会更新或补发。发布成功而compose失败时展示“已出版，组合待处理”，只重试组合，不重复出版。

本任务不新增补发机制，不直接重置pro_mail的review/未知状态。仅展示pending/sent/failed/review等实际存储语义和时间；若sent只是供应商接受，页面写“供应商已接受”，不能写“已送达”。真实投递沿用已有deliverPro及授权的运行流程。

## 7. API与消费者

| 路由（均为拟新增） | 用途 |
| --- | --- |
| GET/POST /api/admin/weekly | 列表 / 创建期次 |
| GET /api/admin/weekly/:id | 当前期次、版本、审核、费用与出版摘要 |
| GET /api/admin/weekly/:id/inputs | 有界分页素材与证据 |
| POST /api/admin/weekly/:id/prepare | 固定数据快照；已有审核时变更使审核失效 |
| POST /api/admin/weekly/:id/runs | 按角色/阶段创建异步任务，202返回runId |
| GET /api/admin/runs/:id | 状态、进度、脱敏错误、费用及结果引用 |
| POST /api/admin/runs/:id/cancel | 请求取消，不能保证退还已发生费用 |
| POST /api/admin/weekly/:id/revisions | 保存人工编辑的新revision |
| POST /api/admin/weekly/:id/review | 提交审核/通过/退回，绑定revision与hash |
| POST /api/admin/weekly/:id/publish | 发布审核通过版本，返回publicationId |
| POST /api/admin/weekly/:id/compose | 显式网站组合及可选邮件入队 |

所有写入复用T01权限、原因、Idempotency-Key及expectedVersion。run有独立版本；任务详情不能返回模型密钥。草稿详情、模型输出和证据摘录只走admin鉴权。

先核对现有`pro-http.ts`的内容列表/详情路由，优先复用已能读取kind=briefing的专业接口；不足时只补`/api/pro/briefings`及详情合同。消费者必须验证当前权益，公开预览和全文分别序列化；渲染Markdown禁用/清理原始HTML及危险链接，并测试XSS。不得将专业正文注入静态HTML。

正文编辑接口总JSON上限建议1MiB；contentSchema仍保留单篇body等字段限制，总包另设最大条目数。只对精确创建revision路径放宽代理和服务端大小，其余admin保持16KiB。代理路由与后端限制一致并测试超限413。

## 8. 建议文件与实施切片

新增`editorial-store.ts`、`editorial-service.ts`、`editorial-worker.ts`、`editorial-model.ts`、`admin-editorial.ts`；重用/扩展`pro-editorial.ts`、`pro-store.ts`、`pro-cli.ts`。前端新增后台周报列表/详情和专业统一周报消费者。

按同一任务中的四个可验收切片实施：

1. 期次/快照/人工稿/审核/出版/消费者，先无模型也能完整走通。
2. 持久任务、租约与模型适配，确定性模拟器走通生成与恢复。
3. 机器核验、费用预算、个人组合与投递状态、重试及更正回归。
4. 一批真实历史素材隔离演练；有单独授权的密钥/预算时再做真实模型质量评测。

## 9. 验收矩阵

- 真正的周一边界、跨月、非法日期、素材dataThrough不足、零证据、缺失平台均有确定结果。
- 同一期重复创建不重复；并发领取任务只有一个有效worker；过期worker写回被拒绝；取消后结果不覆盖；预算不足不调用模型。
- schema错误、伪造证据、口径不一致、内容XSS进入失败/核验问题状态，不自动出版。
- 修改正文后旧审核失效；普通用户无法读草稿；未审核不能发布；证据当前已撤回时不能发布。
- 整包出版故障注入无部分可见结果；重复publish不重复版本/审计/更正队列；CLI与admin均执行同一出版校验。
- 专业新页面真实读取已发布briefing，游客/Free仅见允许的预览，Plus可看全文；静态产物无全文泄露。
- compose包含匹配详解/专题且不误称包含briefing；用户没开启专业邮件不入队；已有同周期报告不会因重试补发。
- 旧周报页面、专业内容/个人报告、更正/撤回、公共REST/MCP/RSS行为无回归。
- 使用临时数据库、冻结历史素材和本地邮件适配完成真实浏览器路径：创建→生成→编辑→审核→出版→Plus阅读。记录截图、版本、费用估算状态及证据核对结果。

必要验证：后端构建、editorial/admin专项测试、现有pro与账号回归、公共MCP相关回归、站点完整构建、代理路由测试；加入正式统一检查入口。无需为了展示进度重复跑无关全套。

## 10. 交付与限制

交付代码、API/数据合同、worker运行与恢复说明、模型配置样例（无密钥）、提示词版本、历史素材演练记录、备份/回滚说明。回滚前停止worker，保留私有快照、新表和正式出版内容；不要删队列来处理重复执行。

没有真实供应商验收时明确写“工作流与模拟适配已验证，真实模型质量/费用未验证”。周报出版时间和预算仍由维护者设置，不在开发任务中擅自开启自动发布或生产付费调用。
