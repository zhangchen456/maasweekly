# Admin API v1

T01 实现合同，2026-10-04。复用现有 account session 与 SQLite。Free/Plus、Bearer、请求体中的 actor/role 均不授予后台权限；每次请求重新检查有效 session 和 enabled administrator。

## 路由与响应

所有响应（含错误）为 JSON，`Cache-Control: no-store`、`Vary: Cookie`、`X-Content-Type-Options: nosniff`、`X-Request-ID`。仅 GET/POST；其余405。POST须 Origin 精确匹配 MAAS_ACCOUNT_ORIGIN，cross-site 请求403。T01不提供HTTP授权或业务写接口。

| GET | 响应 |
| --- | --- |
| `/api/admin/me` | `{id, displayName, role: "administrator", capabilities: ["overview:read", "audit:read"]}` |
| `/api/admin/overview` | `apiTime,datasetVersion,dataThrough,database,releaseVersion`，每项 `{value,asOf,availability}` |
| `/api/admin/audit` | `{items,nextCursor}`；每项 `id,actorType,actorId,action,targetType,targetId,reason,before,after,requestId,createdAt` |

摘要 availability 为 available / unavailable / not_provided。API发布版本当前无可靠来源，固定 null / not_provided；asOf为本次API检查时间，不代表数据更新时间。时间字符串为ISO，审计createdAt为Unix毫秒。

审计筛选 action/targetType/targetId 为精确匹配；from/to为含时间及时区的ISO字符串（含端点）；limit默认25、1–100。未知/重复参数400。排序createdAt DESC,id DESC；签名游标绑定归一化筛选条件，改变筛选须丢弃cursor。nextCursor为null表示结束。分页不承诺跨页数据库快照，新增记录从首屏刷新获取。

错误统一 `{code,message,requestId}`，状态401未登录、403权限/来源、404不存在、409版本/幂等冲突、413超限、415类型、429限流（Retry-After）、503不可用；非法参数400、方法405。内部异常只返回通用503，不暴露SQL或请求正文。拒绝诊断仅将code/requestId送入现有有界JsonlLogger，不写业务审计表。

## 后续写入复用

1. `admin-auth.ts authenticateAdmin(req,store,secure)`取得真实用户；不得读取 body actor。
2. `admin-http.ts adminWriteInput(req,fields,user.id,requestId,action,targetType,targetId,currentVersion?)`校验 Idempotency-Key（1–128）、JSON（16KiB）、未知字段、必填reason（1–1000）；可变对象提供同步currentVersion函数并要求expectedVersion非负整数。认证和来源检查必须在读取正文之前。
3. `AdminStore.command(command,auditFields,resultFields,work)`执行一个BEGIN IMMEDIATE事务：检查资格、幂等→版本→同步业务→白名单审计→脱敏结果→提交。currentVersion与work都不得await或启动异步任务，不调用现有自带transaction的服务方法；拆出事务内SQL实现。错误整体回滚，不保存失败幂等或业务审计。
4. work返回 `{result,before,after}`，before/after可null；显式字段白名单，每份≤4KiB，只允许标量或标量数组，不允许凭据字段。结果只放小型脱敏ID、状态、版本。不要传用户输入正文、附件或模型生成全文。
5. 相同actorType/id、action、key及规范化请求重放原结果，跳过版本检查与工作，不重复审计。同键不同内容409。重试须保留原Idempotency-Key与请求内容。版本冲突409，前端重新读取；不得自动用新版本覆盖。不同请求ID不改变幂等含义。

CLI actorType固定cli，命令记录actorId内部使用`type:id`隔离；审计actorId保存显式操作者标识。首版幂等表不自动清理。迁移版本统一放admin_schema_migrations，后续版本依次在事务内增加，不改既有迁移含义。

## 前端复用

`site/src/layouts/AdminLayout.astro`提供静态noindex壳与仅已完成模块导航；`site/src/lib/admin-client.ts`导出adminApi、AdminApiError、AdminIdentity、AdminSummary、AdminPage、AdminAudit。使用现有AccountAccess及onAccountChange刷新鉴权；后台资格和返回数据不放localStorage。401/403清空私有DOM，409提示重新读取；异步响应用generation阻止注销后迟到数据重现。新增模块复用这些类型与状态处理，内容通过textContent渲染。AdminLayout允许新的slot模块；maas:admin-ready事件携带已确认身份，maas:admin-cleared事件要求模块清空自身内存与DOM。模块自身请求仍须捕获AdminApiError并处理401/403/409，不缓存权限。

## T02 用户、权益与反馈（2026-10-04）

统一鉴权/错误/16KiB正文/Origin/幂等/事务规则不变。`me.capabilities`新增 users:read、users:write、feedback:read、feedback:write。overview增加pendingFeedback（当前内部阶段非resolved，包括尚未处理的新反馈）；asOf为查询时间。

