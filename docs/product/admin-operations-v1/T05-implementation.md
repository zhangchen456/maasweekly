# T05 信源质量与日常任务监控

2026-10-04，本地交付。入口 `/admin/sources/`、`/admin/tasks/`；未部署、未执行生产抓取/发布、未安装新调度，保留T01–T04及既有工作区改动。实现合同见 `docs/contracts/admin-api-v1.md` T05。

## 实施前执行链核对

| 链路 | 实际执行与已有记录 | T05接入 |
| --- | --- | --- |
| 每日05:00北京时间 | daily-update现有schedule，抓取sources→sync→prices（部分失败沿用）→价格解析回归→LLM daily→再sync→leaderboards→配图 | 复用RunJournal；sources/prices/leaderboards已有来源结果。原流程未迁入editorial worker |
| 数据归档 | input manifests、snapshots、record/price revisions；data/pipeline-runs与price-runs保存commit point、版本、source_states及sources；旧价格记录只有created/committed与来源时间，缺started | 采集固定命名空间，仅提取白名单。旧时间保留null；离线重放outcome=not_run，不证明新的在线抓取 |
| 公开投影 | project-site-data→skill→export-public-data→export --check→数据commit | 预定义CLI wrapper记录projection/export/check；archive提交不是校验通过、projection不是发布 |
| 构建发布 | 数据commit SHA→reusable release-deploy候选检查→build-release全量门禁→deploy-release上传激活→四入口online verify | build-deploy记录执行结果，publication=unknown；只有固定release-verify成功表示completed，outputVersion=期望RID。失败可发生在构建或激活，摘要不臆断子阶段 |
| 旧周报 | weekly-update周一09:00 schedule实际mode=full；手动aggregate/import/full→sources→sync→LLM weekly --all→import→projection/check→commit→release | wrapper记录已执行summary/import/sync。aggregate不部署；缺LLM key的wrapper结果not_run。既有定时保持 |
| T03专业周报 | 私有账号库editorial_runs、独立worker、人工审核、publication/compose | 直接读取任务表安全投影与原状态，不复制正文/提示词/费用配置，不把任务成功当出版；管理动作返回原周报工作台 |

实际仓库采集验证：49条归档运行、71个来源（包括注册表、榜单内部ID及未映射旧key）；这是仓库已有记录范围，不是实时生产采集声明。平台映射缺失显示unknown，内部key显示unmapped。相同注册表sourceId的多个URL别名保守合并，失败端点不被成功端点隐藏。

## 采集与运行

新增 `scripts/monitor-record.py`（固定动作、继承原命令exit code、没有shell自由输入），`scripts/monitor-collect.py`（只读注册表及固定journal/stage回执，确定性每100运行一个包），`services/agent-api/src/monitor-cli.ts`（受控本地inbox导入）。已有三个Actions流程补wrapper与always脱敏artifact，不修改调度、不向后台提交生产secret。artifact保留14天，collector日志披露无可靠记录的跳过数。没有安装自动传输/拉取artifact或定时导入器。

本机采集不运行抓取：

```sh
python3.12 scripts/monitor-collect.py --output /private/tmp/maas-monitor-inbox
# 如有私有stage receipts，可显式加 --stages /absolute/private/stage-directory
# 运维终端加载既有账号库配置（本地验收应使用临时库）后逐包导入：
MAAS_MONITOR_INBOX=/private/tmp/maas-monitor-inbox npm run monitor --prefix services/agent-api -- import batch_HASH.json
```

inbox必须真实绝对目录；macOS `/tmp`是别名，CLI应使用`/private/tmp`。不能传日志路径或任意文件名。目录归受信collector/运维帐号管理，后台API进程无inbox访问需求。受控artifact由运维核对GitHub仓库、run和attempt后投送此目录，再运行CLI；未实现网络摄取或凭据读取。不要直接导入原journal（含rawBackups/URL/argv等），必须用collector白名单投影。

wrapper预定义动作：diff-sync、site-projection、public-export、public-validation、archive-validation、price-validation、daily-summary、weekly-summary、weekly-import、build-deploy、release-verify。build-deploy仅接受环境中40位CANDIDATE_SHA，release-verify仅接受严格RID；它们是原工作流命令适配，不是后台重试动作。MAAS_MONITOR_OUTPUT未设置时直接保留原命令行为；设置时先原子保存running回执再执行，最后原子保存终态。采集到未结束回执标needs_review（结果未知），不编造结束时间。journal中断快照独立保存以免后续recover覆盖。

