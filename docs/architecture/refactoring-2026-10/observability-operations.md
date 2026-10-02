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

告警状态保留最多 10,000 个尝试键，输入窗口应覆盖失败/恢复判断；对高频流需调整 freshnessBudgetHours，连续失败不等同于两个自然日。AR-04 已从真实管线输出关联 runId/sourceId/attemptId/extractorVersion 的事件；AR-08 已接入真实构建入口和服务器激活 helper。通知与采集可独立关闭，未接入新通知渠道。


## 构建与激活记录

`scripts/build-release.sh` 默认在 stderr 输出 `release.stage` 与最终 `release.result`。阶段包括 preflight、projection、regression、clean-tree、runtime-package、assembly、manifest；记录 UTC、受控阶段、退出码、耗时、合法 gitCommit/RID/datasetVersion，成功后附 immutable manifest 的文件数/bytes。Bash 时钟分辨率为 1 秒，短步骤记 0 不代表没有开销。`--preflight-only` 使用独立 preflight operation，不会清除正式 build 失败。诊断在退出 trap 中保留原退出码并完成临时运行包清理；`MAAS_RELEASE_DIAGNOSTICS=0` 可关闭。

`ops/server/maasweekly-activate` 在有效 RID 取得发布锁后，记录 activate/rollback 的最终结果、退出码、总耗时和对应 manifest 身份。诊断在释放原发布锁前完成，失败不改变事务结果；不收集回滚原因、URL、目录或环境变量。服务器固定路径 `shared/state/release-diagnostics.jsonl` 只保留当前和上一次轮转，每份上限约 1 MiB；记录权限 0640。更新需沿用现有安装与回退流程，源码已修改不代表 helper 已在生产替换。未取得锁的非法请求不写诊断，也不会释放其他操作持有的 mkdir 锁。

统一 release workflow 保留 `pipefail`，通过 tee 收集构建日志，always 汇总并上传 14 日 artifact；未选中的候选不产生构建报告。真实 GitHub artifact 尚未执行验证。线上四入口验证失败继续按原 CI 失败通知处理；本工具不新增外部发送、不会把 build 成功视为线上验证成功。

```sh
python3 scripts/architecture-observability.py /tmp/release-build.txt --mixed --state /tmp/release-alert-state.json
python3 scripts/architecture-observability.py /tmp/release-diagnostics.jsonl --state /tmp/activation-alert-state.json
```

`--mixed` 只提取含 kind 的 JSON 对象，不将普通 CI 文本作为指标。默认每次最多 100,000 事件、单条 8 KiB；窗口超限明确退出，旧告警状态保持原样。按 24 小时或更小窗口切分；不是无限日志流。构建、激活、回滚各自触发/恢复，重复失败不重复触发。既有 daily-update Issue 通知保留；聚合器只输出 transitions，可供已有通知维护者复用，未开设或测试发送新渠道。

API 仅在成功加载新数据时附 dataCounts（变化、价格、证据、未解析 modelId 的价格数），并标记完整引用校验已通过；不会每个请求重扫全量数据。来源事实数量下降判断使用 AR-04 的前次成功计数，离线回放仍为 not_run，不伪造新鲜度。

构建总时长、磁盘与生产 RSS 阈值需按真实机器和调度周期设置；本地容量报告先记录实测值和启动条件，不将未设定的预算伪装成达标。人工处理顺序：保留 last-known-good → 查看对应阶段/run → 验证 manifest/输入 → 依原协议重试或回退；存储 pending 按 AR-06 操作手册处理。
