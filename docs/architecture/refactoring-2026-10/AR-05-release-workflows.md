# AR-05：工作流与发布构建

状态：TODO。优先级：P1。依赖：AR-01。

## 目标与交付

协调每日、每周和代码更新的写入/发布，减少重复构建，确保测试 fixture 无法进入生产包。保留精确 commit、不可变 release、manifest、服务器互斥与蓝绿切换。

交付：更新后的工作流、构建/测试隔离、变更触发表、故障场景验证、耗时对比和 `AR-05-result.md`。

入口：`.github/workflows/{daily-update,weekly-update,deploy}.yml`、`scripts/{run-all-tests,build-release}.sh`、`ops/{deploy-release,verify-release}.sh`、`ops/server/maasweekly-activate`、`tests/test_workflow_release_contract.py`、release 测试、`site/tests/records.test.mjs`。

## 5A. 数据写入与发布协调

当前三个不同 concurrency group 不能相互协调。分别设计两类互斥：

1. **数据写入**：每日/每周共享同一个写入序列；任务获得执行权后检出最新 main，生成并提交数据。代码提交导致 push 冲突时，不 force push；从最新输入重新生成或明确退出重试，不盲目 rebase 派生数据。
2. **生产发布**：所有触发源进入同一生产部署 job/可复用工作流，按精确 commit 选择候选，过时的尚未激活候选允许跳过，并记录原因。只保留最新候选还是需要逐一处理，应在工作流说明中明示。

避免在父工作流与被调用工作流持有同名锁造成等待自身；不要仅把三个 group 字面值改成一样就视为完成。实现前按当前 GitHub Actions 官方文档确认排队、取消与 reusable workflow 的作用域。

在激活事务开始后不要因新 push 随意取消运行。服务器 `flock`、旧提交拒绝继续作为最终保障；现有 timestamp + SHA 排序不等于 Git 祖先关系，候选选择应限定批准的 main 提交，异常分支排序不得默认视为安全。

## 5B. 精确版本与触发规则

数据提交成功后取得确切 SHA，把该 SHA 传给构建与部署；不能在后续阶段重新解析浮动 main。构建产物同时携带 code commit、datasetVersion 和验证状态。

建立触发表并测试：

| 变化 | 预期 |
| --- | --- |
| API、站点、pipeline、ops、Schema/合同运行文件 | 按影响构建验证并进入发布路径 |
| 已由采集工作流发布的数据提交 | 防止重复发布；不能因此遗漏无采集任务负责的手工数据修正 |
| 正式周报 Markdown / 内容源 | 经正式导入或重建路径更新页面与 RSS |
| 普通说明文档 | 不触发运行时发布 |
| 手动恢复发布 | 固定指定 commit，保留完整门禁 |

不要依赖 bot push 自动触发下一个 workflow；按实际 token 与触发规则验证。最终可使用显式调用统一发布 job，确保一次数据更新有唯一负责的发布路径。

## 5C. 测试与构建隔离

目前 records 测试会用 fixture 重建，再用最后一次 Astro build 恢复正式输出。改为临时输入根和临时 outDir，正式 build 只消费真实已提交输入。

将依赖安装、编译、测试、正式构建、打包职责明确分开。API 编译结果可在同一次流水线中复用，生产依赖单独安装；缓存以 lockfile、Node/Python 版本和平台为键，不只判断 node_modules 目录存在。

保留 tracked diff gate，但区分“应提交的确定性数据投影”与“仅构建输出”。逐项迁移生成文件的归属，不能通过忽略所有差异或移除校验来消除构建失败。

本地依然保留一个清晰的完整验证入口。测试脚本需要报告真实退出码；失败日志若给出路径就必须保留，成功日志和临时目录及时清理。

## 5D. 场景验证

在测试仓库、mock remote 或隔离环境验证，不向生产制造冲突：

- 每日与每周同时触发，数据提交不互相覆盖。
- 采集执行期间 main 有代码提交：安全重试或明确退出，不发布错误 SHA。
- 较旧构建比新构建更晚完成：旧候选被跳过/拒绝，不覆盖 current。
- 测试中断/失败：正式 dist 没有 fixture，未通过测试的产物不可激活。
- 上传失败可重试，候选启动失败/验证失败仍按既有事务恢复。
- Markdown 周报与手工事实修订能到达正确发布路径，普通 docs 不部署。

## 验收标准

- [ ] 三种触发源进入统一生产协调，不存在隐性锁死和无负责方的更新。
- [ ] release 的 commit、datasetVersion 与实际打包输入一致。
- [ ] fixture 不写正式构建目录，正式产物扫描无测试 ID/测试页面。
- [ ] 原有 manifest、旧版本拒绝、候选槽位、四入口验证、回滚测试全部通过。
- [ ] 冷/热构建耗时与重复编译次数有前后对比，未通过删测试获取加速。
- [ ] 干净环境安装依赖后可完整构建；Python 依赖固定策略有明确记录，避免每次构建无边界漂移。

验证至少包括 workflow/release 相关 Python 测试、站点 records/RSS 测试，以及一次标准 `scripts/build-release.sh --commit <准确SHA>`。正式构建应在已经提交的干净 checkout 运行，别为绕过 preflight 清理用户工作区。

## 发布与回退

先合入隔离测试和构建改进，再切换工作流协调。保留可从精确 SHA 手动发布的受控入口。工作流回退不撤销已经合法归档的数据；生产回退继续使用现有协议，并在结果中记录哪些共享配置需要额外恢复。
