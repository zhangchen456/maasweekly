# T01独立验收

状态：开发验收通过，外部或生产验证未完成。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` admin-auth/admin-http/admin-store/admin-cli；测试实现位置：`services/agent-api/src/admin.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| additive repeatable migration preserves account, sessions, feedback and pro tables | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| commands deduplicate, bind actor type, enforce versions and rollback business/audit/results | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| actual HTTP authorization, revocation, errors, bounded body and stable signed pagination | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| two SQLite connections serialize versions, idempotency and immediate revocation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| migration failure rolls back all foundation tables and can retry | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| secure cookie mode rejects insecure and bearer credentials | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：权限、撤权、幂等/版本、原子回滚、旧库迁移、静态隔离。

真实浏览器/HTTP结果：

- anonymous-login-entry
- existing-login-cli-grant-real-overview
- audit-real-record-and-empty-filter
- T03-real-history-create-freeze-stage-worker-edit-review-publish-compose-plus-preview
- T04-7day-28day-custom-real-SQL-deduplicated-cross-day-readers
- T04-Umami-failure-null-values-last-success-local-metrics-still-visible
- T04-desktop-mobile-no-overflow-and-Umami-recovery
- T04-logout-late-response-clears-private-metrics
- T05-real-ingest-duplicate-success-failure-unchanged-stale-unknown-ignore-not-heal-verified-resolution-audit-desktop-mobile
- T05-private-DOM-cleared-no-execution-endpoint-no-persistent-storage
- T05-real-logout-late-task-response-does-not-repopulate-private-DOM
- T02-two-browser-windows-version-conflict
- T02-user-search-grant-private-image-note-public-reply-verification-resolve
- T02-ordinary-owner-sees-public-result-without-internal-note
- revocation-and-logout-clear-private-dom
- free-plus-no-admin-permission

浏览器证据：../browser-main/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：首次生产授权、数据库迁移与真实nginx未验证。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
