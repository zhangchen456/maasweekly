# 搜索增长首批优化（2026-10-08）

本轮针对已有搜索展示但没有点击的入口改进摘要与承接内容。Search Console 的站点资源已可在现有登录会话读取，不再沿用10月1日“尚未获得会话”的历史状态。

## 诊断与范围

Search Console 当时选择 Web、3 months，最后更新为25小时前：670 impressions、0 clicks；查询只列7条，不能将匿名查询或特定site搜索当作全部真实需求。页面报告前10条中/models/有283展示、/en/models/22展示、/en/pricing/16展示，均0点击。概览2361 indexed、1369 not indexed；未在本轮把所有未索引原因判定为故障。数据尚少，没有据此确认排名稳定、商业转化或关键词搜索量。

已有canonical、robots、静态模型正文与中英文页。新发现compare没有进入sitemap；优先修复有效入口遗漏。未批量生成模型比较文章或删除历史档案。

## 实现

- 模型目录标题明确DeepSeek、GPT、Claude、Gemini，摘要展示计费项、官方证据与真实dataThrough；价格工作台标题明确价格对比和Token费用计算器。
- 三篇中英文完整静态指南：Token费用、缓存计费、跨平台报价比较。例子是教学假设，不写死实时牌价；读者进入实际模型页核对条件与来源。
- 指南目录和文章加入sitemap；compare及en/compare加入sitemap。无伪造lastmod。新指南有独立canonical、双向hreflang和真实翻译。
- Article与BreadcrumbList标记对应可见正文、作者和固定实际修订日期，不以每天构建日期伪装内容更新。
- 首页页脚、价格工作台、模型目录及跨平台页可抓取指南入口；指南链接回工作台、模型报价、数据方法与官方缓存文档。

方法参考：[Google有用内容](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)、[站点地图](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)、[Article](https://developers.google.com/search/docs/appearance/structured-data/article)。这些优化不保证排名或新增流量。

## 推广准备

准备了可审阅的[分发草稿](distribution-drafts.md)。尚未发布外部帖子、私信或邮件。先以具体问题和可复算示例吸引读者进入对应指南，不将每日原始diff大量改写成引流文章。

效果判断：Google展示/点击与具体落地页为搜索结果；Umami自然搜索及价格/模型访问为到站行为。两个统计口径不混用。建议人工在7–14天后查看新指南发现与抓取、模型目录点击、新出现的非site查询；不自动新增监控。

## 验证与发布

本地最终构建52451页、sitemap19216条；SEO与中英文专项通过。真实浏览器390px中英文指南正文可读，scrollWidth375，无横向溢出；静态本地预览不提供账号API，未把账号保存错误记为生产故障或账号验收通过。标准发布70组门禁通过、0失败，线上四入口成功；线上12页面、sitemap19216条、百度验证与robots通过，真实浏览器中英文390px无横向溢出。首轮中文专项通过，后续中英文回归发现新指南需要双语sitemap；已补齐实际英文译本，保留严格回归规则。

最终提交680b2a4d3bb0e814fd4d94fd717f9428e471ab32，release rl_680b2a4d3b_22c3472abbdf。[发布流水线](https://github.com/zhangchen456/maasweekly/actions/runs/37750648224)成功。公开数据版本不变。两个mock worker重启加载最终版本，五个相关服务/调度active。证据见ci-success.json、release-summary.txt、validation-online.json、ui-online.json与runtime-online.json。

本轮更新了站点地图文件，未完成Google控制台的手动重新提交状态核对；资源本身已有收录和展示，新页面是否被搜索引擎抓取、是否增加点击需后续实际报告验证。未声称新增指南已经收录。
