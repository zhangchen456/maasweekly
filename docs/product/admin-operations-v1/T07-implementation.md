# T07 问题辅助诊断与修复关联

2026-10-04，本地实施与隔离验收。入口 `/admin/problems/`、`/admin/problems/?id=PROBLEM_ID`，反馈详情可双向跳转。保留已有 T01–T06 和发布相关改动；未部署生产、调用付费模型、发送真实消息、改仓库或启动 T08。

## 依据与实际改动

读取当前全局 AGENTS.md、site/AGENTS.md、ops/README、后台 README/development-order 和 T01–T06 交付记录，核对 AdminStore/T02 feedback、T03 editorial-store/service/model/worker、T05 monitor 和 T06 delivery/health、原内容出版更正与发布验证路径。继续沿用 Astro 静态壳及鉴权 API；页面路由依据 [Astro 路由文档](https://docs.astro.build/en/guides/routing/)。

新增 `admin-problems.ts`、`diagnostic-worker.ts`、`model-task-runtime.ts`、`tests/admin-problems.test.ts`、`site/src/lib/admin-problems-client.ts`、`site/src/pages/admin/problems/index.astro`、`scripts/admin-problems-browser-flow.py`。扩展 admin-http、admin-feedback、admin-monitor、editorial-model/worker、API package scripts、AdminLayout/admin.css、原反馈客户端、page-models、run-all-tests 非quick门禁和浏览器统一入口；更新合同及本交接。不修改已有反馈实体与用户状态，不增加另一套工单状态。

问题关联反馈、用户、确切专业内容版本 `ID@VERSION`、T05 信源异常、原任务运行及有向相关问题。反馈同一时间只归属一个问题，可先解除后重新归并；关联与解除都需管理员 confirmed，并在事务内检查对象存在、禁止自关联/循环。原反馈及用户可见说明保留，归并不写用户反馈状态。问题的 repairStage 只表达修复进度，verified 也不自动关闭反馈；逐条在 T02 保存该反馈影响范围、通过的线上验证及公开说明，才可 resolved。验证失败后可回到 pending；T02 仍支持重开并要求新验证。

关联仓库、issue、PR、提交、发布版本均为管理员录入与核验。后台没有可复用的只读代码托管查询适配，因此不增加远程同步。manual=人工填写；verified=管理员声明已实际查询核验，保存实际查询方式/对象/结果与时间；query_failed=查询失败。这个来源状态不代表后台自动验证。进度 candidate 起要求有效、已核验的 PR/commit；merged 需明确合并证据确认；released/verify_pending 另需已核验发布引用；verified 要求该修复+该发布的最新线上验证 passed。候选和发布 ID 保存到问题，验证记录独立保存。跨问题、已解除、纯链接/未核验/查询失败引用不能当作完成依据；解除错误修复引用重置进度。管理员仍须核对真实提交、合并状态、发布中是否包含该提交和实际影响范围。

## 诊断与恢复

诊断材料是独立白名单：description/reproduction/versions/errorSummary，管理员选择并确认 redactionConfirmed=true；默认不自动复制原反馈、邮箱、凭证、截图、备注或完整日志。截图用 `{feedbackId,index}` 明确选择，必须来自当前关联反馈；读取 T02 原私有截图，并保存独立输入快照。普通详情 API 只返回截图引用、不返回图片 base64，图片仍走原鉴权路径。管理员负责遮盖截图内隐私及文本脱敏；系统不会声称能自动识别所有敏感内容。文本来源标识固定，截图来源为 `feedbackId:index`。

复用 T03 的 ModelConfig、MockModel/OpenAIModel、ModelFailure、estimate 和官方固定端点；共享抽出的 timeout、lease/heartbeat/fencing 基元，原 T03 也使用同一基元并完成回归。独立 taskType=problem_diagnosis、diagnostic_runs、提示词 diagnosis-v1、配置 MAAS_DIAGNOSTIC_CONFIG 与付费开关 MAAS_DIAGNOSTIC_ALLOW_PAID；不建立 editorial_issues/revisions/正式专业内容，不混入周报素材。T05 查询实时安全投影诊断任务，validation=unknown/publication=not_run，不另建监控。

输出固定 facts（来源）、missingInformation、possibleCauses（证据/不确定性）、reproductionAndValidation、repairDirections（影响范围），存为 advisoryOnly 建议。schema 错误或虚构来源 needs_review，不存为可用建议；不能自动修改反馈、宣称根因、解决、执行命令或产生仓库/外部消息动作。供开发者复制的任务描述以管理员材料和逐条核验要求生成，页面安全 textContent 展示模型输出。

配置默认独立 mock，忽略周报配置。真实接入使用与 T03 同 schema 的独立私有配置文件，analyst 为诊断模型；OPENAI_API_KEY 仅服务端环境，MAAS_DIAGNOSTIC_ALLOW_PAID=true 才允许调用。此次均保持 false、mock；真实模型参数、图片质量、诊断质量、费用和账单未验收。OpenAI adapter 只发送选定材料及显式截图，不提供工具/任意端点/隐式重试。

每问题最多30次尝试；单任务最多3次429明确拒绝重试，按两倍延迟退避。付费配置必须有价格来源，上限输入/输出按 T03 estimate 预留3次，历史预留不释放，budget 是问题累计预算上限。超时、5xx、网络/用量未知、租约过期 needs_review，未核对不重发；同输入/config/prompt 去重包括成功、排队、执行及待核查任务。取消中的未知执行也阻止重发。管理员保存 executed/not_executed、供应商核查证据和已知费用（未知 null）后才允许新尝试。取消/过期 fence 阻止迟到建议写入，已知用量仍保留。模型价格计算是估算，不是账单对账。

输入按字节保守约束 tokens，截图 base64 也计入输入上限（默认40000，配置最多100000）；较大图片会被拒绝，需要先由管理员准备更小的脱敏截图，不会静默截断。HTTP 请求只发送引用和白名单文本，维持原16KiB admin请求限制。diagnostic worker 不发送邮件、不运行抓取/合并/部署。

```sh
npm run build --prefix services/agent-api
# 原私有账号库与secret配置已加载；隔离验收应使用临时库：
npm run diagnostic:worker --prefix services/agent-api -- --once
npm run diagnostic:worker --prefix services/agent-api
# 静态构建完成后重跑隔离浏览器：
python3.12 scripts/admin-browser-smoke.py --focus problems --output /private/tmp/maas-admin-browser-t07
```

worker 无需 PUBLIC_DATA_ROOT；SIGTERM 等待当前有界调用完成，不再领取。没有安装生产 worker/systemd/调度；真实配置由既有受控运维流程加载，不放命令参数或浏览器。

## 迁移、回滚与验收

API/worker 初始化自动执行幂等加法 migration7：problems、problem_links、problem_refs、problem_checks、diagnostic_runs 与索引。T01–T06 表保留，迁移失败整事务回滚；业务写入、版本、幂等和安全字段审计一次事务。原账号库一致性 SQLite backup 包含这些私有材料，不能单独复制 WAL 主文件。应用回滚前停诊断 worker、暂停问题管理写入；保留新表/费用/审计/截图快照，不 DROP。恢复后核查 needs_review，不能批量改 queued。生产迁移、备份恢复和大库性能尚未验证。

问题详情参考/验证各最近100条、任务最近25条；列表沿用签名分页。首版关联集合未做大规模性能承诺，不能用浏览器样例代表真实仓库修复、真实上线或模型质量。

最终本地交付完成。完整结果见 [acceptance/T07/summary.json](acceptance/T07/summary.json)。

| 检查 | 最终结果 |
| --- | --- |
| API build / 公共合同检查 | 通过 |
| API test:compiled | 174/174通过，包括12项T07与原T01–T06、账号/反馈/专业/公开REST回归 |
| T07/T02/T03/T05直接依赖专项 | 44/44通过：归并/解除与原记录、循环/存在/版本/审计回滚/幂等、材料白名单与内部隔离、独立任务/监控/重复去重、未知/错误schema/未知来源、显式私有截图、取消/租约/迟到用量、三次重试、价格与预算拒绝、错误/跨问题/解除修复引用、独立合并/发布/验证失败、T02逐条解决门槛、迁移原子回滚与多行材料 |
| page-models TypeScript | 通过 |
| 完整site build，最终Astro build | 通过，47462页，新增问题静态壳noindex，不含私有运行时数据 |
| T07浏览器 --focus problems | 8流程、0页面错误；临时SQLite/真实HTTP/独立mock worker，1440/390px；双反馈归并、材料隔离/去重、合并/发布独立、验证失败/复验、不批量关闭、错误引用及反馈解除、无持久私有存储 |
| 原后台浏览器回归 | 16流程、0错误；T01/T02/T03/T04/T05原闭环、双窗409、普通用户公开记录、Free/Plus隔离、真实注销/迟到响应清空均通过 |
| diff / shell / Python语法 | git diff --check、run-all-tests bash -n、浏览器脚本AST均通过 |

初次HTTP专项因沙箱不允许监听端口失败，未计作通过；在获准的本机隔离端口环境复验通过。开发中的TypeScript参数/类型错误已修正，最终build与门禁通过。T07不改公共MCP查询协议、生产激活器或原投递实现；本轮未重复执行不相关Python发布/抓取全套。

演示入口 `/admin/problems/`、带ID详情以及T02反馈详情的关联跳转。无常驻演示服务，重跑上述focus命令创建临时账号/管理员环境。截图/报告在 [acceptance/T07](acceptance/T07/summary.json)，最终本机日志 `/private/tmp/maas-t07-api-final.log`、`maas-t07-final-tests.log`、`maas-t07-site-delivery.log`、`maas-t07-browser-final.log`、`maas-t07-browser-regression.log`。临时库/outbox/API/代理/Chromium已由脚本清理；清理本次无用的编辑脚本与中间日志/重复截图，保留最终证据。

可信来源：反馈/用户/内容版本直接核对原私有表，信源异常和任务核对T05原记录，修复/仓库/发布来自管理员手工查询声明，模型建议来自独立诊断材料快照及固定prompt。浏览器所有提交、发布、线上环境标签为明确模拟夹具，不能证明真实修复或上线；真实代码托管、生产发布包含提交、线上影响范围、逐条反馈复验、截图脱敏与真实模型质量/费用仍需人工核验。