| 路由 | 合同 |
| --- | --- |
| GET users | q（邮箱包含检索或完整userId）、entitlementStatus=active/free、source=beta/manual；默认25，最多100 |
| GET users/:id | 账号白名单、profile.profileCreated（资料建立时间，非注册时间）、effectiveEntitlement、manual、beta、betaAvailable、watchCount、免费/专业邮件偏好、adminVersion、最多100条凭证元数据、近30天事件按类型汇总、最近25条管理审计及nextCursor |
| POST users/:id/entitlement | operation=grant/revoke；grant要求starts/ends为带时区ISO时间；revoke无需时间；reason/expectedVersion必填 |
| POST users/:id/revoke-sessions | 撤销所有网页会话；reason/expectedVersion必填 |
| POST users/:id/tokens/:tokenId/revoke | 仅可撤销此用户所属专业凭证；reason/expectedVersion必填 |
| GET feedback | userId/stage/priority/from/to（ISO时间含端点）、cursor/limit |
| GET feedback/:id | 原公开字段、userSummary、ops、notes/verifications各最近25条及各自nextCursor |
| GET feedback/:id/notes、verifications | 各自cursor/limit分页，不接受其他筛选 |
| GET feedback/:id/images/:index | index仅0/1/2；管理员读取，no-store/nosniff/CSP sandbox；原所有者端点不变 |
| POST feedback/:id/update | 可选stage/priority/publicReply/resolutionType/relatedFeedbackId；reason/expectedVersion必填 |
| POST feedback/:id/notes | body为1–4000字；追加，reason/expectedVersion必填 |
| POST feedback/:id/verify | kind=code/content/data/other、artifactRef、releaseRef（code必填）、result=passed/failed、note（1–4000字）、environment（code须online）；reason/expectedVersion必填 |

详情和图片不接受查询参数；POST不接受查询参数。用户不存在404，凭证不属于用户404，管理版本/幂等冲突409。写结果为`{updated:true,version,...}`，用户操作另返回最终status/source，反馈返回stage。不返回任何hash/encrypted/unsubscribe/RSS secret；内部备注与验证记录只在admin接口及显式私有CLI详情中提供。

用户查询排序id DESC；反馈按unfinished DESC（非resolved为1）、updatedAt DESC、id DESC；备注createdAt DESC/id DESC，验证checkedAt DESC/id DESC。签名游标绑定路由、对象、排序和筛选，不可跨列表/更改筛选使用。默认25，最多100；筛选在LIMIT之前完成，非跨页快照。有效权益的纯判定函数由原ProStore.entitlement及查询层共用，包含PRO_BETA_ENABLED；没有手工记录时仍沿用原API的source=manual/status=pending口径。

授权与撤销在AdminStore.command事务内调用ProStore.grantInTransaction，保留pro_audit/pro_events和取消pending专业邮件的副作用。公测有效且未撤销时优先；手工grant不会开启邮件、生成支付记录或删除公测。revoke优先保留现有手工starts/ends；若没有记录，以服务器now为starts、now+1ms为ends建立合法revoked标记。该标记阻止公测与手工权益；后续grant清除revoked，可能恢复公测优先。时间需安全整数且starts<ends。adminVersion仅覆盖管理服务和更新后的CLI，用户自行改资料/公测激活不纳入该版本，不改变原行为。

反馈公开映射triage→open，resolved→resolved，其他阶段→investigating。所有写入（包括备注和验证）更新ops.version/updatedAt/operatorId并审计，内部正文不入审计或幂等结果。publicReply最多2000字。引用最多500字，仅http(s) URL或普通标识，拒绝其他URI协议/带凭据URL；显示为转义文本，不请求引用URL。relatedFeedbackId可null，必须存在、不能自身或成环，重复关联使用other处理依据；不删除原反馈。

新解决要求非空公开说明、resolutionType及该类型最近追加的passed验证。code额外要求修复引用、releaseRef及environment=online的验证说明；content/data要求更正引用与核验说明；other要求处理依据与检查说明。最近failed覆盖之前passed，即使同毫秒；重开后须重新追加验证，依据审计版本比较，不能复用上次解决的记录。允许回退或重开，统一reason记录原因。验证记录是操作者留存的材料，本任务不自动部署、请求引用链接或替操作者执行线上验证。

Migration 2在admin_schema_migrations记录，事务内创建admin_user_versions/feedback_ops/feedback_notes/feedback_verifications和查询索引，回填旧公开状态；历史resolved的resolutionType=legacy且无虚构验证。迁移可重复，失败整体回滚；新用户反馈的ops在首次管理写入建立，读取时视为triage/version=0。服务启动及T02 CLI自动迁移。应用回滚保留新表和历史；旧版本仍可读原公开状态和权益，但回滚期须暂停管理写入和旧CLI，以免绕过版本/审计。

CLI：feedback list仍输出数组（最多100），新增adminVersion；export仍私有并只导出原公开字段与图片。status仍接受ID open/investigating/resolved [reply]，新增必填--actor、--reason、--expected-version；支持--key及--resolution-type。detail供读取完整私有详情/版本，verify接受JSON材料，同样要求版本/操作者/原因。pro grant/revoke保留原EMAIL START END ACTOR NOTE参数位置，新增必填--expected-version及可选--key；revoke不使用START/END，建议传`- -`占位；pro user EMAIL|ID供读取白名单详情/adminVersion。旧命令缺版本明确失败，不能静默覆盖网页变更。重试应保留--key与完全相同参数。

