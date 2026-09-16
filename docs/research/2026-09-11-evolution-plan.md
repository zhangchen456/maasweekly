# MaaS Daily 演进计划：Agent 接入优先

日期：2026-09-11。状态：最终建议稿，可据此拆任务；本次只制定计划，不实施或发布。

## 1. 结论与目标

P0 建设「可引用、可查询的 MaaS 数据源」，交付 Skill、远程 MCP、RSS、REST API 四个真实可用入口，以及支撑它们的条目归档、证据、数据新鲜度和方法说明。P1 增强决策解释与模型关联；P2 做跨平台事件时间线与按场景对比。不转向泛 AI 新闻聚合。

P0 的成功不是四个入口图标上线，而是接入者可以完成以下闭环：

1. 问最近 7 天某平台发生了哪些变化，得到可引用的条目及明确时间范围。
2. 问某模型的输入／输出价格，得到原币种、单位、适用条件、观察时间及证据；过期数据明确标识。
3. 顺着返回的 ID 查询证据，能看到当时记录，不只跳转到可能已变化的官网。
4. 获取最新正式周报，并能通过 RSS 持续订阅。

默认采用匿名只读接入，不增加账户、API Key、计费或随机 Actor 统计。此处是本计划的产品选择，不是对既有用户协议的描述。现有抓取凭据仍只留在管线，不进入公开服务。

## 2. 三方建议的综合评估

| 方向 | 处理 | 理由与调整 |
| --- | --- | --- |
| WorkBuddy：条目永久链接 | P0 必做 | 必须先持久归档、固定身份和修订规则，不能只在滚动 JSON 上生成页面 |
| WorkBuddy：Agent 优先分发 | P0 核心 | 四个入口共用公开数据投影；远程 MCP 需要新增轻量运行服务 |
| WorkBuddy：可信度产品化 | P0 基础版 | 方法页、实际观察时间、失败与 stale 状态；完整健康度趋势放 P1 |
| WorkBuddy：为什么值得看 | P1；P0 仅保留已有摘要 | 改为「影响哪些用户、什么条件下有影响」，与事实分离；不能用 LLM 解释代替证据 |
| WorkBuddy：事件聚合 | P1 统一模型身份，P2 事件页 | 同模型在不同平台上线是独立事实，关联展示，不按 24 小时直接合并 |
| WorkBuddy：主题页 | P1 筛选，P2 主题落地页 | 来源类型不等于事件类型；pricing 页面变化不自动算调价 |
| WorkBuddy：多榜共识分 | 暂缓 | 先解决日期、覆盖、模型别名、harness 差异和重复评测，再考虑聚合；市场份额不混入能力分 |
| CC：错误包含恢复动作 | P0 采纳 | 统一错误码、requestId、可执行的恢复说明 |
| CC：共享缓存与条件轮询 | P0 采纳 | 适合每日更新；只对可缓存 REST GET / RSS 使用，不缓存 MCP POST |
| CC：安装器与机器文档 | P0 采纳简化版 | 完整包校验、显式目标目录、失败恢复；不照搬旧版本迁移负担 |
| CC：自编码 watermark 游标 | P2 有同步需求再做 | 当前不存在待重构的外部同步层；P0 只做绑定数据版本的查询分页 |
| CC：不开放匿名 API | 不采纳其理由 | 当前仓库未找到其所称账号凭证基线，且用户明确希望实现 AIHOT 式接入 |
| CC：AI 评分降噪 | 不作为事实门禁 | 分数无法证明价格和下线事实；采用证据等级与规则过滤 |
| CC：全文白名单 | 保留原则，不做全文服务 | P0 发布自有摘要与必要证据摘录，不新增第三方全文 RSS |
| 收藏、群推送、社交信源 | 不进本轮 | 缺少当前目标下的必要性；订阅入口已满足基础分发需求 |

### CC 文档中不能沿用的项目事实

