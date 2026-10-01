# AR-03：标准数据层与共享契约

状态：TODO。优先级：P1。依赖：AR-01。

## 目标与交付

让采集、事实归档、公开导出拥有明确的数据边界，`site/` 只消费可重建的展示产物。统一 Python 导出、Node API 与 Astro 使用的公开类型和 release 校验规则。

交付：数据所有权表、目录/Schema 方案、兼容投影实现、共享契约模块、迁移对账和 `AR-03-result.md`。本任务不改公开 ID，也不顺带启用跨平台本体或数据库。

## 当前入口

- `pipeline/scripts/{fetch-prices,sync-diff-to-site,llm-digest,llm-weekly-digest,export-public-data}.py`
- `pipeline/public_export/{loaders,projector,validator}.py`
- `pipeline/pricing/{base,archive,view_data}.py`
- `schemas/public-v1/`、`site/public/openapi-v1.json`
- `services/agent-api/src/dataset.ts`、`site/src/lib/release.ts`
- `data/model-registry/{models,developers,platforms}.json` 与 `pipeline/model_identity/`

## 3A. 数据所有权与方向

为每个输入/输出写清楚唯一作者、权威源、派生产物、消费者和重建命令。建议按以下角色组织，具体新增路径在实施前写进结果文档：

| 层 | 内容 | 写入者 |
| --- | --- | --- |
| 原始证据 | 抓取快照、响应元信息 | 抓取器 |
| 事实与事件 | records/revisions、price facts/evidence/current、信源状态 | 归档与规范化模块 |
| 编辑内容 | 正式周报源与审核信息 | 导入/编辑流程 |
| 派生内容 | 日摘要、周摘要、页面聚合 | 各自投影器 |
| 公开快照 | `data/public/v1`，按已冻结契约导出 | public exporter |
| 展示产物 | 首页、价格台账、站点索引 | site projector |

新目录可用 `data/normalized/`、`data/derived/`，但不要复制已存在的事实归档。先复用 `data/price-facts/current.json` 等既有权威源，仅补充目前寄存在站点的信源状态、摘要与编辑元数据。

正式周报迁移要核对 `data/weekly` 与 `site/src/content/weekly` 的差异，选定一个权威源，保留现有发布日期、ID 和已发布页面。不能直接假设两目录内容相同。

## 3B. 去除站点反向依赖

1. 把信源状态和摘要从共享 `daily_changes.json` 中拆成独立、带输入版本的派生产物；汇总器最后生成站点兼容结构。
2. 价格采集先产生事实与事件，站点台账由独立投影步骤生成；采集器不再修改站点 JSON。
3. public exporter 改从标准输入读取。不得让公开导出依赖 Astro 构建、站点 working directory 或站点中间产物。
4. 首页需要的信息若不属于公开 API，建立专用展示投影；不为统一目录而把内部摘要和运营信息全部加入公开合同。
5. LLM 摘要记录引用事实 ID、输入摘要、prompt/model 版本与生成状态；本次只规范已有摘要的数据依赖，不更换模型或重新生成历史内容。

过渡期使用单向兼容投影：新权威源 → 旧 `site/src/data` 形状。旧结构只有一个写入者；不能双向同步，也不能让新旧脚本轮流覆盖彼此。

## 3C. 共享类型与校验

以 AR-01 对齐后的 JSON Schema 为公开 DTO 的类型入口，选一种可重复的 TS 类型生成方式，记录生成命令与工具版本。内部领域对象继续可以使用 Python dataclass，不要求整套业务逻辑跨语言生成。

提取 TS 共享模块（建议 `packages/public-contract/`）：公开类型、manifest/路径/hash/版本校验、错误类型。Node 文件读取与纯校验逻辑分开，防止浏览器脚本意外打包 `node:fs`。

站点和 API 使用同一严格校验规则，不能因为抽取而降为较弱的 spot-check。检查 manifest 重复条目、版本路径不符、非法 schemaVersion、缺失 catalog、hash/bytes 不符等失败场景。

明确 API 的 TypeScript 编译和生产打包方式：当前 `rootDir=src`，release 只打包 API dist/依赖，不能直接跨目录 import 使生产缺文件。共享包必须有明确编译输出和依赖安装/随包分发方式，并验证安装后的生产包可独立启动。

OpenAPI、MCP 参数/返回说明继续做契约对照测试；类型生成不自动证明 API 行为一致。

## 3D. 模型身份边界

复用 T07 的注册表、resolver、Gold Set 与已完成的 Developer/Platform 工作。`providerId` 保持 legacy query namespace，`modelId` 保持当前公开身份；不从前缀猜开发者或平台。

建立当前身份字段的来源与责任表，合并重复映射配置时用现有测试证明等价。跨平台 Upstream Model/Availability 仅列出缺失证据与后续任务接口，禁止按名称自动合并、补造关系或把 unknown 改成 confirmed。

## 验收标准

- [ ] 采集器及公开导出不再把 `site/` 文件作为事实权威源；允许独立站点投影器写兼容产物。
- [ ] 同一输入分别用旧路径与新路径构建，所有公开集合、稳定 ID、版本和公开链接一致；必要偏差逐条登记为明确变更。
- [ ] 正式周报数量、ID、内容、RSS 与页面一致，滚动摘要没有变成正式周报实体。
- [ ] 事实与摘要可独立失败/重跑，摘要失败不改变价格/证据和其 freshness。
- [ ] 站点与 API 校验相同坏 manifest 都拒载；有效历史数据与 catalog 继续可读。
- [ ] 生成类型无未提交漂移，生产 API 包脱离仓库源码目录也能启动。
- [ ] T07 registry/identity、public export、API/MCP、RSS、站点价格/记录回归通过。

关键现有验证：`python3 pipeline/scripts/export-public-data.py --check`、`python3 -m unittest discover -s tests -p 'test_public_export.py'`、T07 测试，以及 AR-02 的 API/MCP 测试。新旧导出对账必须在隔离根目录执行，不能覆盖真实归档来比较。

## 切换与回退

先生成新数据并对账，再将消费者逐个切到新输入，最后停用旧写入入口。保留一个兼容窗口及其重建命令，窗口时长在实施结果中明确。回退依赖兼容投影恢复旧消费者，不反向覆盖不可变事实。确认所有消费者完成迁移后再删除旧逻辑。