## 判断与异常处理

抓取失败和解析失败：新价格runner保存failurePhase，旧诊断只能判fetch_or_parse_failed；原staged_fetch明确schema_failed时显示parse_failed。部分成功不会伪装为全部成功。原normalize_and_validate的rejected结果（NG-01～NG-05）增加固定validation/rejectedCount，仅引用已有规则；source coverage=partial、队列validation_failed，不重新定义异常价格规则。归档/公开校验失败引用原退出结果和受控运行入口；未接入按事实ID拆出的重复事件/证据缺失项目，不根据页面文本猜测。

队列支持确认/处理中/忽略/解决，必填原因、expectedVersion、Idempotency-Key；业务结果/审计/命令记录同一事务。来源恢复需后续同source完整覆盖与真实新成功；任务恢复需同kind，校验/发布故障还分别要求passed/completed。忽略不改变信源健康。过期是依据默认48小时预算计算的实时健康提示，不是新的上游异常事实；首版队列保存已报告失败/覆盖/校验/中断，不新增定时过期事件。

所有后台内容运行时鉴权读取，静态壳无私有数据、localStorage无后台数据，错误只固定脱敏摘要。详细诊断入口是白名单GitHub run链接；没有链接则说明受控终端按现有协议查原任务。重试全部保持禁用；T03已有权限/预算/幂等约束的阶段动作从周报工作台使用，抓取恢复按原 --recover/--retry-failed 协议人工执行，绝不隐式调用发布。

## 迁移、回滚与生产配置

服务启动/导入CLI幂等加法migration5，与T01统一迁移表。新增5张私有表和按运行、来源、队列排序的索引；归档运行与观察不覆盖，重复/冲突整包事务回滚。部署前按现有SQLite backup备份（不能只复制WAL主文件）；回滚停止导入与管理写入，保留monitor表/回执/审计，不DROP。尚未验证生产大库迁移、备份恢复与文件权限。

接入生产需要：部署本次API/静态页；审核Actions候选变更；设置CI私有MAAS_MONITOR_OUTPUT（候选已用runner.temp）；建立受信artifact→固定inbox投送与运维执行导入步骤；为导入CLI沿用账号库/secret配置并隔离权限，不赋予API生产抓取/SSH密钥。本次没有创建token、调度、生产连接或自动导入。真实GitHub artifact权限与跨机器运维过程需要后续授权验收。

## 尚未覆盖

历史GitHub运行/构建/发布没有已有结构化时序，本次不联网回填；完整外部实时排队/长任务heartbeat、旧价格抓取/解析的精确原因、hard kill未留下回执的执行、配图、skill构建内部子步骤、数据commit、未被wrapper单独记录的build-release子校验无逐项记录。build-deploy为现有组合步骤，阶段不拆假记录。T03具体来源映射、旧周报正文人工写作、按异常事实ID的价格/重复/证据问题细分未接入。邮件、备份、恢复与服务健康仍留给T06，没有提前实现。

来源查询最多500、单来源历史读取最多501、运行/队列25–100分页；collector每100运行一个包、单包4MiB、单输入8MiB。暂未归档私有monitor表；大规模历史查询需先测量，不承诺生产SLA。schema/run冲突应核查采集器版本/原执行，不删除旧记录来绕过冲突。

## 验收

已完成本地验收。先完成完整构建/API回归，后续来源时间取最大值与UI提示调整仅复验相关专项和浏览器；没有把真实生产或GitHub传输过程算作已验收。