## T03 周报生产（2026-10-04）

Migration 3在原私有账号SQLite新增editorial_issues/inputs/revisions/reviews/runs/publications；冻结快照和不可覆盖稿件随账号库备份。pro_content为唯一出版源：briefing是统一周报，explainer/comparison用于个人报告。静态产物没有专业正文。

写入继续使用管理员session、Origin、reason、Idempotency-Key及expectedVersion。仅POST weekly/:id/revisions允许1MiB，其他16KiB；候选nginx精确匹配revision路径。未知字段拒绝，内部异常返回通用503；409要求刷新，不自动覆盖。

| 路由（/api/admin/前缀） | 合同 |
| --- | --- |
| GET/POST weekly | GET limit默认25、1–100，cursor为最后periodEnd。POST periodEnd真实周一、selection、budget（USD 0–10000）、reason；模型配置由服务端冻结。同一期重复创建返回已有ID。 |
| GET weekly/:id | 返回期次/版本、最新稿件内容包/检查、最近各25条审核/任务/出版及报告数量/邮件状态汇总；不接受查询参数。 |
| GET weekly/:id/inputs | limit/cursor偏移分页，total/snapshotId；旧快照保留。每次最多冻结500条观察，截断明确披露。 |
| POST weekly/:id/prepare | coverage=normal/partial/failed、coverageNote、reason/expectedVersion。冻结有效数据集北京窗口观察的ID/revision/hash/URL/时间/摘录/价格口径与覆盖；批准失效、旧输入活动任务取消。零证据只存覆盖说明。 |
| POST weekly/:id/revisions | package={contents:[ProContent]}、reason/expectedVersion；恰好一份briefing，总计最多12篇、ID唯一且以editorial-PERIOD-开头，sample必须false。每次保存新增revision、批准失效；正式版本只在出版时分配，更正需原ProStore要求的correction说明。 |
| POST weekly/:id/review | decision=submit/approve/reject、revision/outputHash、checklist、note、reason/expectedVersion。批准要求in_review且证据未变；sources/conditions/conclusions/coverage/preview/attribution全部true；机器阻塞项不能跳过。 |
| POST weekly/:id/publish | revision/outputHash、reason/expectedVersion。批准与hash必须吻合，当前有效数据集再次检查撤回/缺失/修订证据。整包draft/review/publish、出版记录、admin审计与幂等结果一次事务；同key返回原结果，已有出版的新key不新增正式版本或业务审计。 |
| POST weekly/:id/compose | queueMail显式boolean、reason/expectedVersion。要求当前版本已出版；既有报告不改写/补发。组合失败只回滚组合，出版仍可读，publication保留pending供重试。 |
| POST weekly/:id/runs | stage=prepare/curate/analyze/verify、reason/expectedVersion，202返回runId。分析依赖本输入成功选题，独立审稿接当前稿件；按期次/阶段/输入/提示词/配置/上游去重。输入截断披露，不自动出版。 |
| GET runs/:id | 不接受查询参数；状态/attempt/租约/fence/version/配置/实际输入数/用量/已知费用/估算/结果；不返回密钥或完整输入包。 |
| POST runs/:id/cancel | reason/expectedVersion针对run版本；增加fence，拒绝迟到正文，已知费用保留。取消运行中的真实模型仍需核查供应商结果。 |
| POST runs/:id/reconcile | outcome=executed/not_executed、note（供应商材料）、actualCost（累计USD或null）、reason/expectedVersion；只处理needs_review/cancelled。材料存私有usage历史，增加fence转failed，允许显式重试。未知结果不盲目重发。 |

任务领取用短BEGIN IMMEDIATE事务，模型调用在事务外；30秒心跳、5分钟租约。过期running转needs_review，旧worker不能写稿。分析期间人工修改阻止覆盖。只有明确429拒绝最多自动重试两次并退避；网络/超时/5xx/未知usage进入核查。每期最多30次模型尝试。输入字节保守视作token上界，限制max_completion_tokens及运行时长；有价格时每run预留三次最大估算，计入整期预算，失败/取消不自动释放。缺报价时金额未知，只声称调用/token/时长边界；mock明确标注模拟，不代表质量或费用验收。

MAAS_EDITORIAL_CONFIG为无密钥的严格JSON，创建期次保存配置快照，后续文件变更不改已有期次。MAAS_EDITORIAL_ALLOW_PAID默认false；真实OpenAI Chat Completions还需OPENAI_API_KEY。curator/analyst/reviewer分别配置模型ID和reasoning。price为运营提供的所有角色保守共同费率，必须带USD、更新时间与来源；usage费用按快照计算，不等于供应商账单。price=null不等于免费。来源摘录是不可信数据；模型无工具和任意外部URL权限。

读者复用/api/pro/catalog预览和/api/pro/content/:id当前权益全文。/pro/weekly/?id=CONTENT_ID只显示已出版briefing，采用转义文本，禁用原始HTML与危险链接；游客/Free只见预览。个人组合排除briefing和样例；selectedVersion保留，但读取最新已出版更正。邮件sent表示供应商已接受，不表示送达。本任务没有状态重置、实际发送、定时或自动出版。

