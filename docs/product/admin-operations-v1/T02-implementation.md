# T02 实施与运维交接

2026-10-04。本地实现，未部署生产、未发送真实消息、未接支付，未开发T03。保留工作区原有T01及发布配置改动，未提交Git。

已核对T01-implementation.md和实际AdminStore/AdminLayout/admin-client；T01已完成并可用。本任务复用其鉴权、分页规则、command事务、幂等、版本冲突、审计和页面事件，仅抽出Plus事务内授权方法，没有新增第二套基础框架。统一合同见`docs/contracts/admin-api-v1.md`的T02章节。

## 实际改动

- 新增后端`admin-operations.ts`（migration 2、签名分页、输入校验）、`admin-users.ts`、`admin-feedback.ts`、`admin-cli-command.ts`；扩展既有`admin-http.ts`路由与总览待处理数量，`admin-store.ts`导出既有时间校验。
- `pro-store.ts`将有效权益判定抽为共用纯函数，并提供grantInTransaction，保留原grant及用户API语义。AccountStore.logoutAll/ProStore.revoke本身不启动事务，直接在command内复用。
- `pro-cli.ts`、`feedback-cli.ts`管理写入接共享服务/版本/审计；保留原list/export/status与grant/revoke入口，新增私有detail/user/verify入口。旧写命令缺expected-version明确失败。
- 新增4个静态页面：`/admin/users/`、`/admin/users/detail/?id=...`、`/admin/feedback/`、`/admin/feedback/detail/?id=...`及运行时`admin-operations-client.ts`。更新AdminLayout导航、状态数量标签和样式。私有数据无静态注入、无浏览器持久存储，注销清空私有DOM，409要求重新读取。
- 新增`tests/admin-operations.test.ts`并接入package.json现有test/test:compiled；扩展既有`scripts/admin-browser-smoke.py`的T02流程，继续由run-all-tests非quick门禁调用；page-models类型检查纳入新客户端。

## 迁移与回滚

备份账号SQLite（在线用SQLite backup，不单独复制WAL主文件）。使用原MAAS_ACCOUNT_DB/MAAS_ACCOUNT_SECRET环境，构建API后启动服务或运行`npm run feedback --prefix services/agent-api -- list`，自动执行migration 2。不用生产数据在本地试跑迁移。

新增4表与索引，旧账号/会话/权益/反馈不删除；旧resolved回填legacy，不伪造验证。新反馈首次管理写入建立ops，读取按triage/version=0。迁移失败回滚，可修正后重试。新表随账号库一并备份。应用按既有发布回滚流程回退，保留表和历史数据；**回滚期暂停所有管理写入与旧CLI**，旧版没有新版本/审计门槛。不要DROP表。未执行生产数据库升级与nginx加载。

## CLI 操作

先读当前版本，写入必须显式expected-version。冲突重新检查对象，不自动覆盖；超时重试保留key和完整参数。环境secret只放原配置，不放命令参数。

```sh
npm run pro --prefix services/agent-api -- user EMAIL
npm run pro --prefix services/agent-api -- grant EMAIL 2026-10-04T09:00:00+08:00 2026-11-04T09:00:00+08:00 OPERATOR '服务期开通' --expected-version 0 --key UNIQUE_KEY
npm run pro --prefix services/agent-api -- revoke EMAIL - - OPERATOR '撤销原因' --expected-version 1 --key ANOTHER_KEY
npm run feedback --prefix services/agent-api -- list
npm run feedback --prefix services/agent-api -- detail FEEDBACK_ID
npm run feedback --prefix services/agent-api -- status FEEDBACK_ID investigating '公开说明' --actor OPERATOR --reason '已复现' --expected-version 0 --key UNIQUE_KEY
npm run feedback --prefix services/agent-api -- verify FEEDBACK_ID '{"kind":"code","artifactRef":"COMMIT_OR_URL","releaseRef":"RELEASE_ID","result":"passed","environment":"online","note":"实际线上验证说明"}' --actor OPERATOR --reason '核验' --expected-version 1 --key VERIFY_KEY
npm run feedback --prefix services/agent-api -- status FEEDBACK_ID resolved '用户公开处理说明' --resolution-type code --actor OPERATOR --reason '处理完成' --expected-version 2 --key RESOLVE_KEY
```

