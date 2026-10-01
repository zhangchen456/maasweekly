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