## T04 流量与内容使用分析（2026-10-04）

`GET /api/admin/analytics`复用管理员session、限流、no-store、Vary: Cookie与统一错误，新增`me.capabilities=analytics:read`。仅GET，POST405；不接受其他参数或重复参数。异步Umami查询完成后再次验证session/管理员资格，期间注销或撤权不可取得结果。

查询：`preset=7|28|custom`，默认7；custom要求`from/to=YYYY-MM-DD`，开始与结束日期均包含。默认北京时间Asia/Shanghai，内部[start,end)；近7/28天含今天并结束于当前时刻，custom未来结束截到now、未来开始拒绝，跨度最多366天。不使用浏览器时区。

返回`{range,business,website}`：range有start/end（Unix毫秒）、from/to（北京日期）、timezone。business.asOf是本地查询时间；coverage={availability:available|partial,completeSince}，表示所选范围是否早于补充采集起点，不保证应用停机期间仍有流量。registrations含count、coverage、historicalUnknown（当前账号中注册时间未知的存量，非窗内新增）。profilesCreated只称资料建立；betaActivated来自唯一pro_beta_access记录，不是付费。professionalReads={requests,accounts}为content_read/report_read/weekly_read；exports来自content_export/report_export。requests是事件条数，accounts按非空userId去重；sample_read/sample_export不计专业内容读取/导出；旧content_export中目标已有样例标记者也排除。

weekly={items,truncated}最多100项，按readers DESC/id排序；项有id/kind（briefing或legacy_weekly）、requests/readers/returningReaders。统计范围中有读取的正式专业briefing及历史日期入口、范围中出版但尚无读取的非样例briefing均展示，同ID多版本只算一期。回访要求同账号/同目标在至少两个不同北京日期读取，跨入口不强行合并；更正按内容ID汇总，不提供按版本历史读者。个人报告不是统一周报。历史weekly_read混合公共结构化周报和私有HTML读取，不能声称所有历史读取都是专业分析全文。

agents={coverage,failures,items}：按北京日的HTTP响应完成汇总，channel为public_api/public_mcp/pro_api/pro_mcp；pro_api只记录带Authorization的/api/pro/请求（不含MCP）。requests含失败响应，httpSuccess为HTTP2xx。MCP包含协议初始化/目录/工具等请求，可能一次请求多工具或HTTP200内工具失败，不称工具数/真实Agent数/注册账号。专业成功工具另由events.agent_tool_success呈现，目前仅read/weekly/reports；每次实际成功执行记录一次，重试执行为新调用。采集失败计数尽力写入，数据库整体不可写时不能保证故障计数完整。

activation7d与retentionWeek4返回numerator/denominator/immature/minimumSample=5/rate/status及coverage。注册7天激活：所选窗新注册且now>=created+7天才进入分母，激活必须在[created,created+7天)。第4周留存：全历史已记录的第一条专业读取位于选定窗且不早于migration4完整采集起点；满28天观察后才进入分母，再读取必须在[first+21天,first+28天)。起点前已记录读者排除，但未采集的历史不能还原，因此只称“首次已记录读取队列”。分母0为no_denominator，1–4为insufficient_sample，rate=null；>=5才提供比例。未成熟不计分母。

website.available返回stats={pageviews,visitors,visits}、pages/sources（label/count）、rankingUnit=views(v3)|visitors(v2)、limit=20、asOf、lastSuccessAt。v3 path/referrer排行为浏览量，v2 url/referrer按其访客合同；不相加为全站访客，不算来源转化。label最多300字、去除URL凭据/query/fragment，前端纯文本。unavailable时stats/pages/sources为null、reason=not_configured/query_failed/busy、lastSuccessAt为本服务任意范围最近成功查询时间或null，不返回陈旧数值或伪造零。真正成功返回0允许显示0。

服务端配置MAAS_UMAMI_TOKEN（仅私有环境变量），MAAS_UMAMI_ENDPOINT默认https://api.umami.is/v1/us、MAAS_UMAMI_WEBSITE_ID默认现有公开ID、MAAS_UMAMI_VERSION默认v3，兼容显式v2。不创建/修改Umami账号、key或追踪配置；自托管可将endpoint配置为受信实例/api并使用现有Bearer凭据。仅HTTPS或localhost/127.0.0.1 HTTP，拒绝URL凭据/查询/fragment，禁重定向，未知schema视不可用。各查询4秒超时、响应128KiB，三个外部请求全部settled；每进程最多4个范围并发、15秒最多10个范围查询（30个外部请求），同范围请求合并。缓存成功结果60秒，结束时间按分钟归并，保留最近32范围；故障不覆盖最近成功时间，缓存的asOf显示实际查询时间。多进程额度独立，Cloud服务总额度需运营留余量。

Migration4在admin_schema_migrations中事务创建account_registrations、analytics_requests、analytics_health、analytics_umami_cache与时间/事件/目标索引，不回填注册历史。新注册在AccountStore.verify的同一新建用户事务写入真实clock时间，userId主键去重；注册失败整体回滚。数据库尚未迁移时原账号流程兼容，但这段历史不回填。应用启动先执行migration4再接受请求；MCP事件只在业务读取成功后记录。回滚保留表/索引，不DROP；旧应用不采集新增指标，恢复时需披露采集缺口。没有统计导出、支付、调度、生产配置变更或T05功能。

