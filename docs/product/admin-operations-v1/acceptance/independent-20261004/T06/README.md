# T06独立验收

状态：开发验收通过，外部或生产验证未完成。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` admin-delivery/mail-ledger/mail-query/mail-receipt/account-mail/pro-digest；测试实现位置：`services/agent-api/src/admin-delivery.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| two business kinds project legacy sent as accepted; private bodies and credentials excluded | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| timeout is unknown and never automatically retried; expired lease is unknown | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| confirmed rejection retries same job with audit, version and duplicate submission once | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| unsubscribe and entitlement revoke block retry without enabling subscriptions | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| verified duplicate and out of order receipts retain event time; bounce never enables resend | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| signature, timestamp, mismatched message and conflicting receipt rejection | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| late acceptance after unsubscribe is accepted, never reported cancelled; no second sender | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| professional sender checks current entitlement and preferences, unknown has no automatic reexecution | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| authenticated provider query saves observation time and omits returned body; 404 is unknown | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| health missing, stale and dependency failures are unknown/abnormal; backup never implies restore | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| filters, bounded pagination and signed cursor bind type/state/user/time | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| HTTP admin permission, Origin, no-store, audited idempotent retry and no remote ingest or shell | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| expired lease before adapter handoff cannot dispatch | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| confirmed professional retry preserves frozen body and supplier key | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| Svix official independent signature vector verifies exact algorithm | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| delivered evidence never loses to later accepted observation or local completion clock | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：超时/租约未知、重试幂等、偏好/权益复查、签名/乱序回执、备份与恢复分离、过期健康。

真实浏览器/HTTP结果：

- T06-unknown-disabled-and-safe-detail
- T06-confirmed-retry-audited
- T06-signed-duplicate-receipt-delivered
- T06-backup-separate-from-restore-and-stale
- T06-mobile-empty-filter

浏览器证据：../browser-delivery/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：真实供应商接受/送达/查询权限、Webhook网络入口与生产恢复未验证。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --focus delivery --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
