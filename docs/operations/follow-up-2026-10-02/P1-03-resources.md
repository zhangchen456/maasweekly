# 生产资源预算与发布包保留

## 基线与预算

实测机器 RAM 3,663,818,752 bytes（约 3.41 GiB）；可用约 1.12 GiB，无 swap。当前服务 cgroup MemoryCurrent 约 189.67 MiB、MemoryPeak 约 301.22 MiB；MemoryMax=infinity，不把预算当成已安装的硬限额。root 使用率 78%，可用约 8.40 GiB；共享 journal 约 173.8 MiB，未设置显式 SystemMaxUse/MaxRetentionSec。历史发布包合计约 19.45 GiB。

预算来源 `ops/resource-budget.json`，可用 `python3 scripts/operations-budget.py <resource-snapshot.json>` 复核。规则及模式为 advisory，工具不更改生产、不自动扩容或删除。

| 指标 | 预警 | 严重 |
| --- | --- | --- |
| root 使用率 | ≥80% | ≥90% |
| 可用磁盘 | ≤3 GiB | ≤1 GiB |
| 可用内存 | ≤768 MiB | ≤384 MiB |
| 单服务 cgroup 峰值 | ≥512 MiB | ≥768 MiB |
| 全机 journal 占用 | ≥256 MiB | ≥512 MiB |
| 事件循环 P99 | ≥50 ms | ≥100 ms |
| release build | ≥15 分钟 | ≥30 分钟 |

恢复目标暂设 180 秒用于后续演练；本次没有执行真实生产回滚，因此不宣称生产 RTO 达标。日志目标保留 14 天，仅记录预算，没有改共享 journald 配置，也没有 vacuum 其他服务日志。

蓝绿需容纳两个加载峰值和其他进程，不能以当前约 190 MiB 稳态估算安全容量。5×/10×仍用已有本地基准作规划参考，不在这台生产机上强制合成负载。接近阈值优先缩减可重建部署冗余、核验缓存/加载峰值，再评估资源升级；不直接引入数据库、队列、多实例。

## 保留规则修复

原清理器合并所有历史包的 retainedVersions，过期包互相保留，13 个超过七天的包全部被旧引用挡住。修复为只从 current/previous 的公开 manifest 计算活跃数据引用；保留 current、previous、活跃引用数据及七天内发布包。损坏/越界保护指针使整个清理跳过；坏候选、未知名字和符号链接均保留，不猜测或跟随删除。

新增固定只读动作 `cleanup-plan`，与清理使用相同代码和发布锁。生产只读预览保留 19、候选 13，依据已有磁盘盘点预计可释放 5.243 GiB；这是预览，不是已经释放。快照与原始证据不属于此次清理路径。

4 项执行级保留规则测试通过；46 项现有激活测试完成（1 项平台相关 skip）。本地完整回归 57 组通过、0 失败（P1-03-regression.txt）；精确提交的 CI 最终 57/57 成功。计划/实际结果分别保存，安装候选 helper 时保留旧 helper 备份；执行后再验 current/previous、四入口和实际 df。

## 额外清单偏差

公开 manifest 中有两份此前本地调试生成、未部署且目录已移除的临时 DS 引用。它们没有实际线上签发游标，但属于保留元数据偏差，需在公开数据维护中修正，不能把缺失目录宣称为可恢复历史。当前和上一版的正式 DS 目录存在。本次清理预览不伪造或恢复缺失数据。

## 已批准执行与清理后验收

自动审批起初拒绝实际删除，候选 helper 曾恢复为原版本，避免间接删除。用户随后明确确认“删除过期的包”；重新核对清单，仍为同一 13 个包后执行。实际移除 13 个，释放 5,629,603,840 bytes（5.243 GiB）。root 使用率 78% → 64%，可用磁盘 9,024,180,224 → 14,653,784,064 bytes。current/previous 指针均保持不变；原脚本备份保存在服务器 root 私有备份目录，没有采集密钥或 env 内容。

P1-03-cleanup-actual.txt 为实际操作与版本记录，P1-03-cleanup-summary.json 为磁盘差值。候选清理器已安装；共享 journald、服务 MemoryMax 和日志 vacuum 未改变。

最终精确候选 CI 57/57 成功，release rl_b5f299d185_4d80d26fca8d 已激活，上一版 rl_f3e2da7bc9_a032da03d915 保留。最终 CI 与生产指针记录在 final-ci.json / final-production-status.txt。
