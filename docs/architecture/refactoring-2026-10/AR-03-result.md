# AR-03 数据层与合同验收

状态：LOCAL_VERIFIED。完成时间：2026-10-02（Asia/Shanghai）。候选 commit `0ba9ee17ad8a305c99cbb5e01192a613337aad3c`，未推送、未发布。

采集价格、清洗信源、LLM 日/周摘要、正式周报导入及公开导出改用独立标准输入；site 兼容产物由统一 projector 单向生成，公开导出无需 Astro 或站点目录。已有价格事实/证据/修订归档没有复制或改写。目录、唯一作者、重建命令、兼容窗口和身份边界详见 [数据所有权](./data-ownership.md)。榜单的调度及恢复协议仍按 AR-04 继续改造。

迁入 source-streams、price-events、day/week summaries、editorial weekly、derived pricing/history 和 structured/timeline。23 份周报保留原发布文本与元数据，原稿按旧导入规则生成后全部一致。历史摘要模型/prompt/input 不可追溯，记录 legacy_unknown/null，没有调用 LLM 重写历史。未来摘要记录实际 prompt 哈希、模板哈希、模型及稳定输入 ID，失败保留上次内容与独立 lastAttempt，不更新事实 freshness。

采用 Python 标准库生成器 v1 从 JSON Schema 生成公开 DTO，canonical 公共实体与 pure manifest/catalog/order/reference 校验放在 packages/public-contract；fs/hash 独立在 node-reader。API/site 使用确定性自包含桥接，API 编译后的 dist/public-contract 随运行包分发，避免跨 rootDir 或遗漏生产源码。--check 门禁拒绝漂移。JSON Schema 补齐已有 model/family 可选字段、model-identities 与带连字符路径；没有新 wire 字段或业务版本。

同一事实输入通过冻结旧加载器与新加载器在临时目录重建，**七集合新旧与当前发布文件逐字节完全相同**；稳定 ID、revision、factKey、价格条件、链接、正式周报与 dataThrough 不变。datasetVersion 仍为 `ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`，dataThrough=2026-10-01；changes/items=7459、prices=1435、evidence=11651、weekly=23。

完整标准 release 回归 **49/49，退出码 0，302.164 秒（含打包）**，干净临时检出运行 build-release，构建后 tracked diff 门禁通过。标准输入 6 项、API REST 68 项及 site/API 同坏 manifest 校验通过；原价档案、registry、RSS/Skill、页面、SEO、多语言、MCP 和 Umami 回归包含在完整套件。摘要失败/标准输入 symlink/生成漂移/价格独立输入通过模拟验证，未做真实模型调用。

生产运行包 `rl_0ba9ee17ad_6fd3cc403bf9`：24,362 文件，703,637,917 字节。在仓库外 cwd、仅生产依赖实际启动成功；REST 四端点及 MCP initialize/五工具/实际查询返回同一 datasetVersion；两份 RSS 与 Skill 八个文件 hash 通过，无临时 fixture 页面。共享合同编译输出可独立运行，未依赖仓库 packages 或 site 源码。

证据：[新旧对账](./acceptance/AR-03/data-reconcile.json)、[迁移清单](./acceptance/AR-03/migration.json)、[完整回归](./acceptance/AR-03/regression.json)、[产物信息](./acceptance/AR-03/release-build.json)、[仓库外运行](./acceptance/AR-03/release-smoke.json)、[源码哈希](./acceptance/AR-03/source-files.json)。正式 release 的临时检出与本轮临时日志将在归档后清理；这些离线证据不等于线上 Nginx/CDN 或已发布验证。

兼容展示数据暂时保留，标准副本增加约 49 MiB，属于迁移期间的权威输入与兼容缓存并存；AR-06 继续评估分层存储。不要在发布前删除旧路径。回退代码可继续消费已生成的旧结构，标准事实和摘要不能被旧 site 反向覆盖。AR-04 将补齐有界抓取、运行关联与跨文件提交/恢复，当前原采集跨文件写入没有被本项宣称为原子事务。
