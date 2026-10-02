# 架构改造发现

- 当前 /api/v1/models 已存在于代码与 OpenAPI，旧契约仍写不新增，需要以后续 T07/页面验收证据对齐。
- API DatasetHolder 30 秒全量同步重载；REST/MCP 各共享进程桶。
- release 的服务器锁与旧提交拒绝已有，不重建这两项。
- Umami Cloud 已上线；自托管脚本是历史候选。
- 测试目前会重建正式 dist，再最后构建恢复；AR-05 隔离。

AR-06 远端配置：用户确认暂时没有对象存储，先本地演练。


AR-02 初次验证：API 61/61（含新增7项），容量预算通过。10× 并发10的P95最高25.3ms，重载事件循环最大16.9ms；worker首次加载较同步基线增加耗时。全量回归正在运行，不能宣称已验收。真实 Nginx 未安装，本地生成器/事务测试可以验证候选结构，但线上429代理链验收尚待发布窗口。

AR-05 预研：GitHub 官方2026文档 concurrency 支持 queue:max（100个pending），cancel-in-progress:false，FIFO按等待时间而非触发时间；不保证调度顺序，必须保留精确SHA/main祖先/过时候选门禁。daily/weekly的写入job共享锁，部署在单独可复用workflow job内持另一锁，父workflow不可持部署锁。bot GITHUB_TOKEN push不会链式触发workflow，因此数据写入应显式调用部署；手工数据提交必须进入deploypush路由，不能忽略data/**/所有md。
AR-05 site records隔离建议：单一临时repo结构，复制site/src/scripts/config与records/revisions；其余只读数据与node_modules链接；两fixture同次临时Astro build，正式dist不写，去掉最终恢复build。无需新增业务环境变量，通过临时cwd保持现有relative路径，避免扩大对页面代码的改动。
官方来源：https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency 和 https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows 。Astro配置参考已读取：https://docs.astro.build/en/reference/configuration-reference/ 。

AR-03预研：public_export/loaders.py直接读site/src/content/weekly与weekly-structured、site/src/data/daily_changes。fetch-prices613行/extractors2305行/sync-diff264行/llm-digest282行，需逐一建立单向所有权（不能只给exporter复制输入）。canonical编辑内容可迁移现有已发布site周报及structured到data/editorial，data/weekly原稿与published必须对账，保留现有ID/日期/正文不重生成历史。信源状态、日/周摘要、price-view移至normalized/derived，兼容site投影一个作者。LLM依赖/输入hash要从既有事实建立，不能触发重新调用模型。
共享契约可采用packages/public-contract canonical纯TS模块 + 确定性生成API/src与site/src桥接副本（禁止手工改、--check漂移），避免file:../../包依赖在production package脱离repo后缺文件；JSON Schema生成DTO、Node文件读取与纯manifest/catalog/实体检查拆开。若选择真正npm包必须解决pack/vendor+runtime安装，不能跨API rootDir导入根源码。
AR-08 basis待AR-05后开始：结构化日志/最小聚合指标，route模板低基数，UTC时间，不记录URL query/cursor/IP/APIkey；实际响应dataset（包括旧游标）要关联，不能finish时读holder.current假关联。MCP AsyncLocalStorage可保持工具异步查询的实际dataset到请求上下文；REST上下文可在结果完成时记录activeDs。日志缓冲有界、失败不阻断请求；pipeline/build阶段后续接入，AR-08最终容量复核再完成全任务。
当前标准AR-05构建/回归session35000，checkout/tmp/maas-ar05-release.IUjEBg，fresh Python/tmp/maas-ar05-python.oNvhIE；源码候选cb03a05b8，本轮只能读研究或写文档，不修改已验源码直到该构建结束。

AR-04 implementation design (after AR-03 db620e840): eight adapters split and separately committed 48e0c94ee, frozen legacy monolith vs new on all17fixtures facts/evidence/warnings equal. Remaining runner design should use existing price-runs namespace with unique runId, per-source attempt IDs and stage snapshots, bounded2workers/domain1, retry fetch only. Current pa.make_run_record supports run_id but fetch hardcodes fetch-{today} and commits before events/current; change actual runner final unique record after full commit while preserving low-level test API. Browser singleton needs launch single-flight lock before concurrency.
Cross-file consistency: immutable committed input view maps logical data paths to existing immutable revision/fact/evidence leaves (current record JSON == latest immutable revision JSON verified for source and price), and to content-addressed snapshots for mutable normalized/derived/editorial/current JSON. Atomic inputs-current pointer, manifests stablehash excluding run/time, no duplicate fact-version archives. Public loader pins one manifest and ignores newly staged/unreachable leaves. Before each managed writer mutate, lock and capture baseline, create pending journal; after fully validated output capture/advance pointer then mark committed. Process interruption keeps baseline readable; candidate site/release build rejects pending runs. Each writer needs snapshot lifecycle, including sync/import/LLM/backfill or refresh snapshots before exporter under lock to prevent stale direct edits. Prefer always pinned view; optional root with no pointer remains existing fixture behavior. data_store read default live for writers; exporter compose_daily(root, view=pinned) explicit. CLI recover reuses staged original fetchedAt, same parserversion; only-failed new run fetches new observation; offline older parse archives history but must not downgrade current.sources/ledger/lastSuccessAt or rewrite latest history. Process-crash scope, not claim host power-loss durability. Restore/discard pending only canonical mutable role paths from baseline; immutable appended leaves retained for audit. Existing API serves immutable release unaffected. Need genuine kill/crash tests + source/MCP/export regression; no production writes or real LLM/leaderboardAPIkey calls.

AR-06 预核对：data/snapshots 有 2197 文件/248330316 bytes；2188 个独立 SHA/247229743 bytes。199 个价格快照元数据 SHA 中 173 可匹配现存原始字节，26 无匹配。属于迁移前遗留缺口，不能将 metadata 当成已恢复 raw；迁移必须显式登记，保持事实/摘录/公开版本不变。

最终容量：冷加载 worker+完整验证/索引比早期同步基线慢（1x398ms/10x3680ms），但同版本轮询约0.16ms且业务解析0，加载期间旧版服务与分页正确。C10 P95/loop满足200/50ms；内存先于延迟值得关注，包含GeoIP/worker/历史/额外limiter的10x子进程maxRSS约3.03GiB不能等同生产单实例。暂缓DB/队列，多实例与资源升级按实际部署内存/流量目标启动；没有精确扩容日期。
