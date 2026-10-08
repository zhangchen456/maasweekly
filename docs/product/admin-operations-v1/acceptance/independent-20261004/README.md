# T01–T08独立验收报告

验收日期：2026-10-04（Asia/Shanghai）。独立执行，与开发交付声明分开。仅本机隔离环境，无生产操作、真实邮件、付费模型、真实扣款/退款。原T06/T07/T08开发证据完整保留。

| 任务 | 状态 | 结论边界 |
| --- | --- | --- |
| T01 | 开发验收通过，外部或生产验证未完成 | 首次生产授权、数据库迁移与真实nginx未验证 |
| T02 | 开发验收通过，外部或生产验证未完成 | 真实上线验证材料为人工录入，浏览器引用是合成夹具 |
| T03 | 验收不通过 | D01：T05异常未参与覆盖/出版判断；真实模型质量/费用未验证 |
| T04 | 开发验收通过，外部或生产验证未完成 | 真实Umami凭据/权限、生产数据规模及完整观察期未验证 |
| T05 | 开发验收通过，外部或生产验证未完成 | 跨任务D01另列；GitHub artifact实际传输和生产调度接入未验证 |
| T06 | 开发验收通过，外部或生产验证未完成 | 真实供应商接受/送达/查询权限、Webhook网络入口与生产恢复未验证 |
| T07 | 开发验收通过，外部或生产验证未完成 | 真实模型质量、截图人工脱敏和真实修复/上线证据未验证 |
| T08 | 验收阻塞 | 无渠道，真实适配/供应商沙箱未交付；候选收费规则待决 |

## 验收版本与基线

Git基线 `5c48d8e34cc2cab31a3f62e8bdf4b2bd5c58c972` **不能单独代表交付版本**：所有后台模块包含未提交/未跟踪修改。实际绑定工作区复制快照 `/private/tmp/maas-independent-20261004`，文件清单129684项，SHA256清单摘要 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`；见 [文件清单](snapshot-manifest.json)。排除Git忽略的私有账号库与开发acceptance证据；依赖本机复制，未切换或改动开发源码。快照内站点生成文件可被构建重建，原始交付文件以manifest为准。

已阅读全局 `/Users/zhangchen/.codex/AGENTS.md`、site/AGENTS.md、ops/README.md、后台README/development-order、T01–T03方案、T01–T08 implementation、admin-api-v1与paid-subscription-v1合同。T04–T08无独立方案，使用用户提供范围与实际合同。README“规划未实施”和早期交付文档“未开发下一任务”是历史阶段叙述；以快照源码、最终development-order和实际测试判状态。T08模拟候选已交付，不把无渠道适配当代码失败。

依赖：T01共享权限/审计/command；T02共享权益/反馈；T03共享内容/worker；T04依赖业务事件；T05投影T03/T07任务；T06依赖邮件与T05健康；T07依赖T02/T05/T06；T08模拟依赖T02/T06，真实渠道单独挂起。

## 独立实际执行

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| API build及公共合同生成检查 | 通过 | api-build.log |
| API现有全量compiled回归 | 195/195通过，含真实本机HTTP、临时SQLite、并发/回滚/迁移 | api-tests-localhost.log |
| MCP compiled/历史公开数据回归 | 21/21通过 | mcp.log |
| page-models类型检查 | exit 0 | page-models.log |
| 完整site build | 47465页，通过公开归档与价格门禁 | site-build.log |
| Chromium主流程T01–T05 | 16流程，0错误 | browser-main/browser.json |
| Chromium T06 | 8流程，0错误 | browser-delivery/browser.json |
| Chromium T07 | 8流程，0错误 | browser-problems/browser.json |
| Chromium T08模拟 | 9流程，0错误 | browser-payments/browser.json |
| T05采集Python | 9/9通过 | monitor-python.log |
| WAL备份与隔离恢复Python | 6/6通过 | maintenance-python.log |
| 候选激活器Python | 49运行，47通过，2跳过 | activation-python.log |
| 后台HTML/共享JS合成秘密扫描 | 55文件，0标记命中 | static-scan.json |
| 自编跨任务信源→出版复现 | 复现D01：degraded/missing仍normal且published | source-publication.mjs / source-publication.json |

首次沙箱API测试因 `listen EPERM`失败，保存api-tests.log，但不作业务失败；在允许本机临时端口后一次完整复验通过。激活器两项跳过与环境有关（macOS flock/测试条件），日志还有subprocess ResourceWarning；未将这些跳过项算通过。没有根据测试名称或开发summary宣称通过：重跑现有脚本、阅读关键断言，并自编联合复现。复用开发测试/浏览器脚本意味着它们仍可能存在共同盲点，不代表所有真实环境风险已穷尽。

截图抽查：统一周报Plus正文、健康来源与备份/恢复分离、诊断建议、支付对账；浏览器真实操作桌面1440及窄屏390。静态扫描仅证明给定合成秘密标记未进入产物，结合运行时鉴权和无私有库构建输入代码检查；不声称是任意秘密的完整DLP证明。

## 阻塞上线的问题

[D01：信源异常未参与出版判断](defects.md)。T03工作流的单模块测试通过，但联合要求不通过，不放行该链路。T08真实渠道/适配/沙箱及规则未决为已知阻塞，按用户要求挂起，不等待渠道或补实现。

## 可后续修复的问题

未新增独立证实的非阻塞代码缺陷。JSON编辑器、纯文本正文、人工修复引用等是已注明首版限制，不擅自当缺陷。API发布版本本机unknown符合合同，不按前端版本猜测。

## 待验证事项

所有生产迁移/一致性备份恢复、真实nginx/systemd/权限、外部统计/邮件、真实模型质量与成本、真实代码托管/发布验证、支付沙箱均未执行。T03真实历史演练只核对冻结ID/URL/观察时间，使用确定性mock，不是商业内容质量通过；公开历史数据未联网重新核验原官方事实。

联合结果见 [integration.md](integration.md)，逐项步骤见T01–T08目录。没有修改业务、部署、发开发聊天消息或设置监控。完成本轮后结束，由协调决定后续调度。

## 恢复方法

保留独立快照供定向复验；不要在开发目录运行测试或覆盖原证据。新交付只固定新快照、比较受影响源码与合同，重验D01及相关链路；无改动不重复195项。额度阈值按用户规则：5小时>=98%、额度未知、ordinaryUsageAllowed=false或周额度耗尽时保存进度停止，不用reset credit。结束前检查5小时48%、周96%，普通使用允许。

命令从快照运行：`npm run build --prefix services/agent-api`；`npm run test:compiled --prefix services/agent-api`；`node --test --test-force-exit services/agent-api/dist/tests/mcp.test.js services/agent-api/dist/tests/mcp-real.test.js`；站点目录`npm run build`；`python3 scripts/admin-browser-smoke.py --output NEW_EVIDENCE`（focus delivery/problems/payments分别隔离）；Python3.12三项unittest discover见日志。自编复现复制source-publication.mjs到快照根后`node source-publication.mjs`。任何外部付费/生产验证仍需单独授权。
