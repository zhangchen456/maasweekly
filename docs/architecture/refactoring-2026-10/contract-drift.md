# AR-01 契约核对与当前架构

核对日期：2026-10-01。输入代码：`b29035eef`；输入数据：`ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`。下述生产状态来自仓库验收记录，不是本轮实时服务器探针。

## 契约偏差处置

| 项目 | 原描述 / 实际行为 | 依据与处置 |
| --- | --- | --- |
| 模型目录 | public-api-v1 仍写不新增 `/models`；代码、OpenAPI 和浏览器刷新使用 `/api/v1/models` | 后续 T07-4B.1 与多语言验收明确增加该端点；更新当前 API 契约，旧阶段任务保留历史原意 |
| 发布路径 | README 仍写 GitHub Pages/legacy rsync 与“待部署” | 现有工作流、activate、后续生产验收均采用 release；更新 README，旧 Pages 说明标历史 |
| MCP 发布状态 | 合同开头仍写本地完成、生产属 Task 06 | 更新状态并引用已有发布验收；协议工具/transport 行为不改 |
| providerId | 早期平台/开发者容易混用 | T07-5 已定义为 legacy public query namespace，维持模型 ID 与 filter，不从前缀推本体 |
| 正式周报 | `data/weekly` 导入后站点正式 collection 成为 exporter 的输入 | 当前如此记录；AR-03 核对差异并指定单一权威源，不在本任务直接移动内容 |
| 限流 | Node REST/MCP 各共享进程桶，Nginx 按 IP 另有限流 | 当前合同保持共享语义；AR-02 调整作用域时同步合同与代理链验收 |
| status 就绪 | `/api/v1/status` 无数据仍返回 200/空集合/错误状态 | 存活与就绪不可混淆；AR-08 记录 readiness，不用单纯 200 判 fresh |
| 热重载 | 每 30s 完整同步加载同一 release | AR-02 比较版本、隔离新旧版本加载；默认轮询当前仍是已确认行为 |
| 分页 | HMAC、固定 datasetVersion、参数重验、保留版本磁盘读取 | 与 query/versioning/identity 测试一致，迁移保持该语义 |
| 金额和 freshness | 原金额 Decimal 字符串、单位与条件；失败沿用 stale | Python 事实/公开投影与合同一致，本轮不改变价格比较口径 |
| Analytics | T08 初稿推荐自托管，后续 lightweight 明确 Cloud | 当前配置与 2026-09-30 真实请求验收为 Umami Cloud；不启动历史候选服务 |

没有尚需用户裁定的 v1 行为。跨平台 ontology、查询数据库与远端对象存储仍按需求/容量条件推进，不把候选模型关系直接公开。

## 组件和服务职责

| 组件/服务 | 输入 → 输出 | 状态与启动 | 发布及失败影响 |
| --- | --- | --- | --- |
| 通用信源抓取 | 配置 URL/上次快照 → 原始快照/diff | Python，daily/weekly Actions | 抓取失败应可见；旧事实保留 |
| 价格管线 | registry/网页 → facts/evidence/revisions/current/ledger | Python + Playwright/bs4，价格 runs | 单家失败沿用旧事实并标 stale；依赖站点路径待解耦 |
| 摘要/榜单/图片 | diff/价格事件/外部源 → 展示派生数据 | Python，各 workflow 步骤 | 可降级；不决定价格事实真实性 |
| public exporter | records、价格、周报、流状态、catalog → 版本化七集合 | Python，构建前/数据提交前 | 校验失败阻止候选，不影响当前线上 release |
| Astro | verified release、站点投影、正式内容 → 静态 HTML/RSS/Skill | Node build；运行期 Nginx | 默认无 SSR 服务；静态页面按统一 release 发布 |
| agent-api | 只读 public release → REST/MCP/country | Node 22；systemd blue/green | 127.0.0.1 8788/8789；内存 Dataset + 历史缓存 |
| Nginx | 静态目录、上游 include → 公网 TLS/路由/限流 | 同机反向代理 | activate 校验后切换，保存恢复步骤 |
| 发布工具 | 精确 Git SHA → immutable RID/manifest → activate | shell/Python、受限 SSH | flock、旧提交拒绝、候选检查、四入口验证已有 |
| Umami Cloud | 白名单页面/交互事件 → 原生统计 | 外部服务、页面可关闭适配器 | 不属于核心事实服务；失败不影响页面交互 |
| PostgreSQL 前置依赖 | 历史自托管方案安装记录 | 仓库记录保留，实时状态未复查 | 不表示当前核心查询依赖 DB，不能据此部署 Umami |

## 本轮测量口径

使用 Apple M1 Max/32 GiB、Node 22.22.3、Python 3.12.1。运行 1×真实数据与固定种子的 5×/10×合成样本：映射全部记录/证据/事实版本 ID 和链接，保持排序与 hash/bytes 校验，检查证据引用和完整分页。模型目录不扩展，因此只代表记录量增长，不代表信源/模型种类扩展。

本地 HTTP 并发 1/10/30，每组 3 轮、60 请求，能力采样使用大配额；真实低配额另记 200/200/429。记录启动/重载/历史加载、事件循环和 RSS。最终内存可能包括历史/低额度服务测试对象，不作为单实例稳态内存。

冻结本地预算：并发 10 列表 P95 ≤ 200 ms；事件循环 P99 ≤ 50 ms；同版本轮询业务集合解析 0 次；完整分页重复/缺失 0。生产内存、磁盘和恢复预算需实际服务器探针，未用开发机 32 GiB 冒充生产容量。

构建阶段成本由完整回归和后续 AR-05 标准 release 采集；冷依赖安装及生产打包不在没有干净输入/无网络条件下伪造数值。不能把本轮未执行的线上探针、冷安装或完整 release 报告为通过。
