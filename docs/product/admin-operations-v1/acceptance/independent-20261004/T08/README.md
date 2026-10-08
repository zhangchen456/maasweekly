# T08独立验收

状态：验收阻塞。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` payment-store/simulator/http/worker/reconciliation、admin-payments；测试实现位置：`services/agent-api/src/payment.test.ts + payment-integration.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| T08 paid independent source, successful payment required, expiration and beta fallback | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 duplicate events/facts, conflict, amount verification and failed event recovery persist | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 refund submission reserves balance, completed partial retains and cumulative full removes paid | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 renewal failure/cancellation are distinct from termination and dispute | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 signed raw bytes verify freshness and reject mutation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 additive migration rollback preserves accounts and is repeatable | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 simulator authoritative lookup supports missing callback recovery and out of order renewal | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 final simulator refund separate from requested state; immutable histories | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 reconciliation isolates currencies and unknown settlement, records discrepancies and append-only handling | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 administrative refund business and audit rollback atomically | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 local simulator HTTP authenticates ownership, ignores browser return, verifies callback and cancellation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 month-end anchors, cancellation prevents future renewal orders, aggregate integers checked | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 paid access consistent across website/REST/MCP/RSS and mail eligibility; independent sources survive refunds | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 administrator HTTP permissions, Origin, request idempotency and safe detail projections | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 failed final refund commit retains reservation and retries the same authoritative result atomically | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 two independent processes cannot reserve more than the refundable balance | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 subscription and order states are derived from facts, not browser guesses | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 read-only event worker recovers persisted events, bounds attempts, and audits explicit re-query | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 expired lookup lease rejects a late result while another processor completes the same event | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 lookup timeout remains unknown without money changes, no supplier mutation or unbounded retry | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T08 migration9 upgrades an existing payment database and rolls back conflicts without changing financial facts | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：模拟服务端核验、重放/乱序/恢复/并发退款、金额/对账/权益、默认disabled。

真实浏览器/HTTP结果：

- T08-processing-return-does-not-grant
- T08-failed-then-verified-paid
- T08-cancel-keeps-current-paid-period
- T08-pending-partial-full-refund-separate-from-entitlement
- T08-currency-reconciliation-source-unknown-vs-known-and-append-action
- T08-mobile-and-logout-private-dom-cleared

浏览器证据：../browser-payments/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：无渠道，真实适配/供应商沙箱未交付；候选收费规则待决。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --focus payments --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
