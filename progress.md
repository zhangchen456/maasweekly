# 架构改造进度

2026-10-01：开始执行，读取任务入口、全局/站点规则及 planning-with-files 技能；核对初始工作区。当前 AR-01。

首次回归在沙箱遇到本地 socket PermissionError，主动停止（130），日志存 acceptance/AR-01/failed-sandbox.txt；用允许本地测试服务的环境重跑，不算成功证据。benchmark 已在允许环境完成。

AR-01 完成：完整回归 45/45，531.63s；benchmark 3轮/并发1、10、30/1×5×10×；build profile 3轮；合同/README 历史描述已对齐。基线实际 raw bytes/data 722781185，source snapshots 248330316，public 368500150。尚未实时检查生产。

AR-02 实现进行中：worker校验/解析，200实体ACK流式回填；同版本manifest跳过；异步历史single-flight、有界LRU；日期/身份索引与二分cursor；共享REST/MCP异步查询；每IP限流+全局护栏、IPv4映射/IPv6规范化、loopback显式信任。当前/历史加载统一路径，并全序检查、引用检查、最终及祖先symlink边界校验。
针对性/API回归62/62通过（2026-10-02）；完整回归session78700仍执行site records段。容量首测已通过预算，完成完整回归后要重跑带重载期间在线请求的扩充采样（上次报告引用检查改动前，不能最终引用旧源hash）。ops生成器与install-api-runtime.sh候选仅本地，未执行生产安装；真实Nginx未安装，线上代理链验证待发布窗口。

AR-02 本地完成：45/45完整回归430.07s；最终带重载流量容量测量通过，并发10 P95最大24.1ms，10×强制重载loop最大14.7ms，332请求全部200。源码SHA/API62项日志/容量/回归/结果归档完成；生产配置及真实Nginx代理链待发布验收。下一项AR-05。

AR-05 开始：records.test.mjs 已改为单次临时repo/cwd构建，真实record/index/dist不写；针对性页面fixture测试通过（保留XSS/withdrawn断言+真实索引字节/详情页集合不变）。第一次CLI路径astro/astro.js不适配Astro7，已改node_modules/.bin/astro，临时根均finally清理。run-all-tests已修退出码/失败日志保留，去掉正式输出恢复build；依赖缓存新增lockfile/node/npm/ABI/platform/arch指纹脚本；API测试新增compiled aliases供统一套件一次编译复用；release package复用已验dist、独立omit=dev安装。以上未完整回归，尚未提交。下一步改daily/weekly/reusable部署工作流并做隔离git场景验证，再完整AR-05回归。

AR-05 下一步工作流实现补充：统一release-deploy.yml可复用job部署锁 maas-production-deploy-main/queue:max/cancel:false；daily/weekly仅写入job持 maas-data-write-main锁，输出确切sha到独立uses发布job。deploy push包含手工data及site/content；raw data/weekly Markdown先调用weekly import可复用入口后发布。GITHUB_TOKEN提交不会触发递归push，由数据工作流显式调用发布。候选检查必须main祖先，若main仅增加普通文档允许旧候选（防docs更新让唯一代码候选被漏掉）；main增加runtime变化则跳过。构建后/激活前复查，latest候选唯一负责，服务器flock/既有旧提交拒绝继续保留。新增workflow-policy.py分类/候选选择与commit-workflow-data.sh（main变化退出75，不rebase/forcepush）尚未接入yaml/场景测试。