`2026-09-11-aihot-analysis.md` 的「账号凭证体系、三轮验收 R01/R07、create/revise/withdraw 既有语义、T4、现成对外 SKILL」在当前项目代码、README 和 HANDOFF 中没有找到对应依据。价格模块明确迁移自追浪，文档可能混用了另一项目的背景；不能据此给 MaaS Daily 安排同步层重构。

游标可解码出 watermark，只能证明它携带了水位，不能仅凭公开响应确认服务端内部完全无状态。即使游标本身无状态，服务端仍需稳定排序、修订日志、快照边界、删除记录与保留策略。单个 watermark 也不能证明跨页快照不漏数。因此不采用「天然解决所有同步一致性问题」的结论。

## 3. 已核对的仓库基线

- Astro 静态站，正式域名 `https://daily.maas.click`；nginx + rsync 发布，未发现公开 REST / MCP 服务。
- `sync-diff-to-site.py` 的 `KEEP_DAYS = 60` 实际表示最近 60 个合法日期文件，非 README 所述 14 天；周归档索引也由窗口内数据重建。
- 本地日变更数据最新日期为 2026-09-08，仅有 6 个日期文件。这里不推断生产故障；实施前应核对 CI 与线上新鲜度。
- 通用 diff 是文本行集合差异；JSON 新增／删除行分别截断至 30／10 条，不能把它直接宣传为完整 diff。原始快照存在时可重算。
- `daily_changes.json` 中通用变更没有稳定条目 ID、实际基线引用、逐源抓取时间。
- 价格事实已有 `fact_key`、计费八元身份、Decimal 金额、`field_state`；应复用。
- 价格运行时有 `Evidence` 和 `ContentSnapshot`，但 history 只保存 facts，脚本没有完整落盘 evidence 定位对象与快照元数据。`price_changes` 也是简化事件，不能作为公共价格事实的唯一来源。
- 价格类型注释写 epoch ms，但 provider 使用 `time.time()` 秒；公开投影需要显式统一时间单位，不能照抄注释。
- `fetch-prices.py` 仅在有 events 时写入当日 price_changes；重跑无变化可能保留旧事件。`--only` 的局部抓取也需要保证未抓厂商不被全量覆盖。
- 三个工作流使用不同 concurrency group，同写生产目录；部署还可能先上线数据、后提交失败。新增长期 ID 和 API 后，需收敛发布竞争。
- `deploy.yml` 排除了所有 Markdown 更新。仅修改 Skill、方法说明或文档内容时可能不会自动部署，需修正相关触发规则。

## 4. P0 架构决策

```text
抓取 / 价格提取 / 周报导入
  ↓
持久记录 + 快照元数据 + 证据索引（git 跟踪）
  ↓
公开投影构建器（字段校验、证据校验、稳定排序）
  ↓ 同一 datasetVersion
Astro 页面 / RSS / 静态 JSON        只读 Node 服务
                                   ├─ REST /api/v1/*
                                   └─ MCP  /api/mcp
```

保留站点静态构建，新增 `services/agent-api/`。REST 与 MCP 调用同一查询模块、读取同一已发布投影；请求时不抓官网、不调用 LLM、不修改数据。使用官方 MCP SDK，并在实施开始时确认可用稳定版本、锁定依赖，不自行拼装协议。

