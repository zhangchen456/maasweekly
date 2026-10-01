# Logo 生产验收

2026-10-01 16:42:39（Asia/Shanghai）激活 `rl_97afdbdf80_6fd3cc403bf9`，代码提交 `97afdbdf800be5d582fe8dcf7e91ca654b18c282`，main 已同步。上一 release `rl_f5fb68b323_6fd3cc403bf9` 保留用于回滚。

标准 GitHub Actions 发布 [36837088164](https://github.com/zhangchen456/maasweekly/actions/runs/36837088164) 成功：45 组门禁通过、0 失败，manifest 校验、incoming 上传、蓝绿激活和 REST/MCP/RSS/Skill 四入口验收通过。manifest 包含 24,348 文件；数据版本仍为 `ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`。部署日志保留于 `dist-release/validation-logo-97afdbdf80/github-deploy.log`。

本地真实浏览器检查：英文页头深浅主题显示正常；中文 390×844 手机布局中 Logo、语言切换、主题按钮和换行导航可见，已恢复默认视口并停止临时 dev 服务。所有 PNG/ICO 尺寸及 manifest 图标路径已检查，SVG XML 解析通过。

公网中文首页、英文首页和英文模型目录均包含新 brand-logo、Apple Touch Icon 与绝对分享图片元数据。12 个线上资产（SVG/ICO/16/32px favicon、Apple、Android、maskable、manifest、分享图及 Logo 下载）返回 200，内容与本地文件逐字节相同；实际生产 current 已确认是新 RID。

生产浏览器导航和新 tab 创建均超时，未取得生产截图；本地浏览器验收与公网资产核对不代称生产交互验收。未在真实 iOS/Android 设备执行添加到主屏操作，也未向社交平台提交链接检查缓存刷新。

图标导出使用 app-logo-assets 技能的确定性导出脚本，来源保持批准的 SVG。SVG 页头支持减少动态效果，favicon 链接带 price-pulse-2 版本参数。没有添加离线或 Service Worker 功能。
