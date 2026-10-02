# 架构改造交付与验收入口

本轮实现按任务顺序完成，本地验收逐项归档。当前实现分支 `codex/architecture-refactoring`；未推送、未部署。所有公开集合保留原 datasetVersion 与 dataThrough；不能把本地完成解释为生产 RELEASED。

| 任务 | 交付 | 每项验收 |
| --- | --- | --- |
| AR-01 | 基线、契约偏差、冻结比较方法 | [结果](./AR-01-result.md)，45/45 |
| AR-02 | 后台加载、查询索引、cursor 历史缓存、客户端限流 | [结果](./AR-02-result.md)，45/45 |
| AR-03 | 标准输入、事实/摘要分离、共享公开合同 | [结果](./AR-03-result.md)，49/49；七集合与旧版字节一致 |
| AR-04 | 八家适配器、固定输入、单写入事务、恢复/撤销 | [结果](./AR-04-result.md)，50/50；17 fixture 与旧抽取器一致 |
| AR-05 | 构建隔离、依赖锁定、exact-SHA 工作流、发布锁 | [结果](./AR-05-result.md)，47/47 |
| AR-06 | 本地 blob、迁移清单、恢复演练、保留/成本方案 | [结果](./AR-06-result.md)，53/53；远端 DEFERRED |
| AR-07 | 一次索引、有类型页面数据层、Astro 价格组件 | [结果](./AR-07-result.md)，52/52；107 模型与真实浏览器行为对账 |
| AR-08 | 请求/数据/来源/发布观测、有界日志与告警、容量决策 | [最终结果](./AR-08-result.md)，53/53；[基础验收](./AR-08-foundation-result.md)，48/48 |

最后一轮全量回归覆盖所有已合并改造，不用各阶段测试数量相加表示覆盖率。每份结果关联自己的源码 commit、候选 RID、真实退出码、JSON/文本证据及测量边界。

## 维护操作入口

- [管线恢复](./pipeline-recovery-operations.md)：run/输入版本、pending、重试/恢复/撤销、离线原时间。
- [页面数据层](./frontend-data-operations.md)：新页面入口、共享组件、严格类型与浏览器复核。
- [存储恢复](./storage-recovery-operations.md)：固定清单、完整 hash/bytes、恢复锁、空目录演练和只读清理候选。
- [成本与保留](./storage-cost-and-retention.md)：各类存储、14 个观测日条件外推、远端成本变量和复查条件。
- [观测操作](./observability-operations.md)：诊断开关、有限窗口聚合、触发/去重/恢复、日志保留。
- [容量决策](./capacity-decision.md)：1×/5×/10×原始结果、内存余量、数据库/worker/多实例启动条件。

## 待上线验证范围

代码和本地证据已备齐，未来发布继续沿用现有 exact-SHA immutable release/蓝绿/回滚及四入口协议。按候选 manifest 选择 RID，不从文件 mtime 猜版本。

| 范围 | 上线时核对 | 当前状态 |
| --- | --- | --- |
| API 代理链与参数 | 安装候选 helper/运行配置；代理信任、两客户端配额、REST/MCP隔离、RELOAD_INTERVAL_MS、共享CURSOR_SECRET | 本地通过；生产未改 |
| 工作流 | main 候选筛选、同数据 writer、发布队列、真实 artifact 与旧运行跳过 | 图与模拟 Git通过；真实调度待验证 |
| 新数据管线 | 先检查 pending，按固定输入运行；恢复只对同run，旧观察不伪装fresh | 本地故障注入通过；生产执行待验证 |
| 监测 | 检查 journald 现行预算，安装诊断 helper，连续记录真实构建/服务窗口 | 候选实现与本地开关/失败/恢复通过 |
| 资源 | 单实例历史+加载峰值、两蓝绿槽位重叠、服务器RAM/磁盘与RTO预算 | 预算未冻结；不宣称生产达标 |
| 存储 | 桶/区域/认证/预算另选，固定清单复制校验、恢复成功后再逐步切换 | 用户指定先本地演练，远端与Git移除DEFERRED |

存储 26 份既有缺 raw 的历史 snapshot 已显式标记，元数据/摘录/公开证据仍保留；正式远端迁移不能宣称可恢复这些不存在的原始文件。任何 Git 历史重写另立任务，不属于本轮。
