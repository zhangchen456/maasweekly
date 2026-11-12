# 099 采集资源保护

2026-11-12 的恢复中，价格归档全量校验长期保留了已解析的历史正文；主机随后出现可用内存不足、磁盘读队列增长和 SSH/HTTPS 无响应。此前的 writer 允许额外使用 swap，服务器定时入口还绕过了临时 systemd 单元。不能仅凭控制台旧日志判定这次发生了 OOM。

## 固定策略

策略位于 `ops/data_job_resources.py`，请求不能覆盖。

| 边界 | 策略 |
| --- | --- |
| 启动准入 | 主机 MemAvailable 至少 1536 MiB，否则登记失败并退出 |
| writer 内存 | 根据可用内存预留 512 MiB，按 64 MiB 取整；至少 1024 MiB，最多 1536 MiB |
| 发布容器 | 256–512 MiB，使用同一主机预留规则 |
| 容器 swap | 0；Docker `--memory-swap` 与 `--memory` 相等 |
| 容器磁盘 | 数据文件系统所在整盘的读、写各 16 MiB/s，从容器启动即生效 |
| 控制器及直接子进程 | systemd MemoryHigh=768 MiB、MemoryMax=1 GiB、MemorySwapMax=0；读写各 16 MiB/s；IOWeight=10 |
| 内存巡检 | 每 2 秒；连续两次 MemAvailable <512 MiB 时中止当前子进程和本任务容器 |
| 截止时间 | 任务总计 90 分钟；systemd 95 分钟；外层定时服务 105 分钟，依次留出收尾时间 |
| 数据库等待 | writer 查询最多 10 分钟、锁等待最多 30 秒；pg_dump 锁等待最多 30 秒，备份阶段最多 10 分钟 |

主机必须提供 cgroup v2 的 memory/io 控制器。整盘设备从共享目录的实际块设备解析，并验证设备号；分层块设备暂不支持，不能绕过检查启动。运行时核对容器 `memory.max`、`memory.swap.max`、整盘 `io.max`，不生效就退出。

数据库服务本身供网站和后台共享，其后端 I/O 不在 Docker 的设备限速范围内；SQL 超时用于限制采集带来的长期占用。该策略降低采集拖垮主机的风险，不替代主机容量监控。

## 退出与重启

服务器定时任务与手动发布统一通过 root 管理的 `data-job.sh`，凭据仍只经 stdin 传递。SIGTERM、低内存、阶段超时会停止本次已确认 CID 的容器并回收子进程，写入失败阶段及资源记录。不得停止其他容器，不删除历史数据或备份，也不修改已发布指针来假造成功。

在持有 release.lock 时，下一次调度会检查未完成任务的 boot ID、PID 和进程启动时间。确认进程已退出后，先保存原始元数据，核对并停止属于该任务的孤立 writer，再生成协议允许的 `interrupted` 回执。保留输入 checkpoint。已有最终回执优先；已经原子发布但未完成验收的任务保留 `partial` 发布事实，控制任务仍为失败。当日失败不自动反复重试；后续日期可正常调度。

部署切换会同步当前 API 槽位的开机启动配置，并在回滚时恢复原配置，避免重启后网站没有启动。

## 价格归档内存

全量校验仍逐个验证所有版本、快照、证据、修订和索引的身份、哈希及引用。验证后只保留后续检查所需的字段和 ID 集合，释放历史正文。在 10,000 条合成版本基准中，tracemalloc 峰值由 40.78 MB 降为 11.04 MB（约 73%）；这不是整个采集进程的内存承诺。

## 发布与排查

先通过统一运行时测试并发布完整代码包，再执行活动运行时内的 `tooling/ops/install-reliability.py`。安装器验证 manifest 哈希、备份原 root helpers 并原子安装，不能直接编辑线上 root 控制器。运行时打包从安装器 MAPPING 自动包含所有 helper。

主机证据路径：

- `shared/pipeline-resources/<jobId>.json`：固定策略、最低可用内存、实际 cgroup 限制、容器峰值与退出原因。
- `shared/pipeline-monitor/{current,daily}.json`：控制任务及失败阶段。
- `shared/pipeline-monitor/reconciled/<jobId>.json`：重启恢复时的原始状态及孤立容器处理记录。
- `shared/data-store/reports/writer-*.log`：采集阶段日志。
- `shared/reliability-install/<timestamp>/`：安装前 helper 备份及哈希审计。

测试覆盖低内存和指标读取失败、超时/信号回收真实子进程、错误清理回调、实际 cgroup 限制核对、拒绝停止非本任务容器、重启中断恢复、部分发布事实、凭据不落盘、完整工具包和 API 导入协议。

Docker 参数语义：[资源约束](https://docs.docker.com/engine/containers/resource_constraints/)、[docker run](https://docs.docker.com/reference/cli/docker/container/run/)。