## T05 信源质量与日常任务

2026-10-04，本地实现；生产采集未接入。沿用每请求管理员鉴权、no-store、同源写入、16KiB正文、版本与幂等事务。不提供HTTP导入、任意日志路径、任意shell、抓取/发布重试接口。

| 接口 | 结果与参数 |
| --- | --- |
| GET `/api/admin/monitor/sources` | `{items,asOf,truncated}`；平台`platform`、健康`health`筛选。固定目录最多500个；不接受cursor。items含id/name/platform/kind/budgetHours、latestAttemptAt/latestSuccessAt/dataThrough、consecutiveFailures/failureCountTruncated、health/freshness、coverage/outcome/errorSummary、runId/runLink |
| GET `/api/admin/monitor/runs` | `{items,nextCursor}`；kind/state/sourceId/runId；limit 1–100默认25；observedAt/id降序、HMAC游标绑定筛选。含类型、触发、状态、阶段、时间、输入/输出版本、result/validation/publication、脱敏摘要、关联来源、受控链接。T03任务直接从原表投影，不复制config/payload/result/secret |
| GET `/api/admin/monitor/runs/:id` | 同一白名单详情，不接受query；未知ID为404 |
| GET `/api/admin/monitor/anomalies` | `{items,nextCursor}`；state/sourceId；limit与游标同上。含id/runId/sourceId/code/state/version/createdAt/updatedAt/resolutionRunId/summary |
| POST `/api/admin/monitor/anomalies/:id` | `{state,reason,expectedVersion,resolutionRunId?}`；Idempotency-Key必填。state为acknowledged/in_progress/ignored/resolved；返回id/state/version/resolutionRunId，审计action=`monitor.anomaly.update`、targetType=`monitor_anomaly` |

处理状态仅改变队列。解决必须关联observedAt更晚、state=succeeded的记录；来源异常要求同sourceId、success/unchanged、full覆盖且真实successAt晚于异常；任务异常要求相同kind，校验失败还要求validation=passed，发布失败还要求publication=completed。没有人工任意“验证通过”字符串入口。409版本冲突先刷新；幂等重放复用原结果，不新增审计。

时间是UTC epoch毫秒或null，展示北京时间；null=未知，绝不使用归档日期/导入时间代替抓取成功。result枚举success/partial/failed/unchanged/not_run/unknown；state复用T03 queued/running/succeeded/failed/needs_review/cancelled。validation为passed/failed/not_run/unknown；publication为completed/failed/not_run/unknown。成功执行不自动设置另外两项。T03 verify成功可投影passed，其生成任务不表示出版。

来源健康根据记录确定：无记录unknown，最新not_run单列，失败或partial/missing为degraded，否则真实成功距查询时刻超过budgetHours（默认48h）为stale，无成功时间为unknown；其余normal。48h是记录新鲜度预算，不是上游变化承诺。连续失败只数有attemptAt的记录，not_run不增加/重置；有界读取最多501条并披露截断。最近成功/dataThrough用已记录最大值，失败不回填，数据截至只取已成功快照的观察时间。注册表别名共享sourceId时合并最大真实时间、任何失败保持可见、不同覆盖为partial。未注册的旧内部source key明确kind=unmapped。

采集协议v1：JSON包严格字段`schemaVersion=1,batchId,sources,runs`，最多4MiB/500来源/500运行；所有字段必填（可空为null），未知字段拒绝。source字段`id,name,platform,kind,budgetHours`。run字段`id,kind,trigger,state,stage,startedAt,finishedAt,observedAt,inputVersion,outputVersion,result,validation,publication,errorCode,runLink,sources`。来源观察字段`sourceId,attemptAt,successAt,dataThrough,outcome,coverage,errorCode`；outcome=success/unchanged/fetch_failed/parse_failed/failed/not_run/unknown，coverage=full/partial/missing/unknown。错误仅固定枚举：fetch_failed/parse_failed/fetch_or_parse_failed/validation_failed/execution_failed/interrupted/coverage_missing/unknown。runLink只允许无query、无凭据的`https://github.com/OWNER/REPO/actions/runs/NUMBER`；链接供管理员进入GitHub权限控制的诊断，不代理原日志。

受控CLI `monitor import BASENAME.json` 从显式MAAS_MONITOR_INBOX绝对真实目录读取basename（禁止符号链接、路径穿越、任意path、超过4MiB）；由受信运维帐号供给白名单投影。API进程不读inbox、不持有生产抓取/SSH/GitHub/模型密钥。完整采集包单SQLite事务写入，batchId及runId+规范化hash去重，同ID内容变化409并回滚整包。导入无业务操作授权含义，只记采集回执；采集包不是浏览器上传API。

migration5增加monitor_sources/runs/observations/anomalies/receipts及查询索引；运行/来源观察不可覆盖，异常操作与audit/admin_commands同事务。中断journal或stage回执按内容哈希产生独立needs_review快照，恢复后原runId的成功终态可作为后续证据，不覆盖历史。运行中的原journal不导入为已失败，外部任务实时状态不假冒T03租约状态。

