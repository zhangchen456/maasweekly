# SEO 搜索平台接入与复盘

站点：https://daily.maas.click。站点地图：https://daily.maas.click/sitemap.xml。

## Google Search Console

1. 登录 https://search.google.com/search-console ，选择已有站点；不存在时添加资源。
2. 有 DNS 权限时选择网域资源 `daily.maas.click`，把平台实际提供的 TXT 验证值添加到该子域对应的 DNS 记录。不要使用示例值或删除其他记录。也可以选择网址前缀资源 `https://daily.maas.click/`，按平台给出的 HTML 文件或 meta 标签验证。
3. 验证成功后，在“站点地图”提交 `sitemap.xml`。通过“网址检查”查看首页、`/models/`、`/pricing/` 和五个首批模型页；核对抓取页面正文、Google 选择的 canonical 和索引状态。
4. 若模型页显示未收录，先看平台具体原因，检查正文、响应及 canonical，避免批量反复申请索引。

本次没有获得可用的 Search Console 账号会话或 DNS 验证值；浏览器状态读取超时。没有提交站点地图，也没有确认搜索收录。后续可以提供平台生成的公开验证文件或 meta 标签，由当前聊天补入站点；账号密码不需要写入仓库。

## 国内搜索

主要面向国内用户时，在 https://ziyuan.baidu.com/ 添加并验证正式站点，按账号实际可用的链接提交入口操作。以平台当前能力为准，不承诺有 sitemap 提交权限，不猜测收录数量。没有现成会话或验证值时保留为待办。

## 复盘口径

Google Search Console 负责搜索展示、查询词、点击、点击率、落地页和索引报告；Umami Cloud 负责进入网站后的来源、访问页面和行为。两边统计口径不完全相同，不用浏览量推算搜索曝光或关键词排名。

现有埋点保留搜索引擎来源域名；查询参数和搜索词不会通过站内埋点采集。`model_click` 可检查模型入口点击，`outbound_click` 可检查官方来源点击，`copy` 可查看接入配置等复制行为。接入页访问或配置复制不能直接算作实际安装或订阅成功。本期没有增加重复 page_view，也没有新增事件。

第一批重点页面：

- `/model/deepseek:deepseek-v4-pro/`
- `/model/alibaba:qwen-plus/`
- `/model/alibaba:qwen3-coder-plus/`
- `/model/google:gemini-2.5-pro/`
- `/model/zhipu:glm-5.2/`

建议上线后第 7、14、28 天复盘：检查重点页是否收录、哪些查询有展示、哪些页面得到自然搜索点击、搜索访客是否进一步查询模型和证据。首次复盘先记录基线；观察有展示但点击较少的页面标题，以及有点击但无法解决问题的正文。没有数据时标记“尚无足够数据”，不生成虚构增长率。

后续选题优先：API 原币种与折算价格区别、缓存与批处理计费条件、月度价格变化。先用本站可核对的事实写完整答案，再准备开发者社区分发清单；外部发布需单独授权。
