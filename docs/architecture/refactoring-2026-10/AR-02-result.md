# AR-02 验收结果

状态：DONE_LOCAL / PRODUCTION_PENDING。2026-10-02（Asia/Shanghai）。当前与历史加载、查询和限流已实现；未发布，未修改生产配置。

## 改动与兼容

- 同版本轮询只读 manifest；不可变槽位默认禁用周期轮询，SIGHUP 强制重新校验。
- worker 完成业务文件 bytes/hash、结构/引用/全序检查和初始索引；200 实体一批、ACK 背压回填候选，完整后一次替换 current。失败续服旧版；加载序号及最新指针复查拒绝被取代候选；关停取消加载。
- 新版和历史版复用同一验证链。同版本并发读取 single-flight，串行后台作业限制峰值；历史 LRU 默认 2 版本/128 MiB 原始字节，current 不淘汰，缓存淘汰不使磁盘仍保留的游标过期。
- 日期二分、provider/model/family 候选索引和 cursor seek；weekly 排序预计算。REST/MCP 共用异步查询入口，保留 HMAC、固定版本、Decimal 条件和字节 ETag。
- REST/MCP 独立每 IP 桶、全局护栏和有界溢出桶；IPv4/IPv6 标准化，只有显式受控 loopback 代理才能提供真实 IP。配置生成器覆盖身份头，Nginx 自身 429 提供 Problem JSON、Retry-After 和 CORS。

## 回归与证据

完整项目回归 **45/45，0 失败，430.07 秒**。API **62/62**，新增 8 个运行时场景；包括同版本10次业务解析为0、坏hash/合法hash坏引用拒载、失败续服、候选竞争、历史并发首次读取、零预算/有界LRU、真正清理409、关停、索引差分和代理信任/配额边界。

- [完整回归报告](acceptance/AR-02/regression.json) 与其指向的完整日志。
- [API 测试输出](acceptance/AR-02/api-tests.txt)。
- [最终容量采样](acceptance/AR-02/runtime-benchmark.json)：同机器3轮，1×真实数据、5×/10×唯一ID合成数据，完整游标无重漏；包括源文件hash。
- [候选源码指纹](acceptance/AR-02/source-files.json)。本次从基线431a8f0f工作区验证，运行时测试阶段消费最终实现；所有候选文件随后归档提交。

| 数据量 | 启动中位ms | 同版中位ms | 并发10 P95最大ms | 并发10 loop P99最大ms | 强制重载loop最大ms | 重载时请求P95 ms | 稳态RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1× | 414.6 | 0.167 | 15.5 | 12.9 | 12.5 | 2.0 | 257.8 |
| 5× | 1775.4 | 0.152 | 18.8 | 15.0 | 15.4 | 2.1 | 1187.5 |
| 10× | 3911.2 | 0.146 | 24.1 | 16.3 | 14.7 | 2.0 | 1709.8 |

本地预算通过：并发10 P95≤200ms、事件循环P99≤50ms、同版业务解析0、分页无重漏。重载期间 33/153/332 个请求全部200。首次加载因 worker/结构检查/传输比同步基线更慢，10×约3.9s，但请求继续使用旧版，加载期间停顿低于16ms。10×RSS约1.67GiB；不能据此承诺生产1GiB或2GiB资源预算。AR-01采样曾与构建重叠，RSS差异不单独归因于索引；AR-08继续统一容量复核。

## 配置候选与线上待验收

[install-api-runtime.sh](../../../ops/install-api-runtime.sh) 仅创建可审查安装候选，本轮只执行 dry-run 和 shell 语法检查。激活事务夹具验证实际生成的 REST/MCP 头覆盖、429 JSON/Retry-After/CORS及既有回退事务；本机没有真实 Nginx，**未宣称真实代理链验收通过**。

发布分两阶段：先部署2A/2B应用候选（保持当前限流行为），观察加载/查询；再取得现网 activator 与 agent.env 的SHA（不回传密钥），审核2C候选后安装生成器与env，再经标准release激活渲染代理配置/重启槽位。显式环境设置可覆盖代码默认值，现网 RELOAD_INTERVAL_MS 是否仍为30000必须在此阶段核实。

线上验收：两个真实客户端、REST/MCP独立额度、伪造头、Nginx自身429形状、四入口版本与回退。其完成前2C状态为发布待验收。

回退：标准release rollback保留数据版本；在同一release锁下恢复安装器记录的activator和agent.env两个备份（包含原权限/所有者，保密保存），再用标准激活刷新槽位与三个Nginx include。配置备份不是release自动回退的一部分；安装器不自行reload/start/activate。