手工授权不会伪造支付或开启邮件。revoke无旧手工期时用now至now+1ms建立revoked标记，保留公测数据、取消pending专业邮件；grant可能恢复公测优先。网页会话和专业凭证分别撤销。所有新解决必须先追加验证，代码问题要求发布版本与线上验证；同毫秒下最近failed会覆盖passed，重开后需新验证。

## 验收与演示

最终验收已通过。演示由隔离浏览器脚本自动创建临时库、同源本机代理、文件outbox及独立Chromium；不会接真实邮件供应商，阻断外部浏览器请求。结束销毁账号库、outbox与进程，截图/报告作为交付证据保留。页面入口如上；本地开发沿用原Astro代理及与访问源一致的MAAS_ACCOUNT_ORIGIN。

```sh
npm run build --prefix services/agent-api
npm run test:compiled --prefix services/agent-api
node services/agent-api/node_modules/typescript/bin/tsc --project site/tsconfig.page-models.json
npm run build --prefix site
python3 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser-t02-final
```

遗留限制：实际生产配置/迁移未验收；API发布版本仍沿用T01“未提供”。adminVersion只保护管理操作，非全账号修改版本。凭证详情最多100条（有效凭证原业务上限20），近30天事件为按类型汇总；审计、备注、验证提供分页入口。数千记录测试证明分页有界与筛选完整，不构成生产吞吐承诺。验证记录由运营输入，不等于自动检查真实发布；浏览器记录的发布/线上材料仅为隔离验收夹具。


## 最终交付状态与证据

**T02已完成本地交付。T01无本任务阻塞能力缺口。**

| 检查 | 实际结果 |
| --- | --- |
| `npm run build --prefix services/agent-api` | 通过，含公共合同生成检查 |
| `npm run test:compiled --prefix services/agent-api` | 111/111通过；8项T02测试含真实CLI、3000用户/3000反馈分页、权益组合、迁移失败回滚、两连接版本、业务/审计原子回滚、同毫秒验证顺序、重开、凭证与私有图片 |
| `node services/agent-api/node_modules/typescript/bin/tsc --project site/tsconfig.page-models.json` | 通过，包含两个后台客户端 |
| `npm run build --prefix site`；最终UI调整后在site目录`npm exec -- astro build` | 通过，最终47453页；4个新增页均为静态无私有数据壳 |
| `python3 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser-t02-final` | 最终8流程通过，0页面错误；真实用户检索/授权/截图/内部备注/公开回复/验证/解决、双窗口409、窄屏、普通所有者结果、第三方图片404、Free/Plus无后台权限、撤权和注销清空 |
| Python语法检查、`git diff --check` | 通过 |

本机沙箱默认不允许监听端口，HTTP回归与浏览器在获准的本机隔离环境复验；未连接生产。一次Astro命令从根目录运行失败，已改在site目录构建并清理误生成的根目录缓存；最终构建通过。Python编译缓存改到/tmp后通过并清理。未重复运行与T02无关的完整Python/发布激活套件，API完整回归和站点/浏览器门禁已独立完成。

保留证据：

- `/tmp/maas-t02-api-final.log`（111测试）。
- `/tmp/maas-t02-site-final.log`（npm完整站点构建）、`/tmp/maas-t02-site-ui-final.log`（最终UI构建）。
- `/tmp/maas-admin-browser-t02-final/browser.json`及admin-user-detail/admin-feedback-detail/admin-feedback-mobile/user-feedback-result等PNG截图。

临时账号库、outbox、API/代理/Chromium进程已由脚本销毁；中间截图与误生成缓存已清理，只保留最终交付证据。生产升级、发布版本运行时来源仍未验证；没有其他T02功能阻塞项。
