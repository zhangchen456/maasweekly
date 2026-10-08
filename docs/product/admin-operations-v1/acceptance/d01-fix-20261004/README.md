# D01 开发修复交付

2026-10-04（Asia/Shanghai）。原独立验收目录independent-20261004完整保留，绑定原snapshot SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`。开发新证据只存本目录；由独立验收方定向复验后判定是否放行。

已核对D01夹具适用：真实窗口内google-vertex-changelog素材，2026-09-27失败、监控missing/degraded而公开sourceStreams清空。原脚本未修改，使用`node --input-type=module < .../source-publication.mjs`重放；现于prepare返回409 monitor_coverage_conflict，日志original-repro.log，exit1是预期的禁止normal结果。

## 修复与运行

新增editorial-coverage.ts只读关联；修改editorial-service/admin-editorial及工作台客户端/页面。依据精确sourceId、窗口内attemptAt、运行observedAt和input/outputVersion关联。明确不同ds_版本、窗口外、无关source、not_run被排除；非公开版本命名空间/null标unknown而不假装不相关。最新unchanged/full成功可证明本窗口恢复，忽略异常操作不会改变读取的来源事实。

工作台展示相关来源失败/投影冲突、数据版本、观察/尝试时间及hash。normal不允许已有相关覆盖限制；partial/failed需人工独立确认当前hash并填覆盖说明。冻结快照含monitor依据；审核/出版重新比较当前同窗口公开来源与监控依据，有变化409，必须重冻/改稿/新审核。旧期次缺依据也要求重冻，不静默认可旧审核。已经出版的正文不自动撤回或修改。

没有新迁移；复用editorial_issues.coverageInfo和inputHash以及migration5的只读表。无T05表时显示monitorAvailable=false，不编造失败；部署前仍需按原协议一致性备份，导入可信collector回执。回滚暂停编辑/审核/出版与monitor导入，保留原库，不删除JSON或表。无法检测未导入、无结构化记录的生产抓取，不能当作已完成真实采集同步。

## 验证与证据

- API构建、page-models TypeScript、git diff --check通过。
- `node --test .../editorial-coverage.test.js .../editorial.test.js .../admin-monitor.test.js`：25/25，api.log。后续将同窗口公开投影和有界查询补入依据，最终D01 HTTP专项1/1，coverage-final.log；无需重复其他无变化套件。
- 实际HTTP覆盖原normal拒绝、已有批准后监控/公开投影变化阻止出版、提交审核后新失败阻止批准、确认partial完整出版、无关/历史/不同公开版本/not_run不改变依据，以及unchanged/full后恢复normal。
- site目录`npm exec -- astro build`通过，47465页，site.log。
- `python3 scripts/admin-browser-smoke.py --focus coverage --output 本目录/browser`：5流程、0页面错误，browser.log及browser/browser.json。真实CLI导入T05失败、真实HTTP/SQLite；normal与未确认partial拒绝，勾选限制后四个mock worker阶段、编辑/六项审核/出版、Plus全文/游客预览、桌面/390px检查通过。所有测试模型均为mock，未验证真实模型质量。
- 新test接入API test/test:compiled；新增focus coverage使独立验收可只复跑联合流程，不运行T08。

隔离账号库、监控inbox/outbox和进程由浏览器脚本销毁，保留截图与JSON。没有生产部署、真实邮件/消息、付费模型、支付操作或调度变更。T08继续挂起。

实际改动与SHA256见files.json；不提交Git，避免混入其他交付改动。文件hash绑定源码/合同/交接，不把Git基线当作本次交付版本。未改动admin-monitor.ts或其他任务业务逻辑。
