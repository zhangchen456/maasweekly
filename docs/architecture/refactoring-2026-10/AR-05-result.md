# AR-05 验收结果

状态：DONE_LOCAL / WORKFLOW_ROLLOUT_PENDING。2026-10-02（Asia/Shanghai）。实施候选 `cb03a05b826692546e7e5f1835565bca28ff7c01`，未推送/部署。

## 实现

每日/每周只在写入 job 持有共享 `maas-data-write-main` 锁，获得执行权后检出最新 main；检查采集期间 main 是否变化，发生冲突退出75，需重新生成，不 rebase 派生数据或 force push。生成及提交完成后输出完整 SHA，由独立可复用发布 job 处理。

三种入口都调用 `release-deploy.yml`，只有它持有 `maas-production-deploy-main` 锁。运行中的激活事务不取消，pending 使用 max 队列；候选必须是准确 checkout 的 main 祖先，main 新增运行文件时跳过旧候选，仅新增普通文档时仍允许该候选。构建后及激活前复查，服务器既有 flock/旧提交拒绝/蓝绿事务保留。队列上限与调度语义按 [GitHub 官方 concurrency 文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) 实现；本轮验证本地图结构和隔离 Git 场景，真实调度待合入运行。

生产包由精确 commit+datasetVersion 选择 RID，替代目录mtime。统一工作流用部署脚本输出的实际 RID 验四入口。数据工作流的 GITHUB_TOKEN push 不依赖自动链式触发，显式调用发布。原 health/Issue 去重通知保留（本轮未发送消息/Issue）。

| 改动 | 路径 |
| --- | --- |
| API/站点/pipeline/ops/Schema/运行合同 | 统一发布，固定触发SHA |
| 手工 data 或站点内容 Markdown | 统一发布 |
| data/weekly 正式源 Markdown | 调用 import 写入流程后发布生成提交SHA |
| 自动采集数据 | 写入流程显式发布，GITHUB_TOKEN不产生第二条push发布链 |
| 普通 docs/README/研究 Markdown | 不发布 |
| 手动恢复 | 固定完整main候选SHA；旧线上版本使用标准rollback；恢复候选需包含AR-05策略工具 |

records 两类 fixture 同次在临时输入根/outDir 构建，真实 records/index/dist 不写。异常路径清理临时根；即使进程直接中断，正式输出也不会含 fixture，无需恢复构建。API统一回归只编译一次，正式运行包复用已验dist、独立安装omit=dev。依赖缓存按lockfile、Node/npm/ABI/平台指纹，缺失缓存重新npm ci；Python3.12使用已验证依赖闭包 `requirements.lock.txt` 约束直接及传递版本，升级必须改锁并重跑验收。锁定版本取自测试环境，不宣称最新。

## 验证

**标准 build-release + 完整回归 47/47，0失败，322.73秒**。从同提交干净 checkout、空node_modules和全新Python3.12 venv运行；锁定依赖安装成功，tracked diff gate通过。增加2个依赖门禁和1组协调测试，去掉1次恢复build，原业务断言保留。

9个新增场景实际验证写入冲突/重生成、采集中代码push、较旧候选晚完成、非main分支、仅文档追加、触发表、独立锁图、真实失败退出23和日志保留、缓存无效重装、目录mtime无法选错RID。原workflow18项、deploy7项、records转义/withdrawn/正式索引字节与页面集合不变通过；既有release候选失败/上传/回退/manifest门禁包含于完整套件。

标准产物 `rl_cb03a05b82_6fd3cc403bf9`：24355文件，703621161字节，datasetVersion `ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`，dataThrough 2026-10-01。仅生产依赖、仓库外cwd启动实际API进程，REST四查询、MCP initialize/五工具/changes版本一致；同release RSS字节和Skill8文件hash通过，测试fixture页不存在。静态验证不等于真实Nginx/CDN验证。

- [完整回归/标准构建报告](acceptance/AR-05/regression.json)及其日志。
- [产物元数据与manifest指纹](acceptance/AR-05/release-build.json)。
- [独立运行包冒烟](acceptance/AR-05/release-smoke.json)。
- [协调场景](acceptance/AR-05/workflow-scenarios.txt)、[原workflow回归](acceptance/AR-05/workflow-regression.txt)、[部署回归](acceptance/AR-05/deploy-regression.txt)。
- [页面fixture验证](acceptance/AR-05/records-test.txt)、[干净Python安装](acceptance/AR-05/python-clean-install.txt)。

## 耗时与构建次数

正式release中的Astro从4次降至2次（真实输出1+隔离fixture1），API TS编译从5次降至1次。AR-02回归430.07s，AR-05标准构建含回归/生产依赖/组装322.73s；额外步骤与机器负载不同，不能把全部差异归因于本次代码。

同工具三轮阶段中位秒数：

| 阶段 | AR-01 | AR-05 |
| --- | --- | --- |
| projection | 15.326 | 5.133 |
| publicCheck | 0.081 | 0.065 |
| apiCompile | 1.197 | 1.063 |
| astroBuild | 35.534 | 25.783 |
| staticDataAssembly | 8.651 | 8.416 |
| cleanInstall:site | 2.327 | 2.274 |
| cleanInstall:services/agent-api | 0.856 | 0.824 |

[构建阶段采样](acceptance/AR-05/build-profile.json)。AR-01曾与API benchmark重叠；本次隔离采样，projection/Astro自身并未作业务优化，阶段差异反映负载/缓存条件。cleanInstall是空node_modules+温npm下载缓存，未宣称空网络缓存冷启动。新Python环境实际从PyPI安装锁定闭包；Requests/Playwright对应版本在 [PyPI Requests](https://pypi.org/project/requests/2.34.0/) 和 [PyPI Playwright](https://pypi.org/project/playwright/1.54.0/) 核实。

## 使用与回退

完整本地验证：`PATH=<Python3.12环境>:$PATH bash scripts/run-all-tests.sh`。标准构建只从已提交干净HEAD执行 `bash scripts/build-release.sh --commit <完整SHA>`；产物离线验证 `bash ops/verify-release.sh --offline <release目录>`，独立运行包验证 `node scripts/architecture-release-smoke.mjs <release目录> <报告路径>`。

冲突退出75时，在新执行中从最新main重新采集/导入；保留失败日志诊断，不强行提交旧派生输入。发布回退沿用标准release rollback；工作流回退使用明确代码提交，不撤销已合法归档数据。线上共享配置不由本任务自动修改。

验收后删除本次临时checkout/release产物，仅保留可复核元数据/日志；后续任务改变运行代码，最终部署候选需从全部改造完成后的准确commit重建。Python临时环境仍用于后续回归，结束时清理。