AR-05 工作流已接入：daily/weekly写入job共享 maas-data-write-main(max队列、不可取消运行中)，输出精确sha给release-deploy.yml独立生产锁。push手工data/weekly Markdown调用weekly import路径；其他运行文件/手工data走统一发布；纯docs跳过。提交脚本main变化退出75、无force/rebase；构建后及激活前再查main祖先/新runtime变化，只有docs追加允许原候选；RID按commit+dataset算，不再按目录mtime。
针对性9项workflow graph/实际隔离git/退出码日志/依赖缓存/精确RID测试通过，既有workflow18项通过、deploy7项通过。runner中文相邻变量发现bash解析code变量边界，已改${code}并通过真实exit23失败日志测试。
新增requirements.lock.txt冻结本机已验证Python3.12依赖闭包；PyYAML>=6声明到requirements；CI加-c constraints。Requests2.34.0与Playwright1.54.0的PyPI页面已核实存在（并非宣称最新），来源 https://pypi.org/project/requests/2.34.0/ 和 https://pypi.org/project/playwright/1.54.0/ 。准备临时fresh Python venv安装；路径记录/tmp/maas-ar05-python-path.txt，安装session稍后poll。architecture-regression.py新增--release-workspace：要求干净且相同commit的checkout，在它运行标准build-release（内含全量suite），把日志归档到原workspace；可避免重复完整回归。还未执行完整AR-05验收、未提交实现。

AR-05 干净Python3.12 venv创建和完整锁定依赖安装成功（/tmp/maas-ar05-python.oNvhIE，安装日志/tmp/ar05-python-install.txt）；接下来保存实施候选commit，创建同commit的干净临时checkout，通过标准build-release一次完成完整回归及release构建，原目录保存验收。临时checkout路径会写/tmp/maas-ar05-release-path.txt；完整回归command使用architecture-regression.py --release-workspace。

AR-05标准构建完成：候选commit cb03a05b826692546e7e5f1835565bca28ff7c01，fresh Python/clean checkout，完整suite47组通过（322.73s含标准打包），release rl_cb03a05b82_6fd3cc403bf9，24355文件/703621161字节，正式tracked diff gate通过。仓库外实际生产依赖API进程REST/MCP/静态RSS与Skill8文件hash检查通过，无fixture；release-smoke.json及release-build.json归档。源码没有发布，GitHub真实调度/NginxCDN仍待上线窗口。现在build profile session待poll，完成后写AR05result、归档commit并清理本次临时clone/venv（先保留profile所需venv）。之后AR08基础。

AR-05收尾：阶段profile归档，Astro4→2次、API编译5→1次（含生产包）；完整47/47+标准build322.73s，待真实GitHub调度/线上代理验证。AR05-result已写，删除临时clone/release，仅保留venv给后续回归；下一AR08基础。

AR-08基础完成：48/48回归293.996s、真实API启停/未就绪、5项TS诊断与3项离线告警测试通过；1x开关对比并发10 P95 off15.973/on15.324ms，discard Writable未测journal。修复无变化轮询取消强制audit竞态。证据与result归档，整项AR08仍待后续管线发布事件和最终容量复核。下一AR03，已核对23份data/weekly经现有frontmatter渲染与已发布周报字节全部相同；不是直接比较原稿与带frontmatter发布稿。

AR-03实现候选：标准source-streams/独立price-events/day/week summaries/editorial/derived pricing已迁入；采集/LLM/exporter无site权威读取；统一projector兼容写入及site prebuild。23周报渲染相等，冻结legacy loader与new loader临时生成七集合字节及当前发布字节全部一致，ds_6fd3cc不变；标准输入6tests、API68tests、source31/public16/RSS/SEO通过。canonical公共DTO生成+purevalidator+node-reader、自包含API/site bridges，schema补齐既有identity与hyphen path。下一提交候选/干净clone标准release完整回归，证据不能提前标完成。

AR-03全量收尾：候选0ba9ee17ad、干净clone标准release49/49通过302.164s，tracked diff clean，rl_0ba9ee17ad_6fd3cc403bf9 24362files703637917bytes；实际仓库外生产依赖REST/MCP/RSS/Skill同版本通过。AR03result和证据归档，未推送部署。清理clone/pycache等本轮临时物后进入AR04，价格8适配器拆分先行；事务恢复需保证exporter读提交输入快照且价格沿用/offline时间不倒退。

