# 架构改造进度

2026-10-01：开始执行，读取任务入口、全局/站点规则及 planning-with-files 技能；核对初始工作区。当前 AR-01。

首次回归在沙箱遇到本地 socket PermissionError，主动停止（130），日志存 acceptance/AR-01/failed-sandbox.txt；用允许本地测试服务的环境重跑，不算成功证据。benchmark 已在允许环境完成。

AR-01 完成：完整回归 45/45，531.63s；benchmark 3轮/并发1、10、30/1×5×10×；build profile 3轮；合同/README 历史描述已对齐。基线实际 raw bytes/data 722781185，source snapshots 248330316，public 368500150。尚未实时检查生产。

AR-02 实现进行中：worker校验/解析，200实体ACK流式回填；同版本manifest跳过；异步历史single-flight、有界LRU；日期/身份索引与二分cursor；共享REST/MCP异步查询；每IP限流+全局护栏、IPv4映射/IPv6规范化、loopback显式信任。当前/历史加载统一路径，并全序检查、引用检查、最终及祖先symlink边界校验。
针对性/API回归62/62通过（2026-10-02）；完整回归session78700仍执行site records段。容量首测已通过预算，完成完整回归后要重跑带重载期间在线请求的扩充采样（上次报告引用检查改动前，不能最终引用旧源hash）。ops生成器与install-api-runtime.sh候选仅本地，未执行生产安装；真实Nginx未安装，线上代理链验证待发布窗口。

AR-02 本地完成：45/45完整回归430.07s；最终带重载流量容量测量通过，并发10 P95最大24.1ms，10×强制重载loop最大14.7ms，332请求全部200。源码SHA/API62项日志/容量/回归/结果归档完成；生产配置及真实Nginx代理链待发布验收。下一项AR-05。
