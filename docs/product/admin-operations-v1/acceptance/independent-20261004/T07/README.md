# T07独立验收

状态：开发验收通过，外部或生产验证未完成。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` admin-problems/diagnostic-worker/model-task-runtime；测试实现位置：`services/agent-api/src/admin-problems.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| T07 additive migration, merge and unlink preserve original feedback and per-user history | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 cycle prevention, existence and stale writes, audit rollback, exact idempotency | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 independent diagnosis uses selected whitelist, fixed sources, dedupes tasks; does not alter feedback or editorial production | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 model uncertainty and malformed suggestions require review, explicit provider recovery before replay | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 cancelled / expired tasks fenced; late usage preserved without storing stale advice | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 repair links distinguish sources, reject wrong fix, release verification can fail and never resolves feedback | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 HTTP roles, CSRF, no-store, version gate, create replay and unknown-field isolation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 explicit private screenshot selection is independent, scoped and redaction-confirmed | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 shared failure handling bounds rate-limit retries and input size without invoking model | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 failed migration rolls back only new tables and retains T02 records | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 independent paid config requires quoted budget; unknown evidence sources are never saved as usable advice | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T07 multiline reproduction/evidence stays private and can be cleared without changing public feedback | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：双反馈关联/解除/循环、显式材料/截图、mock建议来源、阶段区分、逐条解决、租约/费用。

真实浏览器/HTTP结果：

- anonymous-login-entry
- existing-login-cli-grant-real-overview
- audit-real-record-and-empty-filter
- problem-merge-two-feedback-original-history-preserved
- selected-material-deterministic-advice-dedup-no-feedback-state-change
- merge-release-separate-post-release-failure-reinvestigation-per-feedback-gate
- unlink-wrong-repair-reset-progress-unlink-feedback
- mobile-no-overflow-no-private-storage

浏览器证据：../browser-problems/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：真实模型质量、截图人工脱敏和真实修复/上线证据未验证。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --focus problems --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
