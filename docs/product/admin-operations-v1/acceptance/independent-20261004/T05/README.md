# T05独立验收

状态：开发验收通过，外部或生产验证未完成。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` admin-monitor/monitor-cli、monitor-collect.py/monitor-record.py；测试实现位置：`services/agent-api/src/admin-monitor.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| additive migration is repeatable and rollback leaves no partial schema | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| success and unchanged are executions; validation and publication remain independent | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| partial and full failure preserve prior success, distinguish fetch and parse, no not-run success | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| unknown history and stale evidence never invent success | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| duplicate receipt and duplicate run are idempotent; conflicting replay rolls back whole batch | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| strict bounded protocol rejects arbitrary logs, commands, URLs, errors and unknown sources | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| queue ignores do not heal sources; resolution requires later successful same source and full coverage | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| validation anomaly cannot resolve using merely successful execution | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| runs pagination binds filters and omits private diagnostic payloads | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| HTTP permission, CSRF, write audit, version and no execution endpoints | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| two connections and restart preserve receipts and source history | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| T03 live state and safe versions project without config, payload or provider error text | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：状态分离、重复/冲突导入、忽略不治愈、同源恢复核验、受控动作、真实档案接入。

真实浏览器/HTTP结果：

- T05-real-ingest-duplicate-success-failure-unchanged-stale-unknown-ignore-not-heal-verified-resolution-audit-desktop-mobile
- T05-private-DOM-cleared-no-execution-endpoint-no-persistent-storage
- T05-real-logout-late-task-response-does-not-repopulate-private-DOM

浏览器证据：../browser-main/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：跨任务D01另列；GitHub artifact实际传输和生产调度接入未验证。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
