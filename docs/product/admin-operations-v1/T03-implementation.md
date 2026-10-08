# T03 实施与恢复交接

2026-10-04；本地开发与隔离验收。未部署生产、未调用付费模型、未发送真实邮件、未安装服务/定时任务。保留工作区原T01/T02与发布配置改动。

四个切片均在同一任务内推进：人工闭环、持久worker/模型、核验预算恢复组合、真实历史素材隔离演练。实际验收结果见本文末尾。专业正文唯一源为pro_content；统一briefing与个人组合explainer/comparison有独立入口和语义。

## 代码与入口

新增editorial-store/service/checks/model/worker、admin-editorial、pro-publication和专项测试。扩展AdminStore的无业务变化审计抑制（重复出版仍存幂等命令结果）、admin-http精确正文限制、pro-store事务内draft/transition/compose、pro-cli统一出版校验。无第二套账号、CMS或队列。

页面：`/admin/weekly/`创建与列表；`/admin/weekly/detail/?id=weekly-2026-09-28`五步工作台；`/pro/weekly/?id=editorial-2026-09-28-briefing`统一周报读者入口；`/pro/`仍管理个人范围和组合报告。页面只含静态壳，私有正文经API鉴权；转义文本禁用HTML和危险链接。编辑器首版为内容包JSON，旁边显示公共预览与核验问题。

后台写入遵循统一合同，详见docs/contracts/admin-api-v1.md T03。存储冻结素材与不可覆盖revision；修改或重冻失去批准。人工六项清单绑定revision/hash。当前证据撤回/版本变化阻止出版。整包正式导入、审核、出版与审计一次事务，任何失败整包回滚；重复出版不增加正式版本或业务审计。

## 配置与worker

构建API后启动原账号API；它自动迁移。worker单独进程，与API共享同一个私有MAAS_ACCOUNT_DB/MAAS_ACCOUNT_SECRET及有效PUBLIC_DATA_ROOT。

```sh
npm run build --prefix services/agent-api
# 原有环境配置已经加载后：
npm run editorial:worker --prefix services/agent-api -- --once
npm run editorial:worker --prefix services/agent-api
```

`--once`领取并处理一个阶段；常驻每秒查询一次，SIGTERM停止领取并等待当前请求完成（最长配置180s）；SIGKILL后过期租约进入核查。独立worker不发送邮件、不审核、不出版。

`ops/maas-editorial-model.mock.json`为确定性模拟配置；`ops/maas-editorial.env.example`及`ops/maas-editorial-worker.service`仅候选。MAAS_EDITORIAL_CONFIG绝对路径读取配置，期次创建时保存快照。默认mock且付费关闭。真实接入将adapter改openai，分别填入已确认支持JSON模式/max_completion_tokens的三个模型ID，可选reasoning low/medium/high；再设置受控环境OPENAI_API_KEY与MAAS_EDITORIAL_ALLOW_PAID=true。模型支持参数、真实质量、费用和限流须在授权预算下验证，开发没有调用。

价格为所有角色的保守公共费率上界；不同角色报价应选择最大input/output费率，不可用最低报价伪装金额上限。price字段含currency=USD、inputPerMillion/outputPerMillion、updatedAt及source，缺报价用null。每run为最多三次尝试预留估算，失败/取消不释放，计入整期预算；未知价格只约束30次尝试、输入字节上界保守视作token上界、max_completion_tokens和运行时长，不声称金额绝不超支。实际usage按返回token与配置费率计算费用；不是供应商账单对账。

供应商实现依据官方文档 https://developers.openai.com/api/reference/resources/chat；直接fetch固定官方端点，不自动SDK重试，无shell/数据库/任意URL工具。提示词版本editorial-v1在editorial-model.ts，三阶段输入只含冻结证据/选题/上游编辑产物，不含用户资料。模拟器仅验证流程，质量与价格显示为未验证/未知。

## 故障与恢复

每阶段单独任务，prepare为确定性计数；curate选择冻结ID，analyze生成包，verify独立辅助审稿与程序问题。HTTP返回runId即可结束；后台刷新读取状态。输入超限会截取冻结材料的一部分，任务记录保留实际输入；完整冻结素材仍可分页查看，切勿声称全量分析。

仅429明确拒绝自动重试，总三次。网络/超时/5xx/用量未知或服务重启租约过期，进入needs_review，不盲目重发。界面核对供应商记录后填写executed/not_executed、材料及累计已知费用（未知null），保存核查，再手动触发该失败阶段；失败之前的成功阶段复用。同输入未知状态即使取消也不能直接重跑。取消增加fence；迟到结果不能覆盖编辑，已知费用仍保存。供应商执行未知的费用不是0，保留预留与未知说明。

分析期间有人保存编辑，旧任务结果不覆盖新revision。稿件核验失败记录输出/问题进入needs_review，需编辑修正，不能直接出版。Schema失败为failed。审核未完成、旧hash、当前证据撤回均409；刷新重新核对。

出版成功但组合失败，publication保持pending；只重试compose。执行前查看已有/可新建报告数；queueMail默认false，开启也只为专业邮件开启者的新报告入队。已有报告永不靠重跑补发。状态仅显示实际pending/sent/failed/review/cancelled与创建时间范围；sent文案是供应商已接受。未添加直接重置或发送。

## 迁移、备份与回滚

