# 自然定时运行失败与恢复验收

自然运行：37080874994（2026-10-03，北京时间08:09触发；原计划05:00，调度实际延迟）。采集、结构化数据、导出和引用校验均成功；发布完整回归59/60，runtime历史首次加载测试偶发收到 failed。生产门禁拒绝发布，保留原运行版本。

原因：dataset-worker发送done/error后关闭消息端口，父进程通过setImmediate处理消息，exit事件可能先完成失败结算。修复让Worker等待终止消息确认，父进程仍负责超时、取消和最终terminate。

新增回归在收到done/error后延迟50ms，要求Worker保持存活；对旧行为确定性失败（before-fix-reproduction.txt），修复后9项runtime回归通过（runtime-regression.txt）。failure-artifacts保留实际自然运行失败资料，不将修复后的手动发布冒充自然运行成功。

完整回归：60/60 全部通过，日志见 full-regression.txt。修复发布与线上验收已完成。

## 后台验收

- Google Search Console：URL prefix 属性 https://daily.maas.click/ 已确认所有者，robots 有效；sitemap.xml 已收到提交成功回执，但刷新后仍显示 Sitemap could not be read，不能记为抓取或索引成功。公开 Googlebot UA 请求为 HTTP 200，XML 含 8473 个合法本站 URL，见 sitemap-public-check.json。后续需复核 Google 实际读取结果。
- 百度：现有站点可管理，sitemap 当日及剩余配额均为 0；六个核心页面手动提交已填入；用户随后确认已完成验证码提交。只读复核显示验证码弹窗消失、输入框清空；提交成功提示已不在当前页面，数据反馈趋势截至昨天（10 月 2 日），尚未展示今天接收数量。验证码阻塞已解除；6 个链接的接收数量及收录仍待后台统计确认，不重复提交。
- Umami：MaaS Daily 后台显示实际页面访问；过去 24 小时观察到 5 visitors、10 visits、26 views。使用明确 QA campaign 的真实页面操作后，Events 后台收到 copy 1 次、model_click 1 次。自定义事件链路已验证；该 QA 流量与自然访问样本区分。后台账号、邮箱及凭据不归档。

## 仍需后续条件

下一次自然定时运行需独立验收；本次手动恢复不能代替自然调度成功证明。对象存储正式迁移仍等待可用桶，现阶段仅本地演练。百度当日接收统计和 Google 抓取状态待确认。

本次导出来源状态为 ok=45 / failing=10 / unknown=13，明细见 source-state.json；没有将缺失或旧成功时间改写为今天。采集成功不等同于所有来源健康。

Sitemap 日志只读排查：生产 nginx access.log 在 10 月 3 日记录 200×8、301×3、502×1；非成功响应时间分别为北京时间 00:40:51 和 07:12:02，早于本次后台核验。UA 含 Googlebot 的 200×1 可能包含本次 QA 请求，未验证真实机器人身份或请求 Host，不能据此确认 Google 已抓取，也不能把历史 502 当作此次失败原因。未归档 IP、UA 或私人请求数据。

## 最终发布与验收

- 修复 commit：9c21f5fee5e11d272733eccf73e86ba41768d9ca。
- CI：[37090240736](https://github.com/zhangchen456/maasweekly/actions/runs/37090240736)，success，60/60；原始构建日志见 final-ci-artifact。
- 生产 current：rl_9c21f5fee5_12fdc567c7d3；previous：rl_45b0f13b19_7ce1e40d78d2。
- Dataset：ds_12fdc567c7d3e70fd11f64bd2c28fe27a56c40744950e9ab2185e4ebb4723bf5，dataThrough：2026-10-03。
- CI 与独立四入口验收全部通过，见 final-ci.json、production-status.txt、online-verify.txt。
- 隔离工作树只发布本次代码与验收文件，原工作区其他任务的未提交修改保留。

## 剩余任务顺序

1. 下一次自然定时运行：验证采集、构建、发布和告警恢复连续成功；此次自然采集成功、发布失败后已修复恢复，仍缺完整自然成功样本。
2. 来源真实恢复：按 source-state.json 继续追踪失败与未知来源，不用手动刷新时间制造成功。
3. 搜索平台：百度验证码已由用户完成，等待当日接收统计确认；Google sitemap 需再次出现真实成功读取/索引状态，当前未通过。
4. 长期统计：Umami 浏览及两个事件已完成链路验收，持续流量样本仍需积累。
5. 对象存储：等待可用桶，再推进真实迁移；已有本地演练。
