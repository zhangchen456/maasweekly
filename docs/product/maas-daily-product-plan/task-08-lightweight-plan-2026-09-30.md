# Task 08 轻量化方案：第一阶段埋点与看板

日期：2026-09-30。状态：方案建议，未实施。当前 owner 要求轻量化、机器资源有限，第一阶段只做数据埋点和看板；本方案替代原 Task 08 大而全的一期范围，不把历史冻结的 self-hosted 决策自动视为仍适用。

## 结论

推荐 Umami Cloud 承担采集、存储和看板；maasweekly 只接入薄埋点。第一阶段不在生产服务器部署 Umami、构建 Next 应用、建立自己的 Analytics 数据层或实现 `/admin/analytics`。

```text
maasweekly 静态页面
  → Umami tracker（异步、失败不阻塞页面）
  → Umami Cloud
  → 登录 Umami 自带看板
```

这会把新增 Analytics 应用和数据库的运行负担从当前生产机器移走。网站新增成本集中在浏览器脚本和少量请求；不承诺实测前的脚本大小、内存或性能数值。

主要取舍：数据在第三方托管，依赖外部采集域名的可达性和套餐限制。Umami 官方说明 Cloud 服务器在 US/EU，支持数据导出。如果数据必须留在自有服务器，则保留自托管选项，但要单独实测资源，不能将现有约 1 GiB available memory 视作足够的证明。

## 当前生产事实

已有约 2 cores / 3.4 GiB RAM，2026-09-30 prerequisite 安装后 MemAvailable 1037 MiB，无 swap，磁盘剩余约 19 GiB。

用户批准的 prerequisite 包已真实执行：pnpm 12.3.4、PostgreSQL 18.6 已安装；Node 仍为 v22.22.3，路径仍为 `/opt/node-v22.22.3/bin/node`。PG cluster 18/main 在 5432 online，只监听 loopback（127.0.0.1 / 127.0.1.1），应用 DB `maas_analytics` 和 role `maas_umami` 均不存在。

Umami app/service/user/env/nginx block 未创建。站点路由跟随重定向均返回 200；Feed、Skill、REST、MCP initialize 正常。生产 RID 仍为 `rl_f684fc186c_1925cbc6adaf`，datasetVersion 仍为 `ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207`，dataThrough 为 2026-09-30。

本次安装日志保留在 `/root/maasweekly-t08-prerequisites-b84d5e8ff/prerequisite-install.log`，SHA256 `d4bbcfee91aa0bde529ef4c1c733b0b45038844a8ee272b4aae1460e955263ef`。上传脚本核对了 repository commit `b84d5e8ff17337aaf77f87bbfce930862c9e9704` 对应文件哈希。

受限 inventory 的 `postgres_path=NOT_INSTALLED` 是旧 PATH 探针误报；本报告以版本目录、dpkg、pg_lsclusters 和实际 SQL 为准。

本次方案调整不停止或卸载 PostgreSQL、不清理服务器记录。选择 Cloud 后，确认 PostgreSQL 无其他使用方，再单独处理停用、禁用开机启动及清理；该步骤能回收其常驻资源。pnpm 已安装本身不代表一个常驻服务。

## 第一阶段只做这些

| 项目 | 第一阶段交付 |
| --- | --- |
| 基础访问 | PV、匿名访客估算、访问趋势、页面、来源、设备/国家；sessions 等以所选套餐实际支持为准 |
| 核心业务事件 | `model_click`、`outbound_click`、`copy`，页面访问用 provider 自身 pageview，不重复发同名 custom event |
| 页面语义 | 真实路由对应的 page_type；模型事件使用 T07 canonical model_id，按需要带 developer_id/platform_id |
| 来源 | 保留 referrer 的来源域名和允许的 UTM 字段；优先观察 search、AI、GitHub 等实际可见来源 |
| 看板 | Umami 原生登录后台：流量趋势、来源、热门页面、核心事件；优先 7D/30D，90D 取决于实际保留期 |

不另建 visitor_id/session_id，不增加长期本地标识。page_type 不为每个 pageview 额外制造一个 custom event；用页面路径做基本看板分类，必要时在业务事件中带 page_type。

事件字段白名单按事件收敛。例如 model_click 只带 model_id 和必要的来源页语义，outbound_click 只带目标域名/用途，不收集完整外链 query 或文本；copy 记录复制功能类型，不记录复制内容。过滤 URL/query/referrer 中的非必要内容，只保留明确允许的 UTM。开发/preview 域名不采集；管理员访问提供排除方式。

