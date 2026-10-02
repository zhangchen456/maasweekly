# AR-08 最终观测与容量验收

状态：RELEASED（2026-10-02），见[线上验收](./release-2026-10-02.md)。 以下实施候选及本地验收描述保留历史记录。

完成请求/实际数据版本关联、来源 run/attempt/extractor 事件、成功加载时的数据计数与未解析价格计数、健康/就绪/新鲜度分离。构建真实入口输出七阶段及终态，关联 gitCommit/RID/datasetVersion 和产物 totals；激活/回滚在发布锁内输出终态、原退出码与总耗时，固定 JSONL 当前+上一份约 2 MiB。没有新增公网指标接口或改变 Umami 字段。

诊断异常和关闭不改变业务/发布结果，原临时包清理与锁释放保留。修正未取得 mkdir 锁也可能释放他人锁的边界；在合法发布事务持锁后才写激活诊断。聚合器区分 build/preflight/activate/rollback，分别触发、去重和恢复；preflight 成功或 build 成功不清除 activate 失败。有限窗口默认最多 100,000 事件/单条 8 KiB，溢出退出且保留旧状态。来源连续失败、过期、数量骤降、加载/就绪失败、5xx、候选失败等规则保留；429/409 单列统计。

统一 release workflow 用 pipefail + tee 保留真实退出码，always 汇总/归档 14 日 artifact；既有 Issue 失败通知路径未改，没有向真实用户发送测试告警。实际服务器 helper 安装、真实 GitHub 调度/artifact、journald 配额和连续生产趋势尚未上线验证。

真实 build preflight 失败/关闭、真实激活 helper 的缺候选/重复失败/恢复/幂等/轮转与关闭、去重键隔离、输入溢出保留状态通过专项测试。46 项激活回退测试通过（macOS 按既有条件跳过 1 项 Linux flock 并发用例）；6 项观测和 9 项工作流专项测试通过。早期执行期间更新脚本引起的一次 Bash 读取失败已舍弃，固定源码重跑成功，失败记录保留。

隔离容量 1×/5×/10×并发 10，三轮最大 REST P95 14.3/24.6/35.4 ms、loop P99 12.4/14.1/19.4 ms，满足冻结 200/50 ms 目标；同版本业务解析增量 0，分页无重复/遗漏，实际 MCP SDK 查询成功。10×稳态 RSS 1751.1 MiB、整个子进程峰值 3107.0 MiB；冷加载中位 3680.4 ms，比早期同步基线更慢，保留 worker 验证/索引代价。1×诊断 off/on P95 14.265/16.482 ms，无丢弃/写失败；仅测 discard Writable。实际服务另验证启用/关闭/无数据，启动 RSS 198.3 MiB 不代表加载/历史峰值。

完整标准 release 回归 **53/53，退出码 0，359.087 秒（含打包）**。真实构建事件记录总时长 358 秒，Bash 分辨率 1 秒；包装器精确墙钟与阶段日志不是同一统计口径。候选 `rl_6a78846238_6fd3cc403bf9` 共 24,363 文件、702,986,268 字节，保留于项目 dist-release。仅生产依赖的仓库外进程 REST/MCP 成功、RSS 两 feed 和 Skill 八文件 hash 一致；公开七集合与当前数据字节一致，DS 仍为 `ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`，dataThrough=2026-10-01。未执行 Nginx/CDN 或真实部署。

证据：[完整回归](./acceptance/AR-08/regression.json)、[真实构建事件](./acceptance/AR-08/build-events.json)、[构建告警汇总](./acceptance/AR-08/release-diagnostics.json)、[专项测试](./acceptance/AR-08/targeted-tests.json)、[容量](./acceptance/AR-08/capacity.json)、[诊断开关容量](./acceptance/AR-08/diagnostics-capacity.json)、[实际服务](./acceptance/AR-08/actual-server.json)、[封装运行](./acceptance/AR-08/standalone-release.json)、[公开数据一致](./acceptance/AR-08/public-parity.json)。

[容量决策](./capacity-decision.md)明确暂缓数据库、队列和多实例；先按实际加载/历史缓存/蓝绿重叠确定生产内存。连续真实 CI 和来源趋势需上线观察，样本不足不预测精确扩容日期。生产 RAM、磁盘保留和 RTO 预算待冻结，不宣称生产已达标。启动条件与操作、关停/回退见 [观测运行说明](./observability-operations.md)，所有任务入口见 [交付索引](./delivery-index.md)。