## T06 邮件投递与服务健康（2026-10-04，本地）

沿用T01管理员session、no-store、Origin、限流与统一错误；写入reason、expectedVersion、Idempotency-Key必填，16KiB，未知字段/重复query拒绝。`me.capabilities`增加delivery:read/write、health:read。API进程不读取inbox、原邮件文件或任意运维路径，不执行shell/SSH/systemctl。所有操作以真实管理员身份审计。

| 路由 | 合同 |
| --- | --- |
| GET `/api/admin/delivery` | `{items,nextCursor}`，type=digest/pro、state=queued/sending/accepted/delivered/failed/unknown/cancelled、user（完整userId或邮箱字面子串）、from/to（带时区ISO，包含边界）、limit=1–100默认25。按created/id倒序，签名游标绑定全部筛选。筛选在LIMIT之前执行 |
| GET `/api/admin/delivery/:id` | id为`digest:JOB_ID`或`pro:JOB_ID`；无query。白名单用户/邮箱、入队时间、原业务报告ID或普通摘要eventKey（最多101）、租约、provider/messageId、状态时间、version、各最多100次尝试与证据、可用动作。不返回mail/payload、退订令牌、RSS凭据或专业正文 |
| POST `/api/admin/delivery/:id/retry` | 无query、无自由状态字段。只允许最新状态failed且存在provider_rejected未接受尝试、无供应商消息ID、当前偏好/权益允许。仅把原任务重新入队，原ID/冻结mail/供应商幂等键不变；没有创建报告、营销群发或历史补发能力。事务审计action=delivery.retry，targetType=mail_delivery |
| POST `/api/admin/delivery/:id/reconcile` | 只核对unknown/accepted/failed，读取已验证供应商最新证据；无证据拒绝，不允许人工输入pending/已送达或任意供应商ID。核对成功的状态/版本/审计/幂等结果一次事务，action=delivery.reconcile。送达终态不能被后续accepted事件降级；矛盾的后续事件仍保留详情供人工排查 |
| GET `/api/admin/health` | 无query；`{asOf,items,operation}`。项含kind、status=normal/abnormal/unknown、source、checkedAt、value、stale、有外部记录时lastStatus/budgetSeconds；缺失或超过预算当前unknown，保留最近记录结果。不提供重启、回滚、恢复或通知API |

原任务表兼容保留pending/sent/review/cancelled。`pending + lease=0`投影queued；有效租约投影sending；过期租约/历史review投影unknown；历史sent仅accepted且消息ID/发送时间未知。新增mail_delivery覆盖准确状态，mail_attempts记录每次尝试开始/结束、租约、结果、固定错误、供应商ID，mail_evidence保存去重证据及实际事件时间/收到时间。新版发送失败立即review：明确400/401/403/422/429拒绝才failed，其余异常/5xx/超时/无有效接受ID为unknown。租约过期立即review，停止原先5分钟后自动重发；23小时旧策略由更保守的“所有未知先核对”替代。无有效匹配项取消，不能虚构供应商接受。发送前重查偏好（pro另查有效权益）；发送中退订/撤权不能抹去实际接受/未知。租约值防迟到结果覆盖，尝试结果仍保存。

接受后保留原sent兼容，但不称送达。只有认证查询last_event=delivered或验签email.delivered证据核对后才显示delivered，意义为收件服务器接受，不表示打开/阅读。local适配只保存私有outbox并返回模拟消息ID，不证明真实送达。

T06加法表：mail_delivery、mail_attempts、mail_evidence、service_checks；sender独立幂等建mail表，后台/CLI登记migration6。原业务表/去重唯一约束不变，不DROP或回填虚构尝试；历史状态读取时投影。所有新增表随原SQLite backup备份。

受控CLI `delivery health BASENAME.json`、`receipt BASENAME.json`、`local-receipt BASENAME.json`：沿用T05真实绝对inbox、basename、NOFOLLOW、4MiB、私有DB协议（变量MAAS_DELIVERY_INBOX）；API不能调用导入。receipt envelope只含raw与headers（三个svix字段）；精确raw HMAC-SHA256验签、constant-time比较、签名时间±5分钟；保存事件created_at，拒绝未来/不匹配的已保存消息ID，按provider+svix-id去重，内容冲突拒绝。支持email.sent/delivered/bounced/failed/delivery_delayed；不存原正文/其他收件人字段。local-receipt仅非production且无MAAS_RELEASE_DIR；必须使用独立本地签名密钥。真实签名密钥MAAS_MAIL_RECEIPT_SECRET仅运维CLI持有，不进入后台Web。inbox投送必须及时，过期包需供应商真实重放，不能改签名时间。

`delivery query TYPE:JOB_ID`仅运维CLI：从已保存resend消息ID请求固定HTTPS供应商GET、认证、禁重定向、5秒超时/128KiB。401/403/404/5xx、超时或未知schema不证明未发送，不改变任务。只保存ID/状态，不保留供应商返回正文。Retrieve API只提供last_event而无事件发生时间，timeBasis=query的eventAt明确是查询观察时间；签名回执timeBasis=event保留实际created_at。已验证delivered证据优先并保持终态；其余证据按eventAt，乱序不覆盖较新状态，同时间优先failed/accepted/unknown。供应商事件时间不与本机发送完成时间比较。核对accepted之后仍可以查询/收到delivered后再次核对；failed回执如bounce已有消息ID，永不可重试。

