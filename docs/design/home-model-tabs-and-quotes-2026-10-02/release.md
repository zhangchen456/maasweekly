# 发布与线上验收

2026-10-02 20:17（Asia/Shanghai）已上线：https://daily.maas.click/?lang=zh。

产品实现提交：`338f23ca070aa8cba5e8f8e87a15a447e56c6b77`；生产提交：`f3e2da7bc97e4091a684353640cba1b26ee808d6`。

生产 release：`rl_f3e2da7bc9_a032da03d915`；公开数据版本：`ds_a032da03d915eac53cd75f6fa93c5fd5cb5b4b3bdb856d546cce16d12ab45ad2`；数据截至 2026-10-02。最终管理输入：`in_da46d6315a42c20da6d37ed63ea68d0e690c1114eb7ad964a76df44a344bb051`。

## 回归与发布

标准工作流：[36987539497](https://github.com/zhangchen456/maasweekly/actions/runs/36987539497)，第二次执行成功。完整回归 **54 组通过、0 组失败**，随后完成 release 构建、离线校验、蓝绿激活与公网冒烟。

首次执行 53 组通过、1 组 REST 回归失败；发布门禁阻止了生产激活。重新编译后的本地 REST 68 项全部通过，连续 20 次重跑亦通过。首次 CI 只保留失败测试的末尾摘要，没有失败断言，具体原因未确定；第二次全量 CI 未复现。首次日志和复验结果保留，不将首次失败删改为成功。

四入口线上验收通过：REST status / changes、MCP initialize / 五工具 / 实际 changes 调用、两个 RSS 的 Content-Type / ETag / 304、Skill manifest / install.sh。REST 与 MCP 数据版本和服务器 current metadata 一致。详见 `ci-job-final.txt`、`ci-final.json` 和 `ci-artifacts-final/`。

## 线上浏览器验收

`online-browser.json`：5 个场景全部通过，含中文 1440 / 390、英文 1440 / 390、无 JavaScript。

- 一个实际表格，三个水平 Tab，旗舰 / 性价比 / 编程分别 8 / 8 / 2 个型号。
- 全部 18 个型号均有输入和输出价格，没有待核验占位；18 个型号详情链接均返回 200。
- 人民币 / 美元切换及自定义汇率在切换 Tab 后保留；非法汇率回退到上次有效值。
- 方向键、Home、End 与 ARIA 状态正确；页面无水平溢出；手机宽表可横向滚动。
- Google 优惠截止日期、DeepSeek UTC 条件可查看；中文页面没有客户端异常。
- 无 JavaScript 时单表展示全部 18 行。

线上截图：`online-zh-1440.png`、`online-zh-390.png`；最终画面已人工查看。

## 回滚与留存

服务器 previous：`rl_e8388dbcd5_0da7f0c0f2bc`，原数据版本 `ds_0da7f0c0f2bcd5df62281a262539b65a1742e3fbd710a14724359b58675c1b13`。本次未执行回滚；若后续需要，按既有生产 release 回滚流程处理。前后只读状态见 `production-before.txt` / `production-after.txt`。

原始快照、证据、事实版本、管理输入与正式采集运行保留。此次验收的日志和截图存于本目录；最终存档提交只包含验收资料，不改变生产代码和数据。
