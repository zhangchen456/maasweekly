# D01独立定向复验与当前总状态

2026-10-04，Asia/Shanghai。本轮独立实测通过，D01在注明本机环境关闭。T03由“验收不通过”更新为“开发验收通过，外部或生产验证未完成”；没有生产或真实模型质量通过结论。

| 任务 | 当前状态 | 本轮范围 |
| --- | --- | --- |
| T01 | 开发验收通过，外部或生产验证未完成 | 沿用原独立验收证据，无疑点不重复 |
| T02 | 开发验收通过，外部或生产验证未完成 | 沿用原独立验收证据，无疑点不重复 |
| T03 | 开发验收通过，外部或生产验证未完成 | D01及T03/T05直接回归 |
| T04 | 开发验收通过，外部或生产验证未完成 | 沿用原独立验收证据，无疑点不重复 |
| T05 | 开发验收通过，外部或生产验证未完成 | D01及T03/T05直接回归 |
| T06 | 开发验收通过，外部或生产验证未完成 | 沿用原独立验收证据，无疑点不重复 |
| T07 | 开发验收通过，外部或生产验证未完成 | 沿用原独立验收证据，无疑点不重复 |
| T08 | 验收阻塞 | 真实渠道/适配/供应商沙箱继续挂起 |

## 版本与隔离

独立快照 `/private/tmp/maas-d01-independent-20261004`；snapshot.json SHA256 `bb2d593eb2566758b1de3e4a7bee521c6892f7c38c24c6eed151c82d2dc11aeb`。开发交付files.json全部14文件hash独立核对一致，清单摘要 `10d9ffbbddbfb6c19afbaff23405b9a534c47c4e737a0498f5223e59b8235ae6`。实际快照绑定sourceFiles与deliveryHashes，不将未提交Git基线当修复版本。复用原独立快照公开data和依赖只读路径，源码/站点生成文件/服务dist为新隔离目录；未切换或覆盖开发工作区。原independent-20261004与d01-fix-20261004证据完整保留。

## 独立实际证据

| 验证 | 预期 | 实际 |
| --- | --- | --- |
| API构建/公共合同检查 | 可构建 | build.log，exit0 |
| T03/T05/coverage定向回归 | 相关正常流程和风险断言通过 | tests.log，25/25，0失败/跳过；真实本机HTTP、临时SQLite |
| 同源同窗口监控失败与公开投影不一致 | normal拒绝 | 原D01夹具自编重放，409 monitor_coverage_conflict；independent-repro.json |
| partial无确认/过期确认 | 拒绝 | HTTP专项及自编错误hash拒绝；Chromium真实按钮拒绝 |
| 明确确认限制后的partial | 能正常出版 | 自编断言与Chromium四mock worker→编辑→六项审核→出版→Plus全文/游客预览通过 |
| 审核后监控依据或同窗口公开投影变化 | 旧审核不能出版 | HTTP专项409 coverage_basis_changed，未新增正式内容 |
| 提交审核后新失败 | 不能批准 | HTTP专项409，重新冻结后新稿审核可出版 |
| 旧期次缺monitor依据 | 重新冻结/审核 | 自编删除合成coverageInfo中的依据，publish409；恢复合法依据后通过 |
| 无关来源/窗口外/明确其他ds版本/not_run | 不无条件阻断历史期次 | HTTP专项basisHash不变 |
| 最新相关unchanged/full | 可证明窗口恢复 | HTTP专项limited=false，normal可冻结 |
| 重复出版 | 不增加publication | 自编不同幂等键重复出版，publicationId相同、总记录1；editorial回归同时覆盖同键重放与审计原子性 |
| 浏览器真实联通/权限/窄屏 | 能走通且无错误 | browser/browser.json，5流程，0错误；合成管理员、真实HTTP/CLI/SQLite、1440/390px |
| 修复页面构建 | 能构建 | site.log，47465页；此次Astro直接build，不重跑原无变化归档/价格全套门禁 |

自编脚本independent-d01.mjs由原D01复现改成断言，独立增加过期确认、旧期次缺依据和重复出版检查；结果不是引用开发summary。首次从项目根误跑该脚本导致路径找不到，随后从快照根运行exit0，最终证据为正确目录运行结果，未修改业务来绕过失败。

代码检查：editorial-coverage按sourceId/attemptAt统计窗口关联，显式ds版本不匹配排除，非公开版本命名空间保持unknown；observedAt与payloadHash进入冻结basis。审核与出版重新requireCoverageBasis；公开同窗口状态进入hash。T05原事实仍只读，忽略异常不改变事实；未新增迁移，复用coverageInfo/inputHash。图片抽查coverage-conflict.png实际展示限定来源、监控缺失/冲突、确认框和拒绝提示。代码检查结论与实际运行结果分别列出，不声称已读取真实生产监控。

## 联合结论与遗留

“信源失败→任务异常→周报覆盖限制/出版判断”在本机隔离环境通过；D01关闭。T01/T02/T04/T06/T07及其他联合链路沿用原报告的实际本地证据，未重跑无修改全套195项。

没有新增独立确认的阻塞代码缺陷或非阻塞代码缺陷。T08真实渠道/适配/沙箱及收费合同继续验收阻塞；不等待、不实现。未导入的真实监控事实、未知命名空间的精确版本归属、大规模生产性能、生产迁移/恢复/nginx、外部邮件/统计、真实模型质量与成本仍未验证；旧期次必须重新冻结与审核。已出版正文不会被本次代码自动撤回，运营仍负责核查实际覆盖限制。

## 命令与恢复

在快照根运行 `npm run build --prefix services/agent-api`，`node --test --test-force-exit services/agent-api/dist/tests/editorial-coverage.test.js services/agent-api/dist/tests/editorial.test.js services/agent-api/dist/tests/admin-monitor.test.js`，`node independent-d01.mjs`，`python3 scripts/admin-browser-smoke.py --focus coverage --output NEW_EVIDENCE`；site目录`npm exec -- astro build`。所有HTTP/浏览器请求仅本机，付费模型关闭、outbox本地，未部署或操作支付。

恢复复验时以snapshot.json/hash绑定源码，不覆盖原证据。新改动只复验影响范围。保留有用快照及复现脚本，不留常驻服务或私有临时库；浏览器脚本已清理进程/SQLite/outbox。额度检查5小时65%、周98%、ordinaryUsageAllowed=true，未触发原阈值，未使用reset credit。d01 heartbeat已为PAUSED（读取配置确认），本轮报告交付后结束。