## AR-04 实施进展
- 八家适配器独立 checkpoint 48e0c94ee；17 fixture 与冻结旧抽取器的事实/证据/warning 逐项一致。
- 价格、信源、榜单和标准数据写入入口接入单写入方运行协议、固定输入视图、提交点与恢复/撤销。价格有界并发 2、同域限速、传输重试，原观察时间保留。
- 实际价格 CLI 子进程归档后 os._exit、无 HTTP 恢复、两次离线幂等通过；源/榜单恢复、dry-run、浏览器 singleflight/context 释放、提交点及孤立修订撤销、输入缓存上限测试通过（18 个测试）。正式全量回归待执行。
- 两家官方网页 deepseek/qwen dry-run 成功：12/2088 facts，退出 0；未写业务数据，不把真实网页漂移当 fixture 合同。

- 增补 unchanged 成功状态、旧观察离线重放不覆盖 current/事件/原始槽位、通用来源冻结对比快照与 offline-preview；畸形榜单 JSON 保留原响应且不再次 HTTP 重试。先前 50/50 通过，最终改动将重新执行全量标准 release。

AR-04 最终 7d7d9d40a6：50/50 完整标准 release 回归 364.821s，仓库外四入口通过；结果与恢复手册已归档。继续 AR-07。

AR-07：复用模型/价格/变化/证据索引，首页和 GPU/芯片/价格展示抽取有类型 ViewModel；中文台账迁移 Astro + 独立严格 TS + CSS。107 模型对账、41 项 UI 数据/交互契约通过；真实浏览器 13 状态/详情与原页完全相同，移动宽度无全页溢出。旧 CSS scope 生成器漏括号导致媒体规则失效，迁移样式修复；旧生成链及所有消费者调用已移除，完整回归待跑。

AR-07 最终 a4c691f503：52/52 完整标准 release 回归 370.038s，仓库外运行通过；浏览器结果与原页一致，验收资料归档。下一项 AR-06 本地存储迁移演练。

AR-06：本地 SHA256 blob adapter、64MiB 构建缓存、manifest/copy/verify/restore/cleanup-plan CLI 和兼容 reader 已实施；10 项缺失/损坏/不可达/幂等/中断/同写入锁/缓存/清理测试通过。恢复 pending 阻止构建和其他管线 writer；准备固定提交空目录全量演练，旧 Git 原始快照保留。

AR-06 最终 593d858abe：53/53 标准回归 357.462s、封装包独立运行通过；空目录恢复七集合相等，缺失/损坏/不可达候选失败且 LKG/cursor 正常。26 份既有缺 raw 明示保留，不伪造恢复；成本与操作文档归档。继续 AR-08 发布观测与最终容量。

AR-08 最终实现 a4b4d263e：构建阶段/终态、激活/回滚终态与有界诊断轮转接入；真实 trap 失败/恢复/关闭/去重测试通过。增加新数据计数、递归源码+编译产物 provenance、GeoIP/MCP/最坏搜索/历史持有重载/maxRSS 容量采样。当前隔离 1x/5x/10x 采样中，完整回归待执行。

AR-08 最终 6a78846238：53/53 全量标准 release 359.087s、仓库外四入口与七集合相等通过。容量 1/5/10x C10 P95 14.3/24.6/35.4ms、loop P99≤19.5ms；10x稳态1.71GiB/进程峰3.03GiB，生产RAM/RTO待冻结。全部八项本地完成；候选保留于root dist-release，未推送部署；AR06远端DEFERRED。验收/维护/容量决策索引已归档。

发布准备：合并今日数据，唯一冲突为已移除的 price-ledger.rendered.html，保留 Astro 实现。9份标准输入显式最终切入，原迁移标记保留；七集合新旧/当前数据完全相同，DS0da7/dataThrough20261002。服务器root既有密钥可用，maasdeploy本地密钥不可用；正式CI有既有部署凭据，采用非公开候选预验后CI发布，避免并发切换。

