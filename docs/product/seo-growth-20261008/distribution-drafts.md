# 可审阅分发草稿

未外部发布。渠道是匹配读者的候选，不代表已确认流量或有账号发布权限。每篇只选择一个合适渠道试发，根据实际讨论调整；不批量投递、刷链接或承诺最低价格。

## 首篇：掘金技术文章／公众号

标题：每百万Token报价，怎么变成一笔真实API账单？

正文草稿：

看API价格时，不能只看一列“每百万Token”。输入和输出通常分别计费，一段Agent任务还可能有多轮调用。

用一组假设数字手算：输入2元/百万Token，输出8元/百万Token。一轮输入1万、输出2000，成本是0.02+0.016=0.036元；相同任务运行1000次就是36元。这个例子不是模型报价。

实际预算还要把历史对话、工具结果、重试和缓存算进去。我们整理了公式与例子，并把模型原币种、计费条件和官方证据放在查询页，方便你用自己的用量复算。

阅读：https://daily.maas.click/guides/token-cost/?utm_source=juejin&utm_medium=referral&utm_campaign=cost_guides_20261008

若发公众号，将utm_source换成wechat，其余保持同一campaign。内容可扩展成完整教程，避免只贴链接。

## 第二篇：开发者社区的真实缓存问题

标题：缓存命中80%，API费用也一定少80%吗？

正文草稿：

不一定。先分清普通输入、缓存读取、写入和存储费用，再看usage里的缓存Token是否包含在总输入中。直接把所有输入套缓存读取价，或者把命中Token又当普通输入计一次，都会算错。

我们做了一篇有手算例子的说明，附Claude与Gemini官方文档，以及模型实际缓存报价查询入口。规则随供应商变化，费用要按自己使用的接口核对。

阅读：https://daily.maas.click/guides/prompt-caching/?utm_source=developer_community&utm_medium=referral&utm_campaign=cost_guides_20261008

只在与问题相关且社区允许分享时发布，不在无关讨论贴推广链接。

## 第三篇：英文技术文章或个人社交账号

Title: The cheapest input-token price is not always the cheapest API workload

Draft:

A provider with cheaper input and more expensive output may win on a long-input task and lose on a long-output task. Before comparing costs, align the upstream model, region, context tier, cache assumptions and realtime or batch mode.

We wrote a practical checklist and linked it to observed quotes with billing conditions and official evidence. It avoids a lowest-price ranking across incompatible offers.

Read: https://daily.maas.click/en/guides/compare-api-prices/?utm_source=technical_article&utm_medium=referral&utm_campaign=cost_guides_20261008

## 判断一次分发是否有用

UTM只标记候选分发渠道，不增加埋点或声称已经发出。发布后看进入对应指南的访问、继续查看模型与价格工作台的行为、相关讨论是否指出实际问题；不是单看首页浏览量。内部验收继续独立标记，不把验收访问算成推广成绩。
