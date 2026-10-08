# T03独立验收

状态：验收不通过。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` editorial-store/service/checks/model/worker、pro-publication；测试实现位置：`services/agent-api/src/editorial.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| real calendar Monday boundaries, migration additive and snapshots immutable | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| manual revision/review hash binding, atomic package publication and duplicate replay | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| forged references/XSS/price mismatch flagged, current withdrawal blocks publication | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| persistent staged mock worker, dedup, lease fencing and cancellation reject late result | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| uncertain calls require review, retries bounded, insufficient budget calls no adapter | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| authenticated HTTP body limits, no draft disclosure, Plus consumer serialization | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| zero evidence preserves coverage-only issue; no artificial pro content | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| editing during model call rejects overwrite but keeps incurred fees; cancellation and recovery reconciliation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| two connections claim one durable task; restart retains frozen draft and fencing | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| active real-provider cancellation remains blocked until provider reconciliation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| migration failure rolls back all new tables and preserves old account data | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| publication stays available on composition failure; corrections change current reader version without rewriting reports | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：历史创建/冻结/四阶段worker/编辑审核/出版/组合/Plus读取，故障回滚、审核失效、费用未知、伪造引用及XSS拒绝。

真实浏览器/HTTP结果：

- T03-real-history-create-freeze-stage-worker-edit-review-publish-compose-plus-preview

浏览器证据：../browser-main/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：D01：T05异常未参与覆盖/出版判断；真实模型质量/费用未验证。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
