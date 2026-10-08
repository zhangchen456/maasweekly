# T04 流量与内容使用分析

2026-10-04，已完成本地实现与隔离验收，仅本地，不部署、不改生产统计配置。

## 实施前盘点与实际口径

已读全局 ~/.codex/AGENTS.md、site/AGENTS.md、ops/README.md、T01–T03交付、统一合同及实际代码。保留所有已有工作区改动。

| 数据 | 已有与缺失 | T04处理 |
| --- | --- | --- |
| 网站 | site/src/config/analytics.json及public/analytics.js实际使用Umami Cloud，公开websiteId为4f0172a2-5aea-48cf-bb38-22eb86368fea；ops自托管为候选，未据此认为在用。无既有服务端统计查询器 | 服务端配置Cloud API key及endpoint；不从Chrome提取会话、不生成key、不改变追踪配置。缺凭据显示不可用 |
| 账号 | users无created；profile.created为首次资料建立，老账号首次使用可晚于注册 | 分别统计资料建立与真实新注册；migration 4仅在验证码验证事务新建users时记录注册时间，老账号时间未知，绝不回填profile时间 |
| 激活 | pro_beta_access.created且userId唯一；pro_events.beta_activated只在首次激活新增 | 激活人数用原表；不是付费转化 |
| 专业读取 | REST content_read/sample_read/report_read/weekly_read；失败不计；既有content_export仅看是否含format，MCP read/report未计 | 修正导出分类，仅有效markdown/csv为导出，样例单列且旧事件中可核实样例目标排除；补MCP成功业务事件。历史format异常、MCP遗漏及weekly_read公共/私有语义混合不能修复；完整采集起点为migration 4 |
| Agent | 公共REST/MCP诊断日志有界且可能关闭/丢弃，无账号绑定；pro_tokens.used是最近使用，非调用数；MCP weekly已有weekly_read | 新建按北京时间日、固定channel、HTTP status汇总，finish后每请求一次，无IP/URL/query/token/userId。HTTP成功不等于MCP工具成功，不称真实Agent人数。工具成功另用专业业务事件 |
| 周报 | 新briefing通过content_read，旧weekly_read按日期，个人report_read不是一期统一周报 | 按目标及账号去重；同一期至少两个不同北京日期读取为回访。新周报与历史日期入口分列；历史weekly_read存在混合语义 |
| 队列 | 历史注册时间未知、MCP读取遗漏、采集起点未知 | 注册后7天激活只用新注册且观察期完整；专业阅读第4周留存用完整采集起点之后的首个已记录专业读取，排除起点前已有读取者，不称终身首次阅读；观察[21天,28天)，满28天才能进分母；样本<5不展示百分比 |

日期为Asia/Shanghai，preset近7/28天含今天到查询时刻；custom from/to为真实YYYY-MM-DD日期且均包含，内部[start,end)结束截到now，最多366天。未来起点/非法重复参数拒绝。读取人数按userId，事件次数不去重；回访按北京日期去重，不把重试同日称回访。匿名sample读取不计专业读者。网页匿名访客与账号及请求汇总独立，无法还原阅读完成率、真实Agent人数、未采集历史或匿名访问身份。

