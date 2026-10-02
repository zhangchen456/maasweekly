# 搜索平台与统计核对

2026-10-02：当前环境没有 chrome-devtools 连接工具；使用现有浏览器控制接口读取会话，30 秒超时并重置。没有读取到 Search Console、百度或 Umami Cloud 账号状态，不能将此推断成用户未登录。

生产页面、验证标签、robots、sitemap 和埋点兼容性继续独立检查。已知百度 meta 验证值已上线；平台验证和链接提交仍需可用后台会话。Google TXT/meta 验证值尚未提供。不发送密码或私钥。

网站侧 6 项检查全部通过：canonical、百度验证标签唯一、首页单表三 Tab、robots、sitemap 和 models/pricing/agent 入口。证据为 public-site-check.json/txt。账号内验证/提交/真实看板核对仍等待可用浏览器会话。