health离线严格对象：id、kind=api/mail/release/backup/restore、status、checkedAt（UTC毫秒）、budgetSeconds=60–2592000、source、value（null或200字符安全标识）。kind-source必须匹配：api/account-maintenance.health（原SQLite/邮件队列/备份检查，非HTTP连通性）；mail/mail.adapter；release/release.status或release.verify；backup/account-maintenance.backup；restore/account-maintenance.restore。同ID规范化内容hash去重/冲突拒绝。仅受信运维提供，来源标签不是后台主动执行证明。

健康额外实时项：api_runtime=当前鉴权请求与SQLite SELECT 1；data=DatasetHolder存在且无lastReloadError（不返回原错误）；release_runtime=当前进程MAAS_RELEASE_DIR严格RID basename，无文件读取，本地unknown；collection=最近T05 monitor_run结果，48h记录预算，缺失/过期unknown，失败/needs_review/partial异常。运行版本不是全站online验收。最近导入发布状态与验证记录和运行版本分开展示。

既有account-maintenance新增可选`--admin-records INBOX`，只在实际执行后记录结果，不新增调度/通知。backup成功后分别记录backup及restore；restore仅说明第二个隔离SQLite副本的integrity/foreign-key及表内容比较通过，不代表生产全机恢复或应用可用性。失败backup异常、restore未知，不根据文件存在/mtime生成恢复证据。health记录最终含systemd依赖的实际结果；未指定新选项完全保留原行为。release、mail的记录由现有受控运维检查材料白名单供给；没有部署自动采集器。

## T07 问题、诊断与修复

仅管理员鉴权，沿用 Origin、JSON、no-store、Vary Cookie、requestId、安全审计/事务幂等及冲突409。新增能力 problems:read/write。所有 POST 必须 reason 和 Idempotency-Key；创建之外必须 expectedVersion（问题版本）；不接受 actor、未知字段或查询串。请求上限16KiB。创建使用幂等键确定内部ID，重复原请求返回同一问题。

- `GET /api/admin/problems?repairStage=&limit=&cursor=`：repairStage过滤、更新时间/ID签名分页（25默认、100上限）。
- `POST /api/admin/problems`：title/description，可选 reproduction/versionInfo。
- `GET /api/admin/problems/ID`：problem（含 selectedFixId/selectedReleaseId）、有效links、相关用户ID、最近100 references/checks、最近25诊断runs、developerTask。仅私有运行时读取，不进入用户反馈API或公共内容。
- `POST .../update`：title/description/reproduction/versionInfo；不修改反馈状态。
- `POST .../link|unlink`：kind=feedback/user/content/anomaly/run/problem、relatedId、confirmed=true。content格式ID@VERSION；run复用T05监控ID（如 editorial_UUID/diagnostic_UUID）。反馈只属一个当前问题，解除保留原反馈；问题有向边禁止循环。
- `POST .../references`：kind=repository/issue/pr/commit/release、value、trust=manual/verified/query_failed、source（实际来源与核验说明）、非manual必须 checkedAt（带时区ISO真实查询时间）。verified 是管理员人工查询声明，不是系统自动核验；返回 entryId，引用只追加、不覆盖。
- `POST .../remove-reference`：refId；必须本问题有效引用，保留记录active=0并回到pending。
- `POST .../progress`：repairStage=pending/candidate/merged/released/verify_pending/verified、需要时 refId/releaseRefId；merged及之后需 confirmed=true 与原因中的实际证据。candidate 起要求本问题有效verified PR/commit；released之后要求有效verified release；verified要求该二者最新线上check passed。保存 selectedFixId/selectedReleaseId；不关闭关联反馈。
- `POST .../verify`：refId、releaseRefId、environment=online、result=passed/failed、note；修复/发布引用均需有效已查询核验，跨问题/解除/人工链接/查询失败拒绝。failed回pending，passed到verify_pending；checks有操作者/时间与独立记录。
- `POST .../diagnose`：material={description,reproduction?,versions?,errorSummary?,redactionConfirmed:true,screenshots?:[{feedbackId,index:0..2}]}、budget（问题累计USD上限，0..10000）。绝不自动读取原邮箱、备注、凭据、截图或日志；截图最多3项，必须当前关联反馈，单独冻结并明确选择，管理员负责脱敏。返回runId/state，HTTP不执行模型。
- `POST .../cancel-run`：runId；只能取消本问题queued/running，提高fence；执行中取消结果未知不能直接重发。
- `POST .../reconcile-run`：runId、outcome=executed/not_executed、note、actualCost=非负数/null；只能本问题needs_review/cancelled，保存核查用量后转failed供人工重触发。