使用 provider 匿名统计口径，不将 UV 宣称为精确人数，不承诺识别所有 bot，不承诺跨时间段可靠识别 New/Returning。referrer 缺失的 AI 访问无法凭空还原，不把 direct 自动归为 AI。

页面只有一个 pageview 上报入口。当前 Astro 静态页面用标准 pageview tracking；若未来加入客户端路由，再验证路由切换去重。业务事件监听不覆盖现有点击、复制和导航行为，复制成功才上报。采集服务被阻断/超时/不可达时，主站仍正常工作，不增加服务器代理、持久重试队列或 collector fallback。

暂不采集 scroll_depth、每次 content_view、session replay、heatmap、performance 等；不做自定义 session 管理、统一原始事件仓库、数据 manifest、实时 aggregation 或定时 API 拉取。这些都不是第一阶段完成条件。

## Cloud 上线前必须核实的少量信息

1. Owner 的 Cloud 账号及 website 配置；公开 website ID 可以用于 tracker，登录凭证/API key 不进入浏览器或仓库。
2. 账号当时的事件额度、保留期、事件属性/看板功能和导出/API 权限。官方明确有免费 Hobby 方案，但本次 pricing 页面未提供可读明细，不填写未经核实的数值。
3. 来自主要访客地域的脚本和 collect 可达性。生产服务器 curl 成功不等于所有访客浏览器可达；若不可接受，再决定是否改自托管。
4. Owner 接受统计数据交由第三方托管。此处是部署选择的实质取舍，不因此前已装 PostgreSQL 而默认必须继续自托管。

Cloud 用量按 hits、自定义事件及保存的属性计量，不能简单用 PV 推算。先减少属性和事件；若免费方案不足，比较实际付费成本与自托管资源成本再决定，不自动升级订阅。

## 执行顺序与 Done

先确认 provider/account/额度，然后接入一个 tracker 和三个事件，再配置原生看板，最后部署并做真实浏览器验证。沿用已有主站 release/rollback，不建立新的发布流水线。tracker 使用开关，可通过配置关闭并回滚已有 release。

验收：首次访问、刷新、导航各只有预期的一次 pageview；model_click 具有正确 canonical model_id；outbound_click/copy 各按真实动作上报一次；带测试 UTM 的访问可在看板对应；正常非敏感 referrer 可见；事件不含复制正文或未允许 query；7D/30D 看板可查看真实数据；采集失败时页面和复制/跳转照常工作。原站、Feed、Skill、REST/MCP 保持健康。

测试访问本身会形成 analytics 数据，需要标记测试 UTM/事件类型或可用排除规则，不用反复刷新制造虚假流量。无需等积累 30 天才验收功能，长周期趋势待真实数据积累。

## 后续 SEO/GEO：按实际需要逐项增加

第二阶段用 Google Search Console / Bing Webmaster 原生看板看曝光、点击、query/page；主站补 sitemap/robots/canonical 等必要 SEO 工作。暂不开发 GSC/Bing 同步服务；只有手动看板不能回答实际问题时才做周期导出或自动同步。

GEO 先看真实 AI referral 来源及 landing page。之后基于官方 UA registry 增加 AI crawler 日志日级统计，优先轻量批处理，避免全量导入数据库。referral 和 crawler 是两个指标，不混算。

统一 `/admin/analytics`、每日汇总数据层和 Citation Monitor 移到需求确实出现以后。需要联合分析时，先用少量聚合导出，不复制 provider 全量事件，不迁移到 public API/data/public/v1。Cloud API/export 权限与历史迁移完整性到该阶段单独验证。

## 资料来源

- [Umami Cloud overview](https://docs.umami.is/docs/cloud)：托管能力。
- [Cloud FAQ](https://docs.umami.is/docs/cloud/faq)：免费 Hobby、用量计量、服务器区域、导出。
- [Tracker configuration](https://docs.umami.is/docs/tracker-configuration)：域名限制、pageview 初始化、发送前过滤。
- [Track events](https://docs.umami.is/docs/track-events)：事件及属性看板。
- [API overview](https://docs.umami.is/docs/api)：Cloud 与自托管 API，后续功能需核实套餐权限。

用户已批准轻量一期实施。未提交的 self-hosted runner/资源限制草稿已撤销；已批准并安装的 PostgreSQL 前置依赖保留，当前不安装或启动 Umami 自托管服务。Cloud 账号由用户注册；代码默认关闭，获得真实 website ID 后再启用和发布。
