> 2026-09-30 22:18 更新：用户已提供 website ID，当前配置已启用并完成生产发布；下文的关闭状态描述属于初次交付。详见 [生产验收记录](./task-08-lightweight-production-2026-09-30.md)。

# Task 08 轻量一期：代码交付与启用

初次代码交付已接入 Umami Cloud 的可关闭适配器，账号由用户注册。`site/src/config/analytics.json` 保持 `enabled: false` 和空 `websiteId`。关闭时 HTML 不加载埋点脚本；本次不发布未配置的网站，也不安装 Umami 自托管服务。

## 注册与启用

1. 在 Umami Cloud 注册账号，添加 `daily.maas.click` 网站，复制 Tracking Code 中公开的 `data-website-id`。不需要提交密码、API key 或其他 secret。
2. 将该 UUID 填入 `site/src/config/analytics.json`，设置 `enabled: true`。无效 ID 会阻止构建，避免发布错误配置。
3. 按现有构建、验收和发布流程发布。仅 canonical origin `https://daily.maas.click` 加载 Cloud tracker；本地和预览地址不采集。
4. 进入该网站的 Cloud 原生看板，查看访问量、访客、来源、页面、设备、国家和 Events。时间范围使用原生看板；本期不新增 `/admin/analytics`。
5. 用真实浏览器访问首页、模型页，点击模型与外链，成功复制一次；在看板核对 pageviews 和下述事件。检查正常导航、刷新、复制功能，以及浏览器网络请求与 referrer/UTM。记录发布 commit、workflow run、RID 和 Cloud 收到的数据后，才能宣布上线验收通过。

## 事件合同

Pageviews 由 Umami 原生 tracker 负责；适配器只过滤，不额外发送第二个 pageview。同一文档的查询筛选不重复计数；刷新是新的访问。自定义事件只有：

| 事件 | 触发 | 属性 |
| --- | --- | --- |
| `model_click` | 模型详情链接或带规范身份的模型筛选按钮 | `page_type`, `model_id` |
| `outbound_click` | HTTP(S) 外站链接，包括中键打开 | `page_type`, `target_domain` |
| `copy` | clipboard 写入成功 | `page_type`, `kind`（content/url/brief） |

模型身份沿用现有 canonical `model_id`。复制失败不发事件；不发送复制文本、外链完整 URL、任意事件属性、账号身份。查询参数仅保留经过格式限制的 `utm_source/utm_medium/utm_campaign`；hash 和其他查询参数丢弃。外部 referrer 保留 origin，内部保留 origin/path。页面标题使用页面类型。适配器不生成 visitor/session ID、不设置 cookie，访客/会话口径由 Cloud 提供。

浏览器 DNT 或 `localStorage.setItem('umami.disabled', '1')` 会关闭采集；恢复时使用 `localStorage.removeItem('umami.disabled')` 并刷新。浏览器拦截器、禁用 JS、网络失败会导致漏报；Cloud 的 Bot 处理和指标口径应结合真实账号验证，不把 PV 直接宣称为精确真人数。脚本失败不阻止产品导航或复制。

## 验证与边界

静态站点完整构建通过（18,599 页）。埋点与复制交互测试覆盖默认关闭、域名限制、配置校验、pageview 去重、刷新、动态模型筛选、外链、中键、成功/失败复制、属性清洗、DNT 和 provider 异常。原有 analytics foundation 94 项检查通过；埋点与 agent 复制交互 14 项通过，changes 23 项、model detail 14 项及 pricing 校验通过。默认关闭和启用 fixture 的构建均已验证，fixture 构建目录已删除，配置恢复为关闭。

Cloud 账号尚未创建，因此实际 Cloud 收数、原生看板、配额及生产发布验收仍待启用后完成。初次检查获取 Cloud SDK 返回 HTTP 403；上线阶段已重新获取成功，并验证真实 SDK 与生产浏览器请求，见生产验收记录。具体套餐配额、保留期和导出权限以用户账号为准。

此前获批准安装的 PostgreSQL 前置依赖仍保留；没有创建 analytics 应用数据库、部署 Umami runtime 或启用其服务。本期未继续部署自托管方案；如需清理此前依赖，另行检查使用情况后处理。

参考：[Umami tracker configuration](https://docs.umami.is/docs/tracker-configuration)、[Cloud](https://docs.umami.is/docs/cloud)、[events](https://docs.umami.is/docs/track-events)。
