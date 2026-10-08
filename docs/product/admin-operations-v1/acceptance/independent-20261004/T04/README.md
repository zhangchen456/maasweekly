# T04独立验收

状态：开发验收通过，外部或生产验证未完成。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` admin-analytics/admin-umami、pro-http/pro-mcp；测试实现位置：`services/agent-api/src/admin-analytics.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| Beijing date boundaries, leap day, inclusive custom end, presets and strict parameters | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| future real registration is atomic and deduplicated; legacy profile never backfills registration | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| fixed event boundaries, unique readers, cross-day return and zero/mature/immature activation denominator | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| week4 retention excludes legacy, respects 21/28-day edges and only fully observed cohorts | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| Umami bounded server-only query, exact boundary adapter, cache/single-flight and missing/failure freshness | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| HTTP analytics permission, unknown parameters, no cache, revoked and session-cleared access | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| request collection counts one finish per HTTP request, separates channels and records HTTP status without identities | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| migration failure is atomic and repeatable | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| published weekly with no reads is zero, samples excluded, multiple revisions do not duplicate issues | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| v2 uses url and visitors, no implicit zero or unsafe redirects; calls remain bounded | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| admin revocation during external await rejects the finished aggregation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：固定时钟、北京边界、成熟分母、未知注册、去重、零/不足样本、Umami失败、凭据隔离。

真实浏览器/HTTP结果：

- T04-7day-28day-custom-real-SQL-deduplicated-cross-day-readers
- T04-Umami-failure-null-values-last-success-local-metrics-still-visible
- T04-desktop-mobile-no-overflow-and-Umami-recovery
- T04-logout-late-response-clears-private-metrics

浏览器证据：../browser-main/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：真实Umami凭据/权限、生产数据规模及完整观察期未验证。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