诊断 taskType=problem_diagnosis、promptVersion=diagnosis-v1、MAAS_DIAGNOSTIC_CONFIG 独立配置、MAAS_DIAGNOSTIC_ALLOW_PAID 独立开关，默认mock。T03模型配置/适配、预算估算、错误类型及共享超时/租约/fencing复用，数据写diagnostic_runs并实时投影至T05（kind=diagnostic、stage=diagnose、validation=unknown、publication=not_run）。诊断无editorial issue/revision或正式内容写入。执行状态queued/running/succeeded/failed/needs_review/cancelled；三次429退避、问题30次硬限、独立预算3次预留与已知用量、未知不得自动重发、取消迟到只记录费用。详情仅截图引用，不含base64；监控不含材料/配置/模型正文。

建议输出固定 `{facts:[{text,source}],missingInformation:[string],possibleCauses:[{cause,evidence:[source],uncertainty}],reproductionAndValidation:[string],repairDirections:[{direction,impact}],advisoryOnly:true}`。来源只可引用选定description/reproduction/versions/errorSummary或feedbackId:index；错误schema/来源待人工核查。所有输出仅为建议，不自动宣称根因、改变状态、执行命令、创建外部issue/评论或合并/部署。T02反馈detail追加 problems安全内部摘要供跳转；原用户feedback接口不变，最终resolved仍需逐条T02验证与公开说明。

## T08部分候选接口

`GET /api/admin/payments/orders|subscriptions|refunds|events|differences`沿用管理员鉴权、签名分页与no-store；订单详情`GET /orders/:id`。`POST /orders/:id/refund`接amount（最小单位整数）/reason，返回pending退款请求；`POST /differences/:id/annotate`接note/reason追加处理记录。两者使用原Idempotency-Key/command事务/审计，不执行真实供应商调用。`GET /payments/totals?currency=USD&from=ISO&to=ISO`为内部核验成功支付/退款，手续费及结算unknown。

用户`/api/pro/billing`与本机模拟checkout/simulator-result/cancel复用网站session/Origin保护；Bearer管理仍拒绝。模拟回调`/api/payment/webhook`独立原始字节签名，不使用用户Origin；仅loopback origin+simulator模式开放，202只表示持久接收，可recover。正式供应商schema与worker尚未实现，不能当正式支付API合同放行。状态/权益见paid-subscription-v1.md，缺口见T08-implementation。

### T08恢复交付补充

支付列表新增userId/from/to筛选；orders/subscriptions/refunds/differences/reconciliations提供详情；`GET /payments/differences/:id/actions`签名分页读取追加处理记录。`GET /payments/totals?reconciliationId=ID`只接受这个参数，使用冻结快照币种/时间范围，提供providerRevenue/providerRefunds/fees/settlement；缺记录为null，不与未知混为零。订单创建总额orderGross及orderCount独立，不作为收入。所有金额最小单位整数，时间[start,end)。

mutation拒绝查询参数；退款amount必须JSON number安全正整数。成功退款事实与请求终态一次事务；模拟已知成功不能改成失败释放预留。用户billing只允许网站session；专业Bearer无财务读取权限。

T08迁移9为paid_event_jobs可重建处理投影，后续迁移从10开始。readonly PaymentEventWorker带超时/租约/fence/10次未知查询上限；CLI retry-lookup需expectedVersion、key、actor、reason并使用T01 command事务审计，只核查、不重付款/退款。实际供应商写入任务未实现、真实沙箱未验收。

### D01：T03/T05同窗口覆盖核验修订（2026-10-04）

T03详情新增monitorCoverage及coverageBasisChanged。只读关联monitor_observations/monitor_runs，不使用信源当前全局health来判断历史周。来源集合来自该统计窗口active Dataset.changes的精确sourceId，不按厂商猜测；attemptAt在北京时间半开窗口内，排除not_run。每来源读取最新有效观察；inputVersion/outputVersion若明确为ds_公开版本，必须与当前Dataset一致，否则排除；其他命名空间或null仅能标versionRelation=unknown，不能据此忽略同窗口失败。保留observedAt、attemptAt、成功/覆盖截至、运行ID和输入/输出版本便于核对。新成功/unchanged且full不会被当作失败。

monitorCoverage显示缺失/partial/失败及projectionConflict；公开status缺失、unknown或ok与已知监控限制不一致时显式披露。公开来源失败只在同source且lastAttemptDate落入该统计窗口时影响normal，不以无关或任意历史全局失败阻塞所有期次。依据hash同时绑定Dataset版本、窗口、来源、相关公开来源状态与最新相关监控观察；导入时间或无关记录不改变hash。

prepare新增可选monitorAcknowledgedHash。存在相关限制时normal返回409 monitor_coverage_conflict；partial/failed必须提供与详情当前依据相同的hash并填写覆盖说明，前端用独立确认框传入，不自动确认。冻结coverageInfo.monitor，inputHash含该依据。approve/publish重新计算，不匹配返回409 coverage_basis_changed，要求重新冻结、更新稿件与审核；旧库没有该依据时同样要求重新冻结，不自动给旧审核补签。重新冻结沿原规则取消活动任务、批准失效。

不自动修改公开Dataset或已出版内容，不删除/解决T05异常，不发送任何投递。只读取已有迁移5表；T05未导入的监控记录无法被推断，界面monitorAvailable明确标示。无需新增数据库迁移。