上线前先用SQLite一致性backup备份账号库，不单独复制WAL主文件。API/worker启动自动进行幂等migration3，共6表与索引，失败整事务回滚；T01迁移表统一记版本，原账号/权益/反馈/专业内容保持。冻结材料都存私有账号库，不在release目录；沿原账号备份权限策略一起备份。临时库验证双连接、重启恢复与既有数据保留。

候选nginx只把匹配`/api/admin/weekly/ID/revisions`的location放宽1m，其他admin16k；API同样限制，测试1MiB以上413与其他端点16KiB。尚未加载真实nginx。

回滚前停止worker并暂停编辑/出版/组合写入，再按原发布回滚流程切应用；保留新表、快照、审计和费用历史，不DROP。旧pro CLI会绕过本工作台版本语义，回滚期间禁止旧CLI管理写。恢复应用后检查needs_review与供应商状态，不能直接批量改queued。生产迁移、systemd/nginx权限与备份还原需要后续部署授权验证。

## 验收记录

T03四个切片已完成本地交付。最终页面与专项验收无付费模型调用；真实模型质量与账单费用尚未验收。统一检查入口已有test:compiled和admin-browser-smoke，本次将editorial.test加入API脚本，并将历史演练helper接入同一后台浏览器脚本。

| 检查 | 实际结果 |
| --- | --- |
| `npm run build --prefix services/agent-api` | 通过，公共合同生成检查通过 |
| `npm run test:compiled --prefix services/agent-api` | 121/121通过，含当时10项T03；随后新增仅测试的迁移失败和更正/组合故障场景，专项最终12/12通过；没有重复执行无关全套 |
| `node --test services/agent-api/dist/tests/editorial.test.js` | 最终12/12通过：周一/跨月、零证据、冻结历史、迁移失败回滚、两连接/重启、任务去重/三次重试/预算拒绝、取消/未知执行核查、迟到费用、审核失效/当前撤回、整包故障回滚/重复审计、组合故障/更正读取、HTTP大小/Plus隔离 |
| `npm run test:mcp:compiled` / `test:mcp:real:compiled` | 13/13及8/8通过，公共MCP真实数据回归无变化 |
| `node services/agent-api/node_modules/typescript/bin/tsc --project site/tsconfig.page-models.json` | 通过，含两个新客户端 |
| `npm run build --prefix site`，后续UI调整在site目录`npm exec -- astro build` | 完整构建通过，47456页；最终再次构建含输入数和覆盖展开、窄屏样式 |
| `python3 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser-t03-delivery` | 9流程通过，0页面错误；含真实创建→冻结→四阶段独立worker→人工编辑r2→六项审核→出版→组合→Plus全文/游客预览，桌面1440与窄屏390无横向溢出 |
| Python3.12 `unittest discover -s tests -p test_release_activation.py` | 49运行、48通过、1既有跳过；候选精确revision1m与其他admin16k通过 |
| `git diff --check`、激活器shell语法、Python语法 | 通过；Python编译缓存在/tmp，完成后清理 |

历史演练：统计期末2026-09-28，北京时间窗口2026-09-21至09-28；有效数据版本`ds_06271d209e3d343f108455222e239e0cbc323f7e42595ba246c0b28b62923c22`。8条真实历史引用核对ID/URL/观察时间与冻结快照一致，稿件明确区分已观察事实、分析和待核对，不声称已完成官方生效时间、价格/性能或商业质量评测。冻结hash/revision/outputHash/正式contentRefs及独立任务记录在weekly-evidence.json。全部模型阶段为确定性模拟，费用报价未知，没有真实费用支出。

证据保留：`/tmp/maas-admin-browser-t03-delivery/browser.json`、`weekly-evidence.json`、`weekly-approved.png`、`weekly-published.png`、`weekly-plus.png`、`weekly-preview.png`、`weekly-mobile.png`；日志`/tmp/maas-t03-api-last.log`、`maas-t03-editorial-delivery.log`、`maas-t03-mcp.log`、`maas-t03-mcp-real.log`、`maas-t03-routes.log`、`maas-t03-site-build.log`、`maas-t03-site-delivery.log`和`maas-t03-browser-delivery.log`。临时账号库、outbox、API/代理/Chromium已由脚本销毁。演示入口需再次运行脚本或使用隔离环境，未留下持久在线服务。

初次浏览器与构建同时运行导致静态页短暂不存在；后续等待最终构建完成再验收。一次夹具未填必填预算，已修正。人工检查发现长JSON溢出，修正并加入桌面/窄屏宽度断言。中间截图/log清理，保留上述最终证据。

尚需真实环境验证：供应商各角色模型参数/JSON支持、真实稿件质量与人工编辑工时、token/费用及未知执行恢复对账；生产账号库迁移/一致性备份恢复、shared权限、systemd候选运行与真实nginx加载；正式内容对运营范围的覆盖质量与真实授权邮件供应商接受/收信。当前没有生产上线或收费质量验收声明。首版编辑器采用JSON包、阅读页采用安全转义文本；没有富文本编辑器、自动选期、补发、自动发布或调度器。

## D01 后续修复（2026-10-04）

独立验收发现T05同窗口已知失败未参与T03覆盖判断。已接入只读同source/window/版本关联、失败与投影冲突显示、partial显式依据确认和审核/出版依据hash复核；无新迁移。旧期次需重新冻结并审核。修复证据与哈希另存acceptance/d01-fix-20261004，原独立验收不覆盖；本段不是独立重新放行声明。
