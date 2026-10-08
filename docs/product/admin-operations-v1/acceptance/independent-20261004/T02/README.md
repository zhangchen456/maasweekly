# T02独立验收

状态：开发验收通过，外部或生产验证未完成。版本：快照SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，基线Git如总报告。环境：Node22.22.3、本机Chromium、临时SQLite、outbox、mock模型/支付。

业务实现：`services/agent-api/src/` admin-users/admin-feedback/admin-operations/pro-store/feedback-cli；测试实现位置：`services/agent-api/src/admin-operations.test.ts`及对应admin模块；页面`site/src/pages/admin/`与`site/src/lib/admin-*-client.ts`；实际新增合同/运行迁移回滚说明为T01–T08 implementation及统一admin-api-v1。T08另见paid-subscription-v1。依赖与交付状态见总表，均未提交生产版本。

| 验收项 | 预期 | 实际与证据 |
| --- | --- | --- |
| effective entitlement matrix uses original evaluator and filters before pagination | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| no-manual revoke creates marker, cancels pending mail; admin transaction rolls back all side effects | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| feedback gates code release + online verification, keeps notes private, reopens with audit, rejects cycles | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| migration retains legacy resolved without fictional verification, retries failure and preserves old data | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| two connections and CLI actor share versions rather than silently overwrite | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| HTTP private screenshot, ownership, version/idempotency, strict body and credential revocation | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| real compatibility CLIs require versions, share audit, gate resolution and keep private export | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |
| thousands of feedback rows page completely; latest failed verification blocks resolve at same millisecond | 断言满足合同、故障不能产生错误副作用 | 本轮独立执行通过；../api-tests-localhost.log，对应源码测试断言 |

业务范围：用户查询/授权撤销、凭证/会话、私有图片、内部/公开隔离、解决门槛、双窗409、CLI兼容。

真实浏览器/HTTP结果：

- T02-two-browser-windows-version-conflict
- T02-user-search-grant-private-image-note-public-reply-verification-resolve
- T02-ordinary-owner-sees-public-result-without-internal-note

浏览器证据：../browser-main/browser.json与同目录PNG；全部流程exit0，pageerror为空。T01/T02/T03/T04/T05共享主流程，T06/T07/T08各独立进程。

限制及待验：真实上线验证材料为人工录入，浏览器引用是合成夹具。

代码检查证据：管理员路由每次认证与Origin/no-store统一处理，管理write复用AdminStore.command、迁移注册；模型/邮件/支付网络入口默认受控关闭或仅模拟。运行、配置和回滚说明已审阅，未实际演练生产回滚。真实供应商语义、任意历史规模性能不能由本地测试证明。

命令：在快照`npm run test:compiled --prefix services/agent-api`；`python3 scripts/admin-browser-smoke.py --output NEW_EVIDENCE`。无需重复已通过无疑点的测试；本项更改后只重验影响范围。