Umami官方合同：[Cloud认证](https://docs.umami.is/docs/cloud/api-key)、[stats](https://docs.umami.is/docs/api-reference/get-website-stats)、[metrics](https://docs.umami.is/docs/api-reference/get-website-metrics)、[v2合同](https://v2.umami.is/docs/api/website-stats-api)。版本显式配置v3（默认，path/referrer为views）或v2（url/referrer为visitors），不猜测排行单位。最多20条；来源不作为全部流量分母；内测可能混入，不自动扣除。

## 交付与运行

入口`/admin/analytics/`，聚合API`/api/admin/analytics`，默认近7天，可切28天/自定义。沿用AdminLayout及鉴权清空事件，无私有静态数据或localStorage；迟到响应按generation丢弃。网站不可用时本地业务统计仍显示采集覆盖说明。真实Umami凭据未配置/未调用，本次网站验收为模拟返回值，不声称已取得线上流量。

修改文件：新增src/admin-analytics.ts、admin-umami.ts、tests/admin-analytics.test.ts；扩展account-store.ts的新建账号事务、admin-http.ts路由与异步后二次鉴权、server.ts响应完成采集、pro-http.ts导出分类、pro-mcp.ts成功工具读取事件和既有pro.test.ts事件断言。新增site/src/pages/admin/analytics/index.astro、lib/admin-analytics-client.ts，扩展AdminLayout/admin.css/page-models。API package.json接入统一test/test:compiled，浏览器脚本接入scripts/admin-analytics-browser-flow.py，沿用已有run-all-tests门禁。更新本文、development-order和统一admin-api-v1指标合同；没有修改生产配置，没有T05开发。

服务启动自动migration4，数据库备份沿用SQLite backup（不能只复制WAL主文件）。该迁移幂等、事务失败回滚、仅加法表/索引；注册时间仅由真实验证码验证新建用户事务写入，userId主键去重，失败不留账号/注册记录。未来部署才产生生产采集起点。回滚按现有应用发布流程保留新表，不DROP；旧应用不记录新增注册/API/MCP事件，重新升级后必须披露这段缺口，不猜测回填。

服务端私有环境配置：`MAAS_UMAMI_TOKEN`；可选`MAAS_UMAMI_ENDPOINT`（默认Cloud US/v1）、`MAAS_UMAMI_WEBSITE_ID`（默认既有公开ID）、`MAAS_UMAMI_VERSION=v3|v2`。无key显示不可用；不新增key、不读取Chrome secret、不修改生产Umami账号/追踪配置。官方v3.4.0源码确认path/referrer均为EVENT_COLUMNS并走pageview指标；v2则显式按其url/referrer访客合同显示单位。自托管候选不能冒充当前Cloud数据源。真实Cloud权限、schema版本和网络需后续在获准环境核验。

## 验收结果

| 检查 | 结果 |
| --- | --- |
| API `npm run build --prefix services/agent-api` | 最终通过，公共合同生成检查通过 |
| `npm run test:compiled --prefix services/agent-api` | 131/131通过（当时8项T04）；随后仅新增测试及周报零读者/外部查询上限完善，运行最终相关专项 |
| `node --test services/agent-api/dist/tests/admin-analytics.test.js services/agent-api/dist/tests/pro.test.js` | 最终22/22通过：11项T04与11项专业回归，固定时钟/北京边界/注册事务/历史未知/去重/跨日/成熟分母/观察期/样本不足/零读者/多版本/外部不可用/成功零值/v2/v3/请求渠道/迁移回滚/权限/异步撤权；MCP成功读取事件与非法format不冒充导出 |
| `npm run test:mcp:compiled --prefix services/agent-api` | 13/13通过，公共MCP回归 |
| `node services/agent-api/node_modules/typescript/bin/tsc --project site/tsconfig.page-models.json` | 通过，含T04客户端 |
| `npm run build --prefix site`，最终在site目录`npm exec -- astro build` | 通过，47457页；最终构建包含T04样式 |
| `python3 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser-t04-delivery` | 13流程通过、0页面错误；含T01/T02/T03完整闭环、T04近7/28天/自定义、真实SQLite读者及回访、Umami故障/null/最近成功/恢复、1440及390窄屏、注销后迟到响应清空、Free/Plus隔离 |
| 500账号/5万事件/20期周报本机聚合性能 | 5次82–93ms，中位90ms；内存SQLite、无网络和磁盘，不代表生产SLA |
| `git diff --check`、Python脚本语法 | 通过；脚本解析不产生项目pycache |

首次浏览器夹具的日期等待表达式使用了未定义arguments，已改为显式参数；重跑全部流程通过。一次命令工作目录误置site导致前面的编辑/API命令未运行，已在正确目录执行并验证，最终构建成功。不影响生产或既有数据。

最终证据保留：`/tmp/maas-admin-browser-t04-delivery/browser.json`、analytics-desktop.png、analytics-unavailable.png、analytics-mobile.png及原T01–T03截图/weekly-evidence.json；日志`/tmp/maas-t04-api.log`、maas-t04-targeted.log、maas-t04-mcp.log、maas-t04-site.log、maas-t04-site-final.log、maas-t04-browser.log，性能记录`/tmp/maas-t04-performance.json`。临时账号库/outbox/Chromium/API/本机代理由脚本销毁，未留下常驻服务；一次性benchmark源清理。演示需重跑上述脚本，截图及报告为隔离数据。

## 可用与限制

可从现有库复算：资料建立、公测激活、已有成功读取/导出、各期按账号去重读者和跨日回访；新出版但零读取的专业briefing也展示。补充后可采集真实新注册、公共与专业HTTP请求、专业MCP成功读取与工具次数；注册7天激活和专业第4周留存仅在成熟队列有足够样本后显示比例。所选范围早于migration4时明确partial，数字仅代表记录，不声称完整历史。页面首次上线通常队列为未成熟/分母0。

缺数据：历史注册时间、漏计的历史MCP读取、旧错误format的导出分类、公共诊断日志丢弃/关闭期间请求；匿名访客与个人身份关联、阅读完成率、真实Agent人数、付费转化、版本级历史读者。专业完整采集起点并不能恢复之前的终身首次读取。服务整体数据库不可写时无法保证失败计数保存。停机或旧版本运行期间采集有缺口，不能把migration时间当作永不间断的保证。

查询范围最多366天；外部3路并行，各4秒/128KiB，上限4并发范围及每15秒10次范围，成功缓存60秒/32范围，页面与来源20项、周报100项明确截断。缓存按结束分钟归并，website.asOf是实际成功查询时间，business.asOf是本地检查时间；最近成功为任意范围查询，不代表所选窗本次成功。多个API进程的限额独立，需考虑Umami总额度。API请求仅按日汇总，无法细分小时/请求链；不做匿名账号关联或自动排除内测。

本地业务SQL同步执行，首次读取队列计算需全历史按账号分组，周报回访最多100次有索引子查询；事件表尚无自动归档。本机5万条约90ms，百万级历史或慢磁盘会阻塞Node主线程，需先测量再设计后台物化/归档，本次不另建统计平台、不提前开发任务监控。未验证生产升级、Cloud真实凭据/权限/响应、真实网络耗时或生产大库性能。
