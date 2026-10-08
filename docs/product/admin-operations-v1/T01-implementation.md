# T01 实施与运维交接

2026-10-04；仅本地实现与验收，未生产部署、未发送真实邮件。

## 方案与代码核对

仓库根无AGENTS.md，读取全局`~/.codex/AGENTS.md`及site/AGENTS.md。现有server/account/AccountAccess接口与方案吻合。AccountStore事务不支持嵌套，因此AdminStore直接共用连接，仅同步command开启事务。现有pro_audit、feedback结构保持原样，本轮不迁移历史审计、不接入T02/T03业务。后台独立加法迁移记录，应用启动与CLI自动执行，不能将Plus grant与admin grant混用。

API没有可靠的发布版本运行时来源，首页显示“未提供”。数据摘要来自已加载DatasetHolder。现有登录组件采用邮箱注册/验证码验证后设置密码，浏览器验收沿用该真实流程。

## 初始化、迁移与回滚

先备份账号SQLite（在线采用SQLite backup或现有备份流程，不能只复制WAL主文件）。用原账号服务环境配置MAAS_ACCOUNT_DB及MAAS_ACCOUNT_SECRET，执行：

```sh
npm run build --prefix services/agent-api
npm run admin --prefix services/agent-api -- list
npm run admin --prefix services/agent-api -- grant --user-id EXISTING_USER_ID --actor OPERATOR_ID --reason '首次初始化'
npm run admin --prefix services/agent-api -- revoke --user-id EXISTING_USER_ID --actor OPERATOR_ID --reason '撤销访问'
```

只授权已有账号。list/服务启动即执行幂等migration 1；失败整个迁移回滚。新表admin_schema_migrations/admin_members/admin_audit/admin_commands共用账号数据库、WAL、busy_timeout及文件权限。CLI不会发送邮件，操作者由显式--actor记录为cli，grant/revoke与审计、命令结果在同一事务。不要把secret放命令参数或日志。

应用回滚使用原有发布回滚流程，保留新表及历史数据。紧急撤权用revoke，下一请求立即拒绝。不要自动DROP表；仅完整灾难恢复时按已有账号库恢复流程处理。旧API无admin路由时返回不可用，页面不回落到公共数据。

候选ops/server/maasweekly-activate新增/api/admin/代理，共用蓝绿upstream，16k/no-store/无开放CORS。未安装到生产；未来T03扩大正文需精确location，不能扩大整个后台默认上限。

## 演示与验收

```sh
npm run build --prefix services/agent-api
npm run build --prefix site
python3 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser
scripts/run-all-tests.sh
```

浏览器脚本自动启动临时账号SQLite、文件outbox、同源静态代理、独立Chromium context，阻止外部浏览器请求；结束销毁数据库及进程，只保留截图和browser.json。截图是隔离测试数据。实际页面入口/admin/与/admin/audit/；本地Astro开发代理亦已接入/api/admin/，API的MAAS_ACCOUNT_ORIGIN须匹配访问的本地源。

后端test与test:compiled覆盖admin.test；统一run-all-tests非quick阶段运行隔离后台浏览器检查，现有release_activation测试验证候选代理。CI的release、daily/weekly工作流准备Chromium（包括跳过抓取/import模式），避免新浏览器门禁缺少运行依赖。无生产数据、供应商调用或定时任务。

T02/T03必须复用docs/contracts/admin-api-v1.md的鉴权、adminWriteInput、同步command、AdminLayout与admin-client类型；不能通过现有pro/feedback自带transaction方法先提交业务再补写审计。首版只有administrator，无角色编辑器和HTTP授权入口。

## 最终交付状态与测试记录

**T01已完成，可供T02/T03复用。** 当前工作区原有的development-order/T01/T02/T03/README方案文档均保留，未提交Git、未部署生产、未执行真实邮件或模型调用。

实际修改：

- 后端：新增`services/agent-api/src/admin-store.ts`、`admin-auth.ts`、`admin-http.ts`、`admin-cli.ts`、`tests/admin.test.ts`；修改`server.ts`、`package.json`。
- 页面：新增`site/src/layouts/AdminLayout.astro`、`src/pages/admin/index.astro`、`audit.astro`、`src/lib/admin-client.ts`、`src/styles/admin.css`；修改`astro.config.mjs`、`tsconfig.page-models.json`。
- 验收与候选配置：新增`scripts/admin-browser-smoke.py`；修改`scripts/run-all-tests.sh`、`tests/test_release_activation.py`、`ops/server/maasweekly-activate`及daily/weekly/release-deploy三个CI工作流。
- 合同与记录：新增`docs/contracts/admin-api-v1.md`及本文。

| 检查 | 实际结果 |
| --- | --- |
| `npm run build --prefix services/agent-api` | 通过 |
| `node --test services/agent-api/dist/tests/admin.test.js` | 最终6/6通过；涵盖逐表旧数据保留、迁移失败回滚、幂等/版本/业务/审计/结果原子回滚、两连接、HTTP分页与权限、secure Cookie |
| `npm run test:compiled --prefix services/agent-api` | 现有账号/Plus/反馈/REST回归通过；统一入口也执行了最终后台测试 |
| `python3 -m unittest discover -s tests -p 'test_release_activation.py'` | 49项运行：48通过，1项既有跳过；候选admin代理合同通过 |
| `node .../typescript/bin/tsc --project site/tsconfig.page-models.json` | 通过，已包含admin-client |
| `npm run build --prefix site` | 最终通过，47449静态页面；admin页noindex，测试账号/审计内容未进入admin静态HTML或JS |
| `python3 scripts/admin-browser-smoke.py --output /tmp/maas-admin-browser-t01` | 最终5流程通过，0页面错误；Plus使用真实`/api/pro/beta`生效权益，仍无后台权限 |
| `scripts/run-all-tests.sh --quick`，Python 3.12+锁定临时依赖 | 62个检查通过、1项环境失败（test_pipeline_runtime缺少playwright）；补齐锁定包后单独复验18/18通过。未重新执行全部63个检查；quick之外的站点构建、浏览器检查已单独完成 |
| `git diff --check`、shell语法检查 | 通过 |

本机默认Python 3.9不兼容仓库既有类型标注，首次统一运行中止；改用Codex自带Python 3.12并在/tmp准备锁定依赖。首次激活器/HTTP测试也受沙箱端口限制，允许本机隔离端口后复验通过。这些环境问题未通过修改无关业务代码绕过。以后统一验收使用Python 3.12，按requirements.lock.txt/requirements.txt准备完整依赖和Chromium。

可复核现场（全部为本轮本地测试）：

- `/tmp/maas-admin-browser-t01/browser.json`
- `/tmp/maas-admin-browser-t01/admin-overview.png`、`admin-audit.png`、`admin-mobile.png`
- `/tmp/maas-t01-admin-final.log`、`maas-t01-api-tests.log`、`maas-t01-routes.log`、`maas-t01-site-build.log`、`maas-t01-unified-py312.log`、`maas-t01-pipeline-retry.log`

临时账号库/outbox及API/代理/浏览器进程已由验收脚本销毁；临时Python依赖已清理。以上截图与日志作为交付证据保留。

遗留限制：生产数据库升级、首次管理员授权、候选激活器安装及真实生产nginx加载均未执行或验证，须后续部署授权；API发布版本显示“未提供”。没有T01功能阻塞项。未开发T02/T03业务；后续服务方法必须拆出同步事务内实现，审计/命令结果只支持标量或标量数组的脱敏白名单。T02应先读本文与admin-api-v1合同，再按自身方案集成。