| 检查 | 实际结果 |
| --- | --- |
| `npm run build --prefix services/agent-api` | 最终通过，公共合同生成检查通过 |
| `npm run test:compiled --prefix services/agent-api` | 146/146通过；含当时12项T05与T01–T04/账号/Plus/公开REST回归 |
| `node --test services/agent-api/dist/tests/admin-monitor.test.js` | 最终12/12通过：加法迁移/回滚、成功/partial/full failure/unchanged/not_run/unknown/stale、抓取/解析、重复包/重复run/冲突原子回滚、权限/CSRF/版本/审计、忽略不修复、同来源后续核验、校验与执行分离、分页、双连接/重启、T03实时投影不泄露config/payload/error |
| Python3.12 `unittest discover -s tests -p test_monitor_collection.py` | 9/9通过：白名单/脱敏、旧时间未知、离线重放、仅引用原校验、确定性重复、symlink拒绝、别名失败保留、原退出码、固定线上验收动作（mock，不联网）、中断快照与终态分离 |
| `test_pipeline_runtime.py` / `test_price_archive.py` | 18/18、56/56通过，离线快照/恢复/幂等与价格归档回归 |
| `python3.12 tests/test_pricing_extractors.py` | 八家×HTML/Markdown及GLM改版fixture通过；无生产抓取 |
| `test_workflow_release_contract.py` | 18/18通过，原数据先提交、投影门禁、构建发布合同未改变 |
| `python3.12 pipeline/scripts/export-public-data.py --check` | 通过：7文件，既有数据版本ds_06271d…、dataThrough=2026-10-04 |
| page-models TypeScript检查 | 通过，包含admin-monitor-client |
| `npm run build --prefix site`，最终site目录`npm exec -- astro build` | 通过，47459页，含两页noindex私有壳；原归档与价格门禁通过 |
| `python3.12 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser-t05-delivery` | 最终16流程，0页面错误；真实临时SQLite/HTTP、CLI采集/重复、未知/过期/失败/无变化、忽略不治愈、解决核验/审计、关联单运行入口、T03实时任务、1440/390无横向页面溢出、实际注销后迟到响应清空、Free/Plus隔离；T01–T04完整闭环保留 |
| 仓库真实回执采集→临时库导入→重复导入 | 71来源、49运行；prices34/sources3/leaderboards3/source-normalize6/daily-summary3；24条开始时间未知；重复结果imported=0/duplicate=true |
| `git diff --check`、Python AST、run-all-tests shell语法 | 通过 |

本机默认Python3.9缺yaml且无法跑所有仓库依赖，改用已安装Python3.12；HTTP/Chromium按沙箱许可仅开放本机临时端口。一次Astro命令从根目录运行失败，改回site目录后通过并清理误生成根缓存；采集联调识别注册表null平台与共享sourceId别名，分别显示unknown并保守合并。这些问题已修正，不影响生产。

新增代码：admin-monitor.ts、monitor-cli.ts、tests/admin-monitor.test.ts；scripts/monitor-record.py、monitor-collect.py、admin-monitor-browser-flow.py；site/src/lib/admin-monitor-client.ts、admin/sources/index.astro、admin/tasks/index.astro。扩展admin-http.ts、API package.json、AdminLayout/admin.css/page-models、admin-browser-smoke/run-all-tests、pricing/runner.py与run_protocol.py、原三份Actions，以及本交付记录/统一合同/development-order/ops README。没有改生产激活器和T06实现。

最终证据：`/tmp/maas-admin-browser-t05-delivery/browser.json`、monitor-sources-desktop.png、monitor-sources-mobile.png、monitor-ignored.png、monitor-tasks-desktop.png、monitor-tasks-mobile.png、monitor-task-detail.png及既有T01–T04截图；`/tmp/maas-t05-build.log`、maas-t05-api-final.log、maas-t05-tests-final.log、maas-t05-collector.log、maas-t05-pipeline.log、maas-t05-price-archive.log、maas-t05-extractors.log、maas-t05-workflow.log、maas-t05-public-check.log、maas-t05-client.log、maas-t05-site.log、maas-t05-site-final.log、maas-t05-browser.log、maas-t05-collection.json。临时账号库、inbox/outbox、API/代理/Chromium和无用中间文件已清理，保留最终证据。

演示重跑上述浏览器命令，或在已配置的隔离本机API进入 `/admin/sources/`、`/admin/tasks/`；没有常驻演示服务。截图是隔离样例，真实仓库导入记录仍只代表已有档案，未进行生产实时接入。

## D01 联合链路补充（2026-10-04）

T03现在直接只读monitor_observations/monitor_runs，按同sourceId、统计窗口attemptAt、观察与公开数据版本建立覆盖依据；不使用当前全局health倒推历史，也不依靠异常被忽略/解决来放行。T05 API、导入合同与schema不改动。T03需要先导入可信回执，显示相关失败/投影冲突后确认partial，依据变化重新冻结审核。详情与修复证据见acceptance/d01-fix-20261004及统一合同D01段；原T05“具体来源映射未接入”是该阶段历史限制，此处补齐只读联合核验。
