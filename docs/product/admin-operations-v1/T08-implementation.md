# T08 付费订阅与对账：实现、阻塞与恢复

2026-10-04。**模拟闭环及不依赖渠道的后台能力已本地交付；T08整体尚未完成。** 真实渠道和产品规则未确认，真实供应商适配与沙箱验收未完成，不能正式收费或宣称完整支付验收通过。保留所有原 T01–T07 工作区改动，未提交Git、部署、开通商户、切live、真实收费/退款、发送真实消息或启动后续任务。

## 依据、合同与实现

已读全局AGENTS.md、site/AGENTS.md、ops/README、后台README/development-order、T01–T07实际交付、T02/T04/T06实际实现和原订阅/公测/手工授权/专业HTTP/MCP/邮件规则。根目录无AGENTS.md。仓库只有计划价US$9.90/月，无支付渠道。已明确询问必需待决项，尚无确认。

[状态与权益合同](../../contracts/paid-subscription-v1.md)：有效paid > beta > manual，保留T02既有免费来源顺序。paid在原ProStore.entitlement统一判定，网站/REST/MCP/RSS/邮件复用。手工revoked继续阻止beta但不撤销paid；退款、争议、立即终止只影响paid，所以独立免费授权仍可能保留Plus。公测不自动转付费、不扣款、不计收入、不开启专业邮件。

首次付款/续费成功须服务端核查对象、订单用户、供应商、金额、币种与周期一致。续费失败不延长服务；周期取消保留已付期，立即终止不隐式退款。累计全额退款撤销该订单周期，部分退款保留。争议暂停对应订阅，胜诉恢复剩余付费期，败诉撤销对应周期。周期到期实时失效；没有宽限。UTC模拟月周期将31日等落到下月最后有效日；真实供应商周期合同仍需核对。

新增payment-store/simulator/http/reconciliation/cli/worker、admin-payments及两份payment测试。扩展ProStore、Pro HTTP、server、Admin HTTP/Users和API scripts。后台 `/admin/payments/`、用户 `/subscription/payments/` 与 `/subscription/sandbox/` 为静态私有壳，新增payment-view/admin-payments-client/billing，沿用原管理员鉴权/分页/command幂等/原子审计、Astro与登录组件。用户页有当前来源、订阅状态、周期结束/下次续费、取消与支付记录；后台有订单/订阅/退款/回调/对账/差异查询、详情、退款请求与处理备注。金额从整数格式化，用户USD显示US$9.90，管理员显示最小单位；不引入浮点记账。

只有 `MAAS_PAYMENT_MODE=simulator` 且网站origin为localhost/127.0.0.1才允许模拟结账/结果/取消/回调；默认关闭。模拟页面明确不收卡、不扣款，不代表供应商托管结账已接入。订单未付款保持processing，失败和成功由服务端事实决定；浏览器return/success参数不授予权益。未完成订单重复购买复用原订单；已有有效/待生效/争议付费订阅不再创建第二份。

`/api/payment/webhook` 是自定义本机模拟schema，**不是Stripe接口**。原始字节HMAC签名、300s时间窗、原始字节hash/供应商事件ID去重与冲突拒绝。接收和处理结果分别追加，202仅说明持久接收。失败/重复/乱序/漏回调可查询恢复。用户财务接口要求网站session，专业Bearer不得读取账务。

退款请求先检查成功付款和可退余额、预留pending/unknown金额，退款/审计/幂等结果同一事务。退款成功事实与请求succeeded也同一事务；故障不释放余额，恢复复用被冻结模拟供应商结果，不生成第二笔退款。已知成功结果不能被错误标failed释放余额。提交不等于完成；退款和取消/撤销权益独立，没有真实退款执行器，也不允许编辑订单金额或补凭证。

## 持久处理与对账

migration8添加订单、订阅、尝试、事件/结果、不可变支付事实、退款请求/结果、对账快照/供应商记录/差异/处理记录及模拟供应商对象；trigger禁止修改/删除这些历史记录。

