# Logo 透明底与接入页文案修正

2026-10-02。用户反馈浏览器侧栏图标带白底，要求透明PNG；用户确认Codex已验证，要求移除客户端验证描述。

保留M字形与绿色信号点；用内置imagegen background-extraction编辑既有512px参考图，得到真实RGBA透明图。主文件 `site/public/brand/icon-transparent.png`；由该图导出16/32/48px PNG、透明ICO、180px touch及192/512px通用图标。页面以PNG为favicon，资源版本 `transparent-3`；SVG备用移除背景矩形。maskable专用图保留原有安全背景，它不作为浏览器favicon。

移除/agent/的整个客户端验证状态块、Codex配置下方的旧待验收文案及changelog中的过时阻断说明；保留Codex TOML与其他接入配置。pending列表移除Codex，不编造未提供的客户端版本和验证日期。历史任务档案保留原阶段事实。

生成工具：内置 `image_gen`，transparent_background=true。最终提示词：

> Use case: background-extraction. Edit target is the provided MaaS Daily icon. Remove ONLY the entire off-white background to true transparent alpha, delivering a square PNG. Preserve exactly the original dark forest green M silhouette, stroke geometry, rounded caps, position, size, proportions, and the lower-right teal signal dot with pale green center and translucent ring. No redesign, no text, no new shapes, no shadow, no white plate or white halo. Maintain smooth clean antialiased edges, transparent empty pixels everywhere outside the M and signal indicator. This is the production browser favicon master; high fidelity to the input is essential.

验收记录：站点构建、现有access-pages回归、桌面1440px/移动390px真实Chromium与PNG/ICO alpha检查。正式发布采用现有全量回归、exact-SHA蓝绿及四入口门禁；结果见本目录随后归档的release记录。
