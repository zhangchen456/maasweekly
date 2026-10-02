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