**本次恢复新增migration9**：paid_event_jobs及索引，为可重建处理投影。原8库可加法升级，不改原金融事实，9失败全事务回滚；后续迁移应从10开始。PaymentEventWorker仅调用read-only lookup，不提交付款、取消或退款。默认查询超时10s（最多30s）；租约过期提高fence，迟到结果不能提交；业务事实/处理结果/job完成一次事务。未知查询间隔60s，最多10次后needs_review；明确人工核查后经version/幂等/审计重新查询。SIGTERM停止领取并等有界请求结束，没有安装worker/systemd/定时任务。

对账按currency/[from,to)保存来源快照，比较内部成功支付/退款与供应商对象，追加missing_internal/missing_provider/amount_mismatch及处理记录。后台分别显示窗口内创建订单数/总额（不是收入）、成功付款数/收入、成功退款、供应商记录、手续费、实际结算。没有快照时供应商费用/结算unknown；选定快照才显示其实际记录，已记录0和未知分开。不同币种拒绝混合，安全整数聚合超限失败，不默默舍入。对账文件与截图均为模拟材料，不能证明真实账单/到账。

## 迁移、运行与回滚

未来迁移前用SQLite backup备份原账号库，不能只复制WAL主文件。服务启动/AdminPayments自动8/9加法迁移，worker也幂等执行9。本轮仅临时内存/文件库，无生产升级。保持原私有MAAS_ACCOUNT_DB/MAAS_ACCOUNT_SECRET环境，secret不放命令参数。ops/maas-payment.env.example默认disabled。

```sh
npm run build --prefix services/agent-api
# 仅隔离本机库，私有环境已加载 MAAS_PAYMENT_MODE=simulator
npm run payment --prefix services/agent-api -- publish /absolute/path/fact.json
npm run payment --prefix services/agent-api -- deliver SIMULATOR_FACT_ID
npm run payment --prefix services/agent-api -- recover
npm run payment:worker --prefix services/agent-api -- --once
npm run payment:worker --prefix services/agent-api
npm run payment --prefix services/agent-api -- retry-lookup EVENT_ID OPERATOR '已核对，重新只读查询' EXPECTED_VERSION UNIQUE_KEY
npm run payment --prefix services/agent-api -- refund-result REFUND_ID succeeded
npm run payment --prefix services/agent-api -- reconcile /absolute/path/snapshot.json
```

fact字段及严格schema见paymentFactSchema；接收事件引用fact.id，fact.objectId是供应商交易对象。publish冻结模拟结果，deliver/worker从模拟供应商lookup核验。recover每次最多100条，按最后查询时间公平轮转，不无限处理未知事件；worker未知结果不会触发任何供应商写入。版本/state可在后台回调列表的job投影读取；retry-lookup只重查，不重收款/退款。

snapshot为currency/from/to/source/records，每record为kind(paid/refund/fee/settlement)/objectId/amount/currency/occurredAt，最多10000条；账务窗口以供应商occurredAt为准，订单窗口独立按创建时间。首版只支持非负账项；真实负结算/汇率/税费/调整/净额合同需随供应商方案明确。

回滚先停worker并关闭新结账/退款/管理写入，按原发布流程保留新表、金融事实及审计，不DROP。旧应用不认识paid，回滚可能停止paid访问；不能用旧CLI手工授权伪装付款。重新升级先核查pending/unknown/needs_review和真实供应商结果，再恢复写入。本轮未新增生产nginx回调路由、配置或调度。

## 本地验收

