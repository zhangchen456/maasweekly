# AR-03 数据所有权与重建方向

事实权威保持现有归档，新增标准输入把原寄存在站点的数据迁出。标准目录读取失败就中止，没有 `site/` 回读兜底。一次性迁移脚本是唯一允许读取旧展示数据作为迁移输入的入口；迁移标记存在后不再导入展示修改。

| 数据 | 权威源/唯一作者 | 消费与重建 |
| --- | --- | --- |
| 原始快照、响应证据 | data/snapshots；现有抓取器 | 归档器、回放 |
| 来源条目/修订 | data/records、record-revisions；record_archive | exporter、详情页、projector |
| 价格事实/证据/事件 | data/price-facts、price-evidence、price-records、price-record-revisions；pricing/archive | exporter、价格投影；不新增另一套事实归档 |
| 信源滚动状态与清洗后的变更输入 | data/normalized/source-streams.json；sync-diff-to-site | exporter SourceStatusIndex、摘要、site projector |
| 当日价格变化摘要输入 | data/normalized/price-events.json；fetch-prices | 摘要、site projector；原价格事件权威仍为 price-records |
| 每日摘要 | data/derived/day-summaries.json；llm-digest | site projector、周摘要；来源状态写入失败不由摘要覆盖 |
| 周聚合/串讲 | data/derived/weekly-rollup.json（sync）及 week-summaries.json（LLM） | site projector；滚动摘要不是正式周报 |
| 正式周报 | data/editorial/weekly；import-weekly 编辑导入 | exporter、structured extractor、site projector；data/weekly 原稿继续保留作为导入源 |
| 周报结构/时间线 | data/derived/weekly-structured、timeline.json；extract-structured | exporter、site projector |
| 展示价格台账/历史 | data/derived/pricing；fetch-prices 计算投影 | 失败沿用、离线价格回放、site projector；事实依然以 price-facts 为准 |
| 公开快照 | data/public/v1；export-public-data | API、RSS、Skill、site release reader |
| 兼容展示 JSON/内容 | site/src/data、site/src/content/weekly、weekly-structured、timeline.json；data_store.project_site | Astro；单向重建，不反向写权威源 |
| 模型/开发者/平台身份 | data/model-registry，现有 T07 resolver 与审核流程 | exporter、价格投影、目录；不从名称猜关系 |

正式周报先核对 23 份原稿按旧导入规则的渲染结果与已发布文本全部相同，再把已发布完整文本与结构逐字节迁入标准目录。保留 ID、date、period、标题、正文、链接及 RSS。原稿与带 frontmatter 发布稿并非原始字节相同，不能直接复制原稿替代已发布内容。没有重新生成历史周报或摘要。

已有摘要的生成模型、prompt 和真实输入未知，统一标 `legacy_unknown`，这些字段为 null。未来成功记录精确实际 prompt 的输入哈希、模板版本哈希、模型和参与输入的稳定记录 ID；失败单独记录 lastAttempt 并保留上次有效摘要。来源/价格事实及 freshness 不因 LLM 失败而被改写。未调用真实模型验证；使用独立输入与失败模拟。

```sh
# 仅首次切换，从现有已发布展示数据导入；已有标记则只返回原迁移记录。
python3 pipeline/scripts/migrate-standard-inputs.py
# 从标准输入和已有事实重建兼容产物。
python3 pipeline/scripts/project-site-data.py
# 发布同样读取标准输入，和 Astro cwd/build 无依赖。
python3 pipeline/scripts/export-public-data.py --dry-run
python3 scripts/generate-public-contract.py --check
```

LLM 及采集入口只写各自标准输入，结束调用统一 projector。site prebuild 先检查合同生成漂移、重建兼容数据，再执行原档案门禁。直接调用 Astro 的 fixture 构建仍由隔离输入保证一致性。离线 archive-price-evidence 改读标准 ledger_history，离线辅助索引默认写 derived/archive-indexes；显式指定输出路径的调试功能保留，生产站点索引仍由 projector 从事实重算。

兼容窗口：本轮及下一次生产验证周期保留旧站点形状；确认 Astro、公开导出及工作流全部迁移后再另行安排删除。标准迁移新增约 49 MiB 数据，大部分为已有展示历史的权威副本；旧展示文件作为兼容缓存暂时存在。并未复制不可变价格事实/证据归档。AR-06 会评估存储和恢复，不能在尚未上线时删除旧路径。回退消费者可用现有兼容产物，不能用旧 site 内容反向覆盖新事实/摘要。

共享合同 canonical 位于 packages/public-contract：schema-dto 从 JSON Schema 生成，entities 为与公开 DTO 关键字段关联的内部增强视图（包含当前查询使用的已投影字段），validation 为纯 manifest/catalog/order/reference 校验；node-reader 单独封装 fs/hash。生成器 v1 使用 Python 标准库，支持当前 object/array/union enum/allOf/ref 子集，不支持的结构关键字硬失败，TS 类型不声称执行 runtime Schema 验证。

API 与 site 使用生成的自包含桥接文件：API `.js` 相对引用编译到 dist/public-contract，site `.ts` 引用供 Node TS/ASTRO 读取；无需跨 rootDir import 或生产源码包。prebuild 的 --check 拒绝未提交漂移。双方执行相同的完整文件 hash/bytes/路径、目录身份、排序及引用校验，包括未 select 文件；schemaVersion、七个必需集合、重复条目和 catalog 缺失拒载。JSON Schema 补齐已有可选 model/family 字段、带连字符的集合路径以及模型目录 Schema，属于对既有 wire 契约的描述补齐，不生成新的业务版本。providerId 的 legacy query namespace 和所有 unknown/未解析身份维持现状。
