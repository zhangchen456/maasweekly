# 自然定时运行失败与恢复验收

自然运行：37080874994（2026-10-03，北京时间08:09触发；原计划05:00，调度实际延迟）。采集、结构化数据、导出和引用校验均成功；发布完整回归59/60，runtime历史首次加载测试偶发收到 failed。生产门禁拒绝发布，保留原运行版本。

原因：dataset-worker发送done/error后关闭消息端口，父进程通过setImmediate处理消息，exit事件可能先完成失败结算。修复让Worker等待终止消息确认，父进程仍负责超时、取消和最终terminate。

新增回归在收到done/error后延迟50ms，要求Worker保持存活；对旧行为确定性失败（before-fix-reproduction.txt），修复后9项runtime回归通过（runtime-regression.txt）。failure-artifacts保留实际自然运行失败资料，不将修复后的手动发布冒充自然运行成功。

完整回归：60/60 全部通过，日志见 full-regression.txt。修复发布与线上验收进行中。

## 后台验收

- Google Search Console：URL prefix 属性 https://daily.maas.click/ 已确认所有者，robots 有效；sitemap.xml 已收到提交成功回执，但刷新后仍显示 Sitemap could not be read，不能记为抓取或索引成功。公开 Googlebot UA 请求为 HTTP 200，XML 含 8473 个合法本站 URL，见 sitemap-public-check.json。后续需复核 Google 实际读取结果。
- 百度：现有站点可管理，sitemap 当日及剩余配额均为 0；六个核心页面手动提交已填入，但安全验证码阻止完成，尚无成功回执。已请求用户手动验证，不能记为提交成功。
- Umami：MaaS Daily 后台显示实际页面访问；过去 24 小时观察到 5 visitors、10 visits、26 views。使用明确 QA campaign 的真实页面操作后，Events 后台收到 copy 1 次、model_click 1 次。自定义事件链路已验证；该 QA 流量与自然访问样本区分。后台账号、邮箱及凭据不归档。

## 仍需后续条件

下一次自然定时运行需独立验收；本次手动恢复不能代替自然调度成功证明。对象存储正式迁移仍等待可用桶，现阶段仅本地演练。百度验证码和 Google 抓取状态未完成。
