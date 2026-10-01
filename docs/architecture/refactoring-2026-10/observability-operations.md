# 内部诊断运行说明

AR-08 基础：API 在 stdout 输出 JSONL，systemd 收集到现有 journal。`MAAS_DIAGNOSTICS=0` 关闭采集、请求包装和定期内存/事件循环采样，不影响业务。没有新增公网 metrics 路由；Umami Cloud 保持现有统计。

`api.request` 含随机 requestId、固定 route、method、statusCode、elapsedMs、releaseId 和实际 datasetVersion。历史 cursor/历史 MCP 调用通过异步请求上下文记录被服务的版本。requestId 仅关联日志；路由与方法是有界聚合标签。country 路由不采集。

`dataset.load` 记录变更/无变化/失败/被新候选替代、force、耗时、缓存和加载计数。失败公开响应与日志均使用 `dataset_load_failed`，不向客户端输出文件路径。`runtime.sample` 每 60 秒记录 RSS/heap、事件循环 P99、缓存和 fresh/stale/unknown；存活、就绪和新鲜度分别判断。日期精度的成功时间按上海日期结束估计，并明确不是精确时刻。

日志序列化上限每条 8 KiB，应用等待队列上限 256 KiB，Writable 背压停止继续写入，超限丢弃并计数。日志异常不会导致业务请求失败。日志关闭等待最多 1 秒；服务器关闭兜底 3 秒。stdout 的 journald 存储由服务器统一限制：部署前检查 `journalctl --disk-usage` 和现行 journald 配置，建议该机所有服务合计 `SystemMaxUse=256M`、`MaxRetentionSec=14day`，实际修改需按服务器运维范围执行。本轮未修改服务器。若共享 journal 使用其他预算，记录其实际值即可，不能宣称应用排队上限等于磁盘保留上限。

本地汇总：导出一段完整、有限的时间窗口（推荐 24 小时）的 JSONL，然后运行：

```sh
python3 scripts/architecture-observability.py /tmp/agent-api.jsonl --state /tmp/agent-alert-state.json
```

输入只接受内部诊断格式；不要将 Nginx 原始 URL 或访客事件混入。报告以 UTC 标记生成时间；用户报告转换为 Asia/Shanghai。P50/P95/P99 用最近窗口实际请求的 nearest rank；不同窗口不能简单平均百分位。大日志需先按时间分段，当前离线工具保留该窗口时延样本，并非流式无限日志服务。

告警工具只生成结果与原子状态文件，不发送消息或 GitHub Issue。重复窗口通过 runId/sourceId/attemptId 去重；已激活告警不会因缺少采样自动恢复。规则：日级信源连续两个失败尝试（not_run 不清零）、成功时间超过 freshnessBudgetHours（默认 48）、解析数量不足上一成功的 50%（候选异常），无就绪数据、加载失败、stale、候选发布失败、窗口内同路由至少三个 5xx。429/409 单列统计，不自动解释为服务故障。

恢复条件：信源成功且未超 freshnessBudgetHours；数量比恢复至至少 50%；加载结果 changed；health ready/fresh；候选 success；路由窗口至少三个请求且零 5xx。去重键为规则+受控sourceId或固定路由。处理：来源失败查看对应 run/attempt 并重试；数量下降人工核对适配器证据；加载失败先保留旧版并验证 manifest；无有效版本检查不可变 release；候选失败禁止激活；重复 API 错误关联 release/dataset，按现行发布协议排查或回滚。

告警状态保留最多 10,000 个尝试键，输入窗口应覆盖失败/恢复判断；对高频流需调整 freshnessBudgetHours，连续失败不等同于两个自然日。现阶段来源与发布事件由模拟验证，AR-04 和本轮后续发布步骤补齐真实事件输出。通知与采集可独立关闭，未接入新通知渠道。