2026-10-02正式上线完成：commit8ebc6b9e4e，RID rl_8ebc6b9e4e_0da7f0c0f2bc；本地和Linux CI均53/53，蓝绿/四入口/旧游标/真实代理链/线上浏览器通过。完整证据、资源边界及回退见 docs/architecture/refactoring-2026-10/release-2026-10-02.md。远端存储DEFERRED。


## 2026-10-29 数据/代码解耦
- 开始实施已同意方案，读取存储迁移、标准输入、公共合同与构建协议。
- 完成工具/依赖盘点；生产连接与对象桶准备方式已异步询问，尚未得到答案。
- 尚未改生产、停止原 writer、删除 Git 数据或迁移账号 SQLite。

用户选择现有服务器 PG，并明确暂不使用对象存储；方案已同步。

已完成生产隔离基础设施：复用 PG18 main，不安装/重启；新增 maasdata peer 账号与 maas_data 独立库（连接上限4，work_mem4MB），创建 shared/data-store/{blobs,backups,reports} 0700。现有应用/写入/调度未切换。部署脚本 ops/provision-data-store.sh 已应用成功。
本地8项真实PG专项通过；首次全量因历史 NUL 失败，已保留为 payload_json 无损文本并补测；192057逻辑文件全量重跑 session88255，独立DB maas_shadow_drill、blobs在/private/tmp/maas-decoupling-20261029。

真实输入全量影子导入成功：192057逻辑文件，178489个新内容对象；事务提交与结构化payload/原始字节验证通过。原文独立复制5341唯一对象、783493910字节，逐对象校验0失败，既有缺原文26份显式保留。开始pg_dump→空库→空文件目录恢复及七集合对账。

pg_dump→空库→空目录恢复通过：192057文件/310270867逻辑字节；原exporter七集合SHA和datasetVersion ds_3622dedc逐项相同，耗时226.54s（迁移恢复演练，不是日常发布耗时）。报告归档至docs/architecture/data-code-decoupling-2026-10-29/parity.json。

数据库直读第一次 canonical 对账发现仅 status.priceStreams 顺序不同；补 source_order 元数据后 datasetVersion一致。进一步文件bytes对账发现嵌套JSON对象键序仍导致4个文件hash不同，未激活此候选。现改为JSONB查询表示+同事务有序JSON表示，reader禁止旧库未补齐时导出；全量backfill已完成，正在做严格7文件bytes+内存复核。

PG专项已扩至14项（含端到端固定样本、不可达历史事实证据时间、源顺序、有界解码键状态），传输4项、标准输入6项、旧导出20项均通过。影子数据包与代码/config哈希已上传；开始限额服务器导入session待记录（root命令不切换应用）。

基础代码已提交 dff5b929d3（分支codex/data-code-decoupling-20261029），原有站点修改未提交。新提交SHA运行完整独立CLI成功：baselineByteParity=true，21.28s，子进程峰1404MiB（Mac；不代替Linux预算）。候选未激活。服务器影子导入session98656仍运行，unpack已加内存/CPU限额。后续需在独立工作树实施C网页运行，避免改动现有未提交Layout/指南内容。

2026-10-29：完成服务器影子导入、Linux候选对账和真实备份恢复。C运行时分支完成本机回归；仍需独立运行包、Linux SSR部署适配、7周期、writer切换。无对象存储，无Git历史重写。完整状态见 docs/architecture/data-code-runtime-2026-10-29.md。

独立代码包180489902字节、不含业务归档，从/private/tmp运行18项SSR验收通过。C仍待Linux/蓝绿/回退和7周期；生产writer未切换。

