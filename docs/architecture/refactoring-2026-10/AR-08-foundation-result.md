# AR-08 基础指标验收

状态：基础阶段 LOCAL_VERIFIED；整项 AR-08 仍实施中。完成时间：2026-10-02（Asia/Shanghai）。未推送、未发布，来源/发布事件接入与最终容量复核将在后续任务完成。

API 使用有界异步 JSONL 日志，关联 requestId、固定路由、releaseId 和实际服务的 datasetVersion；历史 cursor/MCP 版本通过 AsyncLocalStorage 记录。每分钟采集内存、事件循环、缓存和数据新鲜度；健康分为存活、就绪、fresh/stale/unknown。公开错误不再泄露加载路径，查询参数与实体 ID 不进入聚合标签。`MAAS_DIAGNOSTICS=0` 可独立关闭，未改 Umami Cloud 或 country 路由。

修复普通无变化轮询使在途强制校验失效的竞态。候选序号仍保证较旧候选不能覆盖新版本；新测试证明强制校验失败会记录错误且继续服务当前数据。

完整回归 **48/48，退出码 0，293.996 秒**。输入提交 b99b5c7c2 的本地改造源码已按 SHA-256 归档；正式数据版本 ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f。API 基础测试新增 5 项，告警汇总新增 3 项，真实服务验证 enabled/disabled/unready 三种模式。未就绪时 status 仍返回既有 200，价格查询 503；内部 ready=false。完整回归含 REST/MCP、版本保留、公开导出、RSS/Skill、身份注册表、价格/记录、SEO、多语言和分析统计。

同机器同 1× 数据依次运行诊断 off/on，各 3 轮、并发 1/10/30、每轮 60 请求。并发 10 最差 P95 为 off=15.973ms/on=15.324ms，事件循环 P99 off=12.927ms/on=12.575ms；开启日志零丢弃、零失败。并发 30 P95 off=25.561ms/on=49.403ms，仍为短采样波动，应随最终容量复核观察，不能宣称开启指标使服务更快。输出流是 discard Writable：实际执行序列化、队列、异步写，不测生产 journald/磁盘吞吐。有界背压、故障、超长与循环对象另有验证。

告警工具仅在本地汇总和更新原子状态，不发送真实通知。模拟来源失败/未运行、429/409/5xx、加载失败、候选失败、价格数量下降及恢复通过。真实来源和发布字段将在 AR-04/后续发布接入；服务器日志磁盘上限和实际 journald 开销待发布窗口核对。运行方法、去重、恢复和保留期见 [运行说明](./observability-operations.md)。

证据：[完整回归](./acceptance/AR-08a/regression.json)、[关闭采集](./acceptance/AR-08a/diagnostics-off.json)、[开启采集](./acceptance/AR-08a/diagnostics-on.json)、[实际服务](./acceptance/AR-08a/server-smoke.json)、[源码哈希](./acceptance/AR-08a/source-files.json)。开关回退不删除诊断证据，代码回退沿用不可变 release 协议。未执行 Nginx/CDN 测试或生产配置变更。
