# MaaS Daily · Price Pulse M

连续折线构成 M，青绿终点表示最新观察数据。终点细化为中心亮点、低透明度细环和四分之一弧刻度；悬停外圈扩散、刻度扫描一次。SVG 为透明背景；字标使用自绘路径，不依赖字体。

- `logo.svg`：完整静态字标。
- `logo-animated.svg`：入场描线与悬停圆点动效。
- `mark.svg` / `mark-animated.svg`：独立图标。
- `preview.html`：交互预览，包括反白、小尺寸和页头应用。
- `generate.py`：资产生成源，修改后用 Python 3 执行。

动效不无限循环，支持 prefers-reduced-motion。需要悬停反馈时将 SVG 内联到页面；外部 img 引用不保证触发内部 hover。暗色应用通过内联 SVG 的 color 覆盖墨色，保留青绿终点。

已通过 SVG XML 解析和桌面浏览器视觉检查。

## 站点接入

`site/src/components/BrandLogo.astro` 为中英文共用页头组件，使用继承颜色适配深浅主题，保留描线、探针扫过和减少动态效果支持。链接有 MaaS Daily 无障碍名称。

`site/public/brand/` 保存矢量下载版本、1200×630 分享图和 512px maskable 主屏图标。站点根目录提供 SVG、ICO、16/32px PNG favicon、180px Apple Touch Icon、192/512px Android 图标及 site.webmanifest。分享元数据由共用 Layout 输出。

图标经 app-logo-assets 的 export_app_logo_assets.py 从透明 mark 栅格生成，以 #f3f2ed 为底色和 0.7 的安全比例，再导出浏览器/主屏所需尺寸。16/32px favicon 直接由带底色的 favicon.svg 栅格化；favicon 链接带版本参数，避免旧图标缓存。

这是网站图标接入，没有添加 Service Worker 或离线功能。