2026-10-29 用户明确要求正式切换。现网已由旧静态站切到runtime/ad91dc2ce9的blue槽，数据来自shared/public-data/v1与PG。Linux18项SSR验证通过，实际切流→回退旧站→再切新站通过；旧绿槽签发的cursor在新蓝槽200。首次因静态favicon目录权限自动回退，修复仅public client目录权限后通过。当前应用RSS约247MiB。独立采集容器已构建，非root+Chromium sandbox+专用PG peer连接通过；初次数据缓存prepare已完成。下一步更新固定writer代码（schema7、恢复mutable、setgid目录继承），跑validate和真实update，然后启用新的daily/weekly/code工作流并移除Git当前树的运行数据；未完成部分不能标done。

2026-10-29 writer切换候选：71项PG/发布/恢复/工作流测试通过。独立run日志入writer_run_logs，不混入业务inputVersion，保持离线重放幂等；schema7记录最新完整采集head，素材准备失败不丢已入库事实。root固定SSH入口、容器凭据stdin、FD安全安装与候选权限核验已复核；尚待服务器完整validate和真实日更。

2026-10-29 切换继续：PR12合入18909b33c1；PR13合入19da9a1000，200314份运行文件/生成投影已取消Git当前树跟踪，仅保留34份手工模型配置/稿件和20份站点手工配置/平台内容，本地原文件保留。首次writer导入完整提交后，导出子进程与父进程堆叠触发1.5GiB容器OOM，未发布半成品；改为独立ingest进程释放内存，完成带日志入库18项回归，并修复日志覆盖raw manifest变量。固定提交0b9ac75dfd在服务器严格7文件对账+18SSR通过（1m16s，SSR RSS322306048），不发布。首次代码CI等待服务器锁时SSH Broken pipe，未切换；现有root助手改为独立systemd任务+SSH保活，22项部署回归通过。254份历史run日志已从验证归档恢复writer缓存。新代码CI40893971585执行中；真实日更仍待验证。

2026-10-29 继续：61项读取/协议/PG回归通过，PR14合并c200d6653d，CI40899202962通过，生产代码部署40899367511成功。Git HTTPS直连失败，按用户提供的127.0.0.1:7897代理推送成功。首次真实日更40894724146安全中止，pending不存在，采集检查点in_5ba680...保留；启动受原容器权限限制的maas-checkpoint-recovery.service入库，不发布，之后再验证完整更新。

2026-10-30：代理推送有效。PR14 c200d6653d部署成功，旧来源检查点in_5ba680...入库成功，255历史run日志已保存。真实日更40902444706完成68来源67成功、价格9/10成功（15变化）、榜单3/3、翻译0pending、864记录门禁、12278事件/23601证据价格门禁，但最终ingest触及旧45分钟限制，未发布。完整输入in_f63e1cafd51791c21d6b92b5561c786b66a6bc972593eb9151f31c6c913197d3且无pending。PR15提高受限任务预算90/95/100分钟，PG CI40908541517通过、部署40908738377成功（de2271a6a813c9acaff801ce3404399f9857c2e2）；根固定助手已同步。maas-final-checkpoint-recovery.service正在入库最终检查点，日志final-checkpoint-recovery.log；随后仍须rebuild发布、旧cursor/无重启核验、最终备份和文档提交。不能称全部完成。

2026-10-30 最终发布通过：PR16合并4006c9b095，CI40910840266及部署40911039650成功。最终完整输入in_f63e1c...恢复入库成功；rebuild任务40912729486发布ds_e496c4...成功，导出68.46s。代码4006c9b095/PID3150279发布前后相同，旧cursor同版本同ID，四公开路由200，lastReloadError=null。正在最终备份，原始完整采集并非一次成功且仍有全历史扫描瓶颈；持续异机调度/7周期观察未完成。

最终服务器备份cutover-final-20261029T163617Z完成并生成SHA。下载约495MB至现有本机私有备份目录被自动审批拒绝，要求用户明确授权具体载荷和目的地；未重试绕过。其余生产切换与最终数据发布已完成，最终异机副本待批准。
