# 首页与归档中的 Plus 周报

2026-10-03：首页最新深度周报、历史周报入口以及归档页的深度周报卡片标记 Plus；2026-05-03 为完整公开样例。原始每日/周度归档、公开变化和证据保持免费。

原 /weekly/{date}/ 与 /en/weekly/{date}/ 地址保留，静态页面仅含标题、日期、前三条头条预览及权限入口。游客登录后可继续开通；Free 在原文章中一键免费开启 Plus，随后直接加载全文；有效 Plus 直接加载。专业全文当前仍为中文。

构建集成 site/scripts/private-weekly.mjs 在最终构建阶段将全文模板从静态页面移出，存放到 data/private-weekly/{date}.html；任何非样例缺失模板都会中止构建。发布包单独包含此目录，处于 nginx 静态根之外。/api/pro/weekly/{date} 校验登录与当前 Plus 权益，响应 private/no-store，记录 weekly_read。匿名 REST/MCP 的周报对象仅包含发现信息，其分析字段置空；RSS仍只返回标题摘要与原文章链接。内部版本化数据仍保留原始数据，不直接对外提供文件下载。

/pro/继续作为个人简报、范围与凭证管理入口。公测不收费，无自动邮件订阅。

验收：22期受保护中英文静态页面均无全文模板/分析正文，公开样例保留全文；专业权益与 MCP 23/23 测试通过。浏览器验证游客摘要、Free文章内开通和Plus全文、首页Plus标识。截图与日志位于 docs/product/subscription-v1/acceptance/weekly-*、home-plus-cards.jpg。本地服务重启后 tester@example.test 仍为Free供用户验证，free@example.test 已用于自动验收开通。

生产未部署。发布前需清除旧版静态周报/CDN缓存，并通知匿名周报接口调用方：周报分析正文已迁移到专业鉴权接口。
