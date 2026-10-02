# AR-06 本地存储迁移验收

状态：LOCAL_VERIFIED（用户指定的本地适配器、迁移演练和成本评估）。日期：2026-10-02（Asia/Shanghai）。候选 commit `593d858abe10e806ea69fec233ed3ae0e5ed2890`，未推送、未发布；远端启用、引用切换和停止 Git 原始快照跟踪为 DEFERRED。

实现按 SHA256 寻址的 filesystem blob adapter、幂等复制/逐对象校验、兼容读取、每次构建独立的 64 MiB 有界缓存和固定 commit 迁移 manifest。恢复与现有管线共用写入锁；中断留下 pending 标记，阻止候选构建和其他 writer，允许同清单续跑。已有内容不一致时拒绝覆盖。清理只生成超过 14 日宽限且所有提供清单均未引用的对象列表，没有实际删除。

固定提交下 2,197 个原始文件、248,330,316 字节，对应 2,188 个唯一对象、247,229,743 字节；去重收益约 0.44%。199 份价格 snapshot 元数据中 173 份匹配现有原始文件，26 份历史原始文件此前已缺失；保留其元数据、摘录和证据关系并显式标记 `legacy_raw_missing`，不宣称能够恢复这 26 份原始文件。完整清单及存储分类见归档。

从空目录仅凭固定提交代码、元数据和本地对象存储恢复，所有现有 raw bytes/hash 与 199 份价格元数据一致，所有历史公开版本路径保留。归档校验、价格归档、七集合导出与 Astro 构建通过；公开七集合字节相同，datasetVersion 仍为 `ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`，dataThrough=2026-10-01。Astro 生成 19,267 路由，最终 19,269 HTML 文件包含两份既有静态页面。

最终演练冷复制 2.974 秒、代码/元数据恢复 24.554 秒、原始文件续跑恢复 4.453 秒；价格归档 24.638 秒、导出 17.585 秒、站点构建 53.720 秒。缓存载荷 64,884,498 字节，小于 67,108,864 上限。站点使用已有锁定依赖缓存；没有测量冷网络依赖安装、总体 RTO 或生产磁盘恢复，不能判断尚未设定的生产 RTO 是否达标。早期缓存扫描开销修正前的 checkpoint 也保留归档。

部分复制、缺对象、损坏、存储不可达、恢复中断与续跑、缓存修复、并发幂等、路径保护和互斥均通过专项测试。隔离候选故障时，仓库外正在运行的 AR-07 last-known-good 封装 API 与既有 cursor 查询持续正常返回；这是本地进程验证，未操作生产 Nginx/CDN。

完整标准 release 回归 **53/53，退出码 0，357.462 秒（含打包）**。候选 `rl_593d858abe_6fd3cc403bf9` 共 24,363 文件、702,985,890 字节，仓库外仅生产依赖实际启动通过 REST/MCP；RSS 和 Skill 八文件 hash 一致。

证据：[完整回归](./acceptance/AR-06/regression.json)、[迁移清单](./acceptance/AR-06/migration-manifest.json)、[空目录演练](./acceptance/AR-06/drill.json)、[持续服务故障验证](./acceptance/AR-06/sealed-runtime-faults.json)、[封装发布包](./acceptance/AR-06/standalone-release.json)、[存储盘点](./acceptance/AR-06/inventory.json)。复核及回退流程见 [恢复操作](./storage-recovery-operations.md)，增长假设、成本公式和启用条件见 [成本与保留评估](./storage-cost-and-retention.md)。Git 历史未重写、原始快照未移除；不能把理论 checkout 收益当作已经缩小 Git pack。