| 检查 | 最终结果 |
| --- | --- |
| API build/公共合同检查 | 通过 |
| API test:compiled | 195/195，包含最终21项支付专项及原T01–T07/账号/专业回归 |
| 支付专项 | 21/21，包括首次/续费/失败/到期/取消/终止/争议/退款/重复/乱序/遗漏补查、金额/币种核验、不可变记录、迁移、退款审计原子回滚、两个独立进程余额竞争、readonly worker超时/10次上限/过期租约/迟到fence/人工重查审计 |
| paid跨服务面 | 同一真实ProStore/HTTP/MCP/RSS及模拟邮件sender：paid生效可读，全额退款后均拒绝且pending邮件取消，独立manual/beta恢复访问，撤销manual不取消仍由paid覆盖的pending邮件；无真实邮件 |
| 管理HTTP | Free/未登录/错误Origin拒绝退款；幂等和冲突、详情/币种/查询校验、no-store通过 |
| page-models TypeScript / diff / shell / Python AST | 通过 |
| Astro build | 47465页；最终显示微调构建亦通过 |
| T08隔离浏览器 | 9流程、0错误；真实临时SQLite/HTTP/登录/CLI，processing return不授予、failed→paid、取消、pending→部分→全额退款、快照费用/结算未知与已记录0、差异备注、1440/390、注销清空 |
| 原后台浏览器回归 | 16流程、0错误，T01/T02/T03/T04/T05原流程、Plus/Free无后台权限、版本冲突及迟到清空保持 |

初次浏览器漏了列表退款状态列导致等待失败，已补展示并复验；初次全量API的子进程并发夹具从npm子目录错误取cwd，已用模块URL定位服务根复验195/195。Bundled Python缺Playwright，最终用现有python3.12/Playwright，无安装新包。这些失败没有计为通过。

最终证据见 [acceptance/T08](acceptance/T08/summary.json)。本机日志 `/private/tmp/maas-t08-api-final-delivery.log`、payment-delivery.log、site-final-delivery.log、browser-final-delivery.log、browser-regression.log。私有临时SQLite/outbox/HTTP/代理/Chromium由finally清理；无常驻演示。重跑 `python3.12 scripts/admin-browser-smoke.py --focus payments --output /private/tmp/maas-t08-browser` 创建隔离演示，统一run-all-tests非quick已接入该门禁。

## 剩余阻塞与正式收费前事项

必须确认：一个供应商/商户地区、结算币种、正式价格/周期/税费及退款/争议生效规则；沙箱产品/price ID、test key、webhook签名secret和可达回调/return地址只能由既有私有配置提供。计划价不能代替确认。没有自行选择/开通商户。

真实供应商adapter仍未实现：托管checkout、真实对象/最新订阅核验、续费/取消/终止/争议事件映射、退款提交与最终查询、稳定供应商幂等key、分页账单/手续费/结算读取。通用readonly事件worker已实现；供应商金融写入任务、未知执行确认、商户API限流/官方签名向量和真实负结算/税费规则仍须随渠道实现。不能把simulator-result或CLI模拟最终结果直接用于真实收费。

真实沙箱matrix全部未执行：首次、续费、失败/异步处理、取消/立即终止、全额/部分退款、争议胜败、重复/乱序/漏回调、网络未知、账单/手续费/结算及各服务面。正式收费还需真实产品合同批准、用户明确选择、生产回调/密钥权限/限流、迁移备份恢复、沙箱证据和后续上线授权；本轮没有真实通知、上线或开收费。

后续首先读取额度并保留既有改动；5h usedPercent>=98、额度未知、ordinaryUsageAllowed=false或周额度耗尽时保存停止，等待协调聊天。原98%检查点已在授权恢复后继续，未使用reset credit。当前开发允许普通使用；结束前最新额度：5小时usedPercent=34、周usedPercent=93、ordinaryUsageAllowed=true；未触发暂停阈值。本任务仍为部分交付，只剩上述真实配置/供应商工作及其验收，不能标T08完成。

参考：[Stripe webhook](https://docs.stripe.com/webhooks)、[订阅生命周期](https://docs.stripe.com/billing/subscriptions/overview)、[Astro routing](https://docs.astro.build/en/guides/routing/)。用于候选设计与页面约定，不代表选定Stripe或验证真实集成。

最终视觉核对修正了用户窄屏付款表：表格在容器内横向滚动，金额/状态不再被挤成逐字换行；浏览器门禁检查滚动容器及整页无横向溢出。后台详情同样使用滚动容器，写入后刷新列表/详情，处理记录数随读取更新。
