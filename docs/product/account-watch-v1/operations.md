# 开发与启用

## 本地

要求 Node >=22.13（内置 SQLite，无需 --experimental-sqlite）；当前工具链 22.22.3。Node 22 仍提示 SQLite 实验性警告。数据库、验证码和邮件不可放进 site/public 或公开投影。

在项目根目录创建被忽略的 `.local-account/`，将以下变量存入权限 0600 的本地环境文件（不入仓库，不把真实密钥写进命令历史）：

```
MAAS_ACCOUNT_DB=/absolute/project/path/.local-account/accounts.sqlite
MAAS_ACCOUNT_SECRET=<至少32字符的随机值>
MAAS_ACCOUNT_ORIGIN=http://127.0.0.1:4321
MAAS_MAIL_MODE=outbox
MAAS_MAIL_OUTBOX=/absolute/project/path/.local-account/outbox
PUBLIC_DATA_ROOT=/absolute/project/path/data/public/v1
```

API 构建：`npm run build --prefix services/agent-api`，载入环境后 `npm start --prefix services/agent-api`。Astro 开发服务器按照 site/AGENTS.md 使用 `astro dev --background`；开发配置会将 `/api/account/` 和 `/api/v1/` 代理至 127.0.0.1:8787。浏览器必须使用上面配置的确切 Origin。

outbox 模式不发送真实邮件。邮件 JSON 仅写本地私密目录，验证码不在 HTTP 响应或日志出现。自动浏览器验收脚本使用临时目录和本地 outbox，不需要外部邮件凭据：

```
npm run test:account --prefix services/agent-api
npm run build --prefix site
python3 scripts/account-browser-smoke.py --output docs/product/account-watch-v1/acceptance
```

## 生产启用候选

1. 核对 Node 至少 22.13、`/usr/bin/node` 与当前部署实际 Node 路径一致；如不一致调整 digest unit。现有 read-only systemd 已允许写 `/srv/maasweekly/shared/state`。
2. 以 maasagent 可写、其他用户不可读的权限建立持久目录；`accounts.sqlite` 和 WAL/SHM 放此处，跨两个槽位共享。不得写 release 内部。运行时创建 schema，不包含破坏性迁移。
3. 在 root 管理的 `shared/agent.env` 配置 `MAAS_ACCOUNT_DB`、`MAAS_ACCOUNT_SECRET`、`MAAS_ACCOUNT_ORIGIN`、`RESEND_API_KEY` 和 `MAAS_MAIL_FROM`。Resend 发件域名须先验证。生产禁止 outbox。
4. 审核并安装包含新账号 location 的服务器激活器（`ops/server/maasweekly-activate`），再发布候选代码，沿用已有不可变 release 审核和激活协议；仅上传 release 不会更新服务器上的激活器。只读 `/api/v1` 合同不变，账号走独立 `/api/account`，不能通过现有仅允许 GET 的公共 API 路由代理。
5. 先用维护者邮箱验收验证码、Cookie、保存关注、重启、退出和退订。邮件投递服务还没有真实配置时，不得把本地 outbox 验证视为发信验证。
6. 将 `ops/maas-account-digest.{service,timer}` 和 `ops/maas-account-digest-retry.{service,timer}` 作为候选安装到 systemd，启用两个 timer。每天北京时间 09:15 排入新摘要；每 15 分钟仅重试已排入任务，不生成新摘要。只有这些单独服务启动邮件 runner，Web/API 槽位不自启发信任务，避免蓝绿重复发送。
7. 首次发送只处理主动订阅后、关注后有明确时间的记录。没有 modelId 的变化不发；日期精度记录保守按北京时间当天零点判断，可能略过订阅当天无法判定先后的动态。

## 投递与恢复

- `npm run account:digest --prefix services/agent-api` 运行一次，需 DB/数据根/邮件环境。只输出 queued/sent/failed/review 计数，失败退出 1。`--retry-only` 仅处理已排入任务，不发送新变化。
- SQLite 事务创建任务、占用事件版本和领取 5 分钟租约。每次最多排入 50 条/用户，批次最多处理 500 个；超出后续运行处理。
- 邮件第一次尝试前冻结正文和 idempotency key；网络失败后使用同一正文/key 重试（需等待租约），无更新不发送。
- Resend 幂等保护为 24 小时。超过 23 小时且投递结果不确定的任务标为 review，暂停自动重试，需查询邮件服务确认是否已发送；不能直接重发而假定绝对不重复。
- 退订链接 token 在 URL fragment 中，页面读出后立即移除。GET 不修改状态，点击确认后同源 POST 退订，防邮件扫描器误退订。关闭邮件会取消 pending 任务；已经向邮件服务提交的投递无法撤回。
- 取消某模型后，未开始发送的任务在领取时剔除该模型；已经冻结正文用于重试的任务可能仍包含该模型，保障邮件服务幂等一致性。
- 备份使用 SQLite online backup API 或维护窗口停写后备份 DB/WAL，一并保护密钥；不能仅复制运行中的主 DB。暂不提供个人数据删除 UI，后续商业化阶段需补管理员删除/数据导出流程。
- 密钥轮换使当前待验证验证码失效，不影响已登录会话。

## 当前部署状态

本任务仅完成本地实现与候选配置。真实邮件域名/凭据及生产发信尚待配置与验收；没有自动安装 systemd timer 或发布生产。

邮件去重依据：[Resend 幂等键官方说明](https://resend.com/docs/dashboard/emails/idempotency-keys)。