静态文件可作为数据下载，但不能宣称支持任意 query 参数过滤。Astro 静态端点构建时生成；动态查询与 MCP POST 由运行服务处理。参考：[Astro endpoints](https://docs.astro.build/en/guides/endpoints/)。

MCP 使用 Streamable HTTP；可选择单次 JSON 响应、不提供独立 GET SSE 推送流。业务上「不提供实时推送」不等于协议上禁止 SSE 编码，二者分开描述。参考：[MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)。

P0 不建设持久同步接口、Webhooks、全文镜像、账户系统、数据库集群。服务只读发布文件即可。

## 5. P0 工作包与执行顺序

以下路径是计划新增或修改，不表示已存在。执行顺序为 A → B → C；C 后 D、E 可分别推进；最后 F 集成验收。

### A. 固定公开数据约定与来源身份（预计 0.5–1 人日）

新增：

- `docs/contracts/public-api-v1.md`：字段、时间、分页、保留、修正、错误约定。
- `schemas/public-v1/`：record、price、evidence、source-status、weekly 与发布清单的 JSON Schema。
- `pipeline/config/source_registry.json`：稳定 source_id、现有 platform/provider ID 映射、来源 URL、来源类型、public_enabled。

平台标识优先映射现有 `site/src/data/platform-logos.json` 与价格 provider_id，不创建第三套互不关联的名称。URL 改动不自动改变 source_id；真正新增来源显式分配 ID。关键词搜索 P0 不承诺完整模型别名合并。

公开记录的最小字段：

| 字段 | 规则 |
| --- | --- |
| id / revision / status | 固定条目身份；revision 从 1 递增；status=active/corrected/withdrawn |
| recordType | source_observation / price_change；不把整批来源 diff 冒充单一发布事件 |
| providerId / sourceId | 稳定标识；外部行业来源允许 providerId=null |
| observedAt / publishedAt / updatedAt | ISO 8601 UTC；官方发布时间未知则 null；updatedAt 仅在公开内容修订时变更 |
| observationDate / timePrecision | 历史只有日期时保留 date 精度，observedAt 可 null；不能补造午夜抓取时刻 |
| evidenceLevel | structured / source_diff / incomplete；与是否过期分开 |
| title / summary / summaryOrigin | 原始观察与 AI 摘要分开；summaryOrigin=rule/llm/manual |
| changeType | P0 只有结构化事实支持 price_added/price_changed；其余默认 source_updated |
| links / evidenceIds | 站内详情、官方来源、证据入口；不可解析的引用不能标 structured |
| quality | fresh/stale/unknown、解释、最后成功时间；不是 AI 打分 |

稳定 ID 规则：通用记录粒度为「source_id × Asia/Shanghai 观察日期」；价格变化为「fact_key × 观察日期」。对规范化身份元组计算完整 SHA-256，加 `obs_` / `pc_` 前缀，不把摘要、行排序、内容 hash、当前运行时间混入条目 ID。同日重跑更新 revision，跨日再次观察是另一条记录。P0 明确是日批次记录，不承诺一天内每个瞬时变化都单独成条。

归档保存已发布版本；更正不换 ID，保留修订说明；撤回保留可访问的说明页。噪声重新分类导致退出默认列表时标明原因，不能静默删除既有 ID。source_id / fact_key 的身份迁移保留 alias 或 redirect，不直接让旧地址失效。

验收：schema 可验证合法／缺失字段；同日重跑、平台展示名修改、摘要重写不改变 ID；跨日身份不会错误复用。

### B. 持久归档与证据补齐（预计 2–3 人日）

修改：`fetch_sources.py`、`fetch-prices.py`、必要的 `pricing/providers.py` / `view_data.py`。

新增：

- `pipeline/scripts/export-public-data.py`：唯一投影入口，支持 `--backfill`、`--check`、显式输出目录；离线可运行。
- `data/records/<id>.json` 与 `data/record-revisions/<id>/<revision>.json`：当前条目及已发布修订。
- `data/evidence/`：不可变证据对象、快照元数据及内容 hash。
- `data/source-runs/<run-id>.json`：逐源运行结果，不将最后一次成功伪装成本次成功。
- `data/public/v1/`：构建后的公开投影；内部原始内容不直接复制进 public 目录。

执行步骤：

1. 通用抓取记录实际 observedAt、source_id、此次与前次快照 ID；原有每日文件继续服务旧页面，另存不可变快照，防同日覆盖破坏证据。
2. 价格抓取持久化 `Evidence` 的 locator、excerpt、snapshot_id、extractor_version，并保存快照 URL、时间、hash。事实继续复用 fact_key 与完整计费条件。
3. Kimi 聚合快照要保留各子页 URL 与片段来源；不能将所有价格都指向目录首页。时间显式由当前实现的秒转 ISO，并用 fixture 校验。
4. 成功抓取但当日无有效变化时清空／修正该日旧价格事件；抓取失败保留旧事实及旧证据，更新 stale 状态。局部 `--only` 抓取合并未选厂商，不删除其数据；未选不计本次成功。
5. 首次抓取或缺乏可比基线只建立状态，不声明调价或下线。比较币种、单位、region、tier、billing_mode、context/time 条件一致的事实；条件变化另行说明，不输出误导百分比。
6. 通用 diff 记录以 source_updated 发布，标注 source_diff；jitter 默认排除。LLM 已有摘要可保留，但不升级证据等级。
7. 从全部现有日期文件、快照、价格 history 回填，不从 60 文件窗口回填。原始快照足够时重算完整文本 diff；否则明确 evidence incomplete、diffTruncated，不推测缺失行或基线。
8. 历史价格可离线重跑对应快照进行证据重建，只有模型／金额／条件对齐才认定回链成功；否则保留 incomplete。首发前至少有一轮新采集价格完整通过证据校验。
9. 新增 `/item/<id>/` 与 `/evidence/<id>/`；只展示转义后的必要文本摘录、前后值、定位信息与 hash，不执行抓取 HTML。原始快照内部保留，P0 不新增全文下载服务。
10. 修改 `site/src/pages/daily/[week].astro`、首页条目入口：挂稳定链接；周归档索引从持久数据生成，历史页不随 KEEP_DAYS 消失。周报 `/weekly/<id>/` 保持现有路径。

归档策略：已公开的条目 ID 不因滚动窗口或版本清理失效；事实修订与证据记录进入 git 持久保存。发布包的技术保留期不等于内容保留期。撤回页面仍解释状态。

验收：同日二次运行幂等；模拟超过 60 个日期后旧链接仍存在；失败来源的旧证据可打开；删除定价行不自动宣称降价/下线；新公开 structured 价格证据引用零悬空。

### C. REST 查询服务与静态分发（预计 1.5–2 人日）

新增 `services/agent-api/`，建议拆为 `server.ts`、`dataset.ts`、`query.ts`、`http.ts`、`mcp.ts`。加载已校验发布投影，在内存构建简单索引即可；P0 不引入外部搜索服务。

| GET 路径 | 功能与参数 |
| --- | --- |
| `/api/v1/changes` | provider、type、q、from、to、limit、cursor；最近变化查询，不是增量同步日志 |
| `/api/v1/items/{id}` | 当前条目、修订说明、证据链接；withdrawn 仍可读取 |
| `/api/v1/prices` | provider、model、component、region、billingMode、limit、cursor；原币种价格及完整条件 |
| `/api/v1/evidence/{id}` | 证据摘录、快照时间、来源 URL、定位、hash、完整性说明 |
| `/api/v1/weekly` | 正式周报索引，limit、cursor；默认最新在前 |
| `/api/v1/weekly/{id}` | 正式周报结构化内容；不将滚动周摘要冒充正式周报 |
| `/api/v1/status` | 各数据流最后尝试／成功、已知失败、覆盖范围、datasetVersion |

公共约定：

- 列表默认 limit=20，上限 100；q 为 2–100 字；未知、重复或错误参数返回 400，不静默忽略。
- changes 默认最近 7 天，以最新发布清单中固定的 `asOf` 为窗口锚点；任意窗口最多 90 天；默认不含 jitter 和 withdrawn。相对窗口不是墙钟实时窗口，响应明确返回 `query.from/to/asOf` 与 `dataThrough`；数据未更新时不得显示“截至现在”。
- 绝对时间按 `[from,to)`，必须带时区；日期精度历史按上海日历日期参与查询并保留精度标记。超出已覆盖日期返回空结果及 coverage，不猜历史。
- 所有列表响应含 schemaVersion、datasetVersion、query、coverage、items、page；实体响应含相同版本信息。缺失与空列表有不同语义。
- 价格 API 默认原币种 Decimal 字符串与原单位，返回模型／组件／区域／档位／阶梯／峰谷条件。换算值如展示必须附手工 FX 日期，P0 不提供“全平台最低价”的自动结论。
- 查询按稳定键排序；cursor 包含版本、规范化查询摘要和最后排序键，作为不透明值回传。严格校验结构与绑定关系，cursor 从不构成权限凭证。
- 翻页固定 datasetVersion；服务保留最近 7 天的查询数据版本，版本已清理返回 409 `restart_query`，明确从第一页重新查询。当前未变化的版本始终保留。不得把这个查询 cursor 宣传为可无限期续传的 changes 同步 cursor。
- 错误采用 Problem JSON：type/title/status/detail/code/requestId/recovery。未知实体 404；非法查询 400；版本失效 409；限流 429 + Retry-After；无任何有效发布数据 503。
- ETag 基于规范化查询和稳定响应内容，不把每次请求时间／requestId 加入成功响应体；未变化返回 304 空体。
- 初始建议 REST `max-age=0, s-maxage=300`，RSS 1800 秒；客户端不快于该节奏轮询。内存保留最近有效投影，更新失败继续服务旧版并在 status 显示状态；没有有效版返回 503。
- 匿名 REST GET/HEAD/OPTIONS 支持 CORS，暴露 ETag、Retry-After、X-Request-Id；不允许凭证跨域。缓存 key 包含完整查询；错误不缓存，MCP POST 不走共享响应缓存。
- 发布 `openapi-v1.json`、`llms.txt`、`data/v1/manifest.json` 和版本化静态数据分片。manifest 列 schemaVersion、datasetVersion、文件 URL/hash、coverage；全量 JSON 下载不等同增量同步 API。

验收：筛选真实有效；分页同一数据版本无重复／漏项；新增、摘要更正、撤回导致 ETag 变化；无修改重建不改变 datasetVersion；304 空体；跨查询 cursor 拒绝；REST 与静态包相同版本实体内容一致。

### D. MCP 与 Skill（预计 1–1.5 人日）

MCP 地址 `/api/mcp`，五个工具：

| 工具 | 对应能力 |
| --- | --- |
| `maas_get_changes` | 最近变化及关键词／平台筛选 |
| `maas_get_prices` | 指定模型计费事实，不替用户自动择最低价 |
| `maas_get_item` | 稳定条目与证据 ID |
| `maas_get_evidence` | 核验事实依据 |
| `maas_get_weekly` | 最新或指定正式周报 |

工具复用 query 模块，默认 10 条，上限 30 条；分页只按工具返回 cursor 继续。输出文字与 structuredContent，明确时区、证据等级、数据时间。每个工具都只读，不提供任意 URL 抓取、文件读取、shell 或写入。价格查询返回 stale 时，文字答案必须同步说明。

按官方 SDK 处理 initialize、initialized、tools/list、tools/call、版本协商及协议错误。校验 Origin（缺省的非浏览器客户端允许；存在时只接受配置允许的来源），设置请求体大小和限流，不缓存 POST。远程进程绑定回环地址，由 nginx 终止 HTTPS。

新增 `agent-skill/maas-daily/`：

```text
SKILL.md
README.md
references/api.md
references/errors.md
agents/openai.yaml
```

Skill 路由和行为：问题→唯一默认端点；不需要 MCP 或 Key；先查询再总结；返回 ID 原样使用；不得将页面删除推断为产品下线；价格必须同时引用条件和观察时间；失败不拿旧知识补答案；分页／重试遵守 API 约定。Skill 代码许可与数据使用说明分别维护，不能把一个 MIT 文件误用为数据许可。

在 `site/public/maas-skill/` 发布构建副本、校验清单与 install.sh。安装器只写显式目标目录，先完整下载与 SHA-256 校验，确认 Skill 名称与文件清单后替换，失败恢复旧目录；不默认 sudo，不覆盖其他 Skill，不收集 Actor。P0 支持 `--dir`；平台快捷目标与软链仅为经过实际验证的客户端提供。校验清单保证下载一致性，不宣称等同独立签名认证。

验收：SDK 客户端完成一次真实工具调用；至少 Codex 与一个其他支持远程 HTTP 的客户端完成接入验证；Skill 在临时目录安装、更新失败回退、错误 checksum 拒绝；新会话能触发价格／变化／证据／周报四类问题。不得为测试静默覆盖用户已有 Skill。

### E. 接入页面、RSS 与方法说明（预计 0.5–1 人日）

新增：`site/src/pages/agent.astro`、`method.astro`、`changelog.astro`、`feed.xml.ts`、`feed/weekly.xml.ts`，按需使用 `@astrojs/rss`。

`/agent` 顺序：能问什么 → 四条入口 → 一段可复制配置／安装提示 → 一句验证问题 → 成功示例 → 数据范围与更新节奏 → 错误恢复与反馈。复制按钮提供成功反馈，地址从统一 site 配置生成。

默认 feed 为有效变化摘要，最多 100 条；正式周报 feed 保留最近 30 期。GUID 使用稳定条目 ID／既有周报 ID，link 指向本站永久页，description 附官方来源。正文只发本站自有摘要与必要摘录，不镜像第三方全文。修订不换 GUID；RSS 不承诺可靠传递所有更正与撤回，需要核验时查询详情 API。

`/method` 说明文本集合 diff、截断／重算规则、噪声边界、首次发现不等于发布时间、LLM 可能错误、价格条件、手工榜单与 FX、失败沿用策略。首页和价格页显示各自数据时间，不用一次成功构建掩盖数据未更新。

来源健康信息区分「抓取成功」「价格解析通过」「最后有效事实时间」。基础状态可由现有日志回填，未知值显式 unknown；P0 不展示虚构的长期成功率曲线。

`/changelog` 首期记录接口范围和限制；接口 v1 只允许兼容添加，破坏性变化开 v2。当前没有旧公共 API 要下线，不先造 Sunset 公告。

验收：RSS 可解析、GUID 去重、页面链接无 404；复制配置中所有路径可访问；手机宽度下四个入口和代码块可使用；方法说明与实际 schema 一致。更新 README/HANDOFF 的域名、路由、归档范围和发布流程。

### F. CI、部署与首发验收（预计 1–1.5 人日）

修改三条工作流，让 public exporter 在最终数据写完后运行；`skip_fetch` 仍从已提交数据构建投影，不能触发实时抓取。把来源记录、证据、公开投影加入自动提交清单；有数据变化应先成功持久化／提交，再发布对应版本，避免发布了无法从仓库恢复的 ID。

新增构建与部署脚本：`scripts/build-release.sh`、`ops/deploy-release.sh`、`ops/maas-agent.service`、`ops/nginx-agent.conf`。构建产物包含静态站、公开投影、API 服务、锁定依赖信息与 release manifest。投影版本由内容决定，不能只用构建时间。

部署方案：

1. 保留本地授权部署和 GitHub Actions 两条通道，但共同调用发布脚本；不能只靠不同 workflow 的各自 concurrency。服务器发布锁覆盖本地与 CI；在切换前核对待发布提交／版本，拒绝旧作业覆盖新版本。
2. rsync 上传到新的 staging/release 目录，不直接覆盖在线根目录；hash、schema、完整链接检查通过后才切换。将当前站点路径迁移成指向 release/site 的入口，API 每次请求固定读取该入口对应的 release/data；在一次请求内不混读版本。
3. 旧链接内容由持久归档带入新 release；技术旧 release 保留最近 7 天及当前版本，满足分页版本保留合同。业务历史记录不随 release 清理删除。
4. API 作为独立 systemd 只读进程运行；首发先部署兼容服务并本机冒烟，再启用 nginx `/api/v1/` 与 `/api/mcp`。API schema v1 内的服务升级必须能读取当前和上一版投影；不符合时不得热切。
5. 现有 maasdeploy 受限 shell 目前仅允许 rsync，不假定它能 restart 或切换链接。一次性由服务器管理通道配置最小化发布入口、目录权限和 systemd；日常发布只允许固定部署动作，不放开任意命令。
6. 开启 nginx 路由前执行配置检查。首发尚未开放入口时，失败可恢复原静态站；一旦公开永久链接，不能直接切回缺少新条目的旧目录。代码回滚须保留当前已发布归档与兼容投影；数据回退应生成一个修正版 release，包含所有已公开 ID 的有效记录或更正／撤回说明，再切换入口。回退不能清除持久归档，新旧数据版本与服务兼容性必须有演练记录。
7. 修改 deploy paths-ignore：Skill 源文件、站点消费的 Markdown、协议文件变化应触发重建；仅研究文档更新可继续忽略。统一 daily/weekly/deploy 的发布协调，不取消正在持久化数据的运行。

首发阻断条件：结构化事实证据断链；相同 ID 指向不同身份；分页丢失；无变化重跑产生新 GUID；MCP 与 REST 同版本结果不一致；失败数据显示 fresh；安装器破坏旧目录；站点／数据发布混版。任何一项失败都不宣布 P0 完成。

## 6. P0 必要测试与验收清单

新增 `tests/test_public_export.py`、`services/agent-api/tests/`、`site/tests/public-links.test.mjs`、安装器临时目录测试。沿用现有价格、榜单与 Logo 测试；无需给静态说明文字逐句写测试。

| 用例 | 预期 |
| --- | --- |
| 同输入重复导出、AI 摘要修订、显示名修改 | ID 稳定；只有内容改变时 revision / ETag 改变 |
| 同日抓取覆盖／失败／恢复／无变化重跑 | 旧证据仍存在；stale 正确；旧伪事件被修正 |
| 局部厂商抓取 | 未选厂商不被删除，不计本次成功 |
| 输入价变、输出价不变，或计费条件变 | 返回具体变化，不概括为全价下降 |
| 来源缺失、首次发现、解析器身份迁移 | 不生成无依据的下线／降价结论 |
| 连续翻页期间切换 release | 继续读取固定版本或明确 restart_query，不静默混版 |
| 非法／跨查询 cursor、未知参数、重复参数 | 确定错误码与恢复动作 |
| REST 200 → 相同 ETag → 304 | 304 无响应体；更正后重新 200 |
| 数据全部失败但有旧版／无旧版 | 旧版带明确数据时间／503，不输出空的正常成功结果 |
| 61+ 日期与旧永久链接、withdrawn 记录 | 链接仍可解析，状态明确 |
| MCP 初始化、工具发现、真实查询、错误参数 | 协议和文字／结构化输出均正确 |
| 非预期 Origin、超大请求、请求任意路径 | 被边界校验拒绝，服务不读取数据目录之外的文件 |
| RSS 修订与订阅刷新 | GUID 不变、不重复新增；XML 正确转义 |
| 安装下载失败、校验失败、目标是其他 Skill | 原目录完好，退出并给出原因 |
| 发布失败、两个发布竞争、服务回滚 | 旧版继续可用，旧作业不能倒灌 |

首发演示问题（按真实数据回答，不保证一定有变化）：

1. 「最近 7 天有哪些 API 定价变化？区分新增定价与价格调整。」
2. 「查询当前台账里某个确实存在的模型输入输出价格，说明条件、时间和来源。」
3. 「打开上一条返回的 evidence ID，说明证据是否完整。」
4. 「给我最新一期正式 MaaS 周报，并附链接。」

完成定义：四种入口都真实可用；至少一轮新采集数据完成证据闭环；上述关键回归与线上只读冒烟通过；发布和回滚步骤可由另一位维护者复现。只完成网页或本地 mock 不算 P0 完成。

## 7. P1：提高决策价值

P0 稳定后按下列顺序推进，不以页面数量作为目标：

1. **模型身份与平台可用性**：维护 model family/version/alias 映射，区别官方模型与平台部署名；以人工确认的小表起步，歧义保留未关联。建立同模型跨平台查询基础。
2. **影响说明**：扩展 llm-digest 的 prompt、解析器、存储和 UI；新增 impact、audience、evidenceIds，允许为空。说明必须附适用条件；不能把 inference 混入 structured fact。
3. **筛选与订阅粒度**：发布、调价、弃用／下线、API/SDK 变更；先支持筛选与精选的平台 RSS，再考虑主题页面。来源类型仅是辅助特征。
4. **来源健康趋势与纠错**：记录抓取／解析／事实更新时间，展示真实分母的成功率；建立一条条目级反馈和更正流程，优先处理高噪声来源。

验收重点：选取约 30 条跨类型历史样本人工核对，不得出现跨模型误关联或无证据下线结论；影响说明能帮助判断成本、迁移或选型，而非重复摘要。

## 8. P2：跨平台事件与更深分发

- `/events/<id>/`：模型发布、各平台上架、定价、后续迁移组成时间线；每个事实保留原 ID 和证据。时间窗只召回候选，不决定合并；模型版本、动作、平台范围共同决定关联。
- `/topics/<slug>/`：优先模型家族与具体决策主题，有足够内容与真实访问需求再独立成页。
- 多榜并列＋价格条件对照：明确来源日期、harness、缺失值、覆盖集合；不把市场份额和能力评分混合。综合分须另有方法学评审与需求证据。
- 当外部消费者确实要求完整镜像时，再做 snapshot＋changes：不可变修订日志、单调水位、快照期间修改/撤回、故障重试、日志压缩与恢复都需契约测试。cursor 只是编码方式，不是同步正确性的替代。
- 只有拉取延迟实际不满足需求时，才重新评估推送；当前每日采集没有建设秒级推送的依据。

## 9. 排期、范围与衡量

P0 估算约 **7–10 个有效开发日，预留集成后约 2 周工作量**；历史证据缺失、服务器权限配置与真实客户端兼容性可能影响排期。不是一天页面开发任务。各工作包人日是估算，不是对部署环境的已验证承诺。

可拆三个可审查交付：A+B 数据与引用 → C+D 查询与 Agent → E+F 分发与首发。前两段完成不代表整体结束；用户本轮只请求计划，实际执行与上线留在后续实施任务。

首发检查结构化价格证据覆盖率 100%、公开引用零悬空、身份幂等、版本一致性和真实接入成功。上线后观察匿名请求成功率、延迟、304 命中情况和脱敏的端点使用量；不把请求数当用户数，不必先引入 Actor UUID。两周后根据实际查询与反馈决定 P1 优先级。

## 10. 依据

- 本仓库 `README.md`、`HANDOFF.md`、管线脚本、价格领域模块、页面与三条 GitHub Actions 工作流。
- CC 研究：`docs/research/2026-09-11-aihot-analysis.md`；保留其观察，修正本文第 2 节所列推断与背景。
- [AIHOT Agent 接入](https://aihot.news/agent)、[OpenAPI](https://aihot.news/openapi-v1.json)、[Skill](https://aihot.news/aihot-skill/SKILL.md)、[安装器](https://aihot.news/aihot-skill/install.sh)。本轮会话已实测 REST、快照、ETag 304、MCP initialize/tools/list/tools/call；未审计其服务端源码，未完整测试其增量同步一致性。
- [Astro endpoints](https://docs.astro.build/en/guides/endpoints/)、[MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)。正式实施时按锁定 SDK 版本核对协议兼容性。
