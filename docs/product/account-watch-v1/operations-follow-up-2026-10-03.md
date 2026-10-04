# 账号关注上线后运维 · 2026-10-03

原 v1 和后续账户体系均已上线。本次只部署独立运维文件，不改变网站 release、公开数据或真实账号的偏好。

## 已实施

- 生产在线 SQLite 备份：每天北京时间 08:45；目录 `/srv/maasweekly/shared/state/accounts/backups` 为 0700，文件 0600，保留最近 14 份。SQLite backup API 包含已提交 WAL 数据；每次备份做完整性、外键检查，并复制到隔离库逐表对比。首次生产备份与恢复验证成功。
- 账号健康检查：每15分钟检查 pending 积压超过1小时、review 任务、备份缺失或超过26小时，以及摘要/重试/备份 timer 停用或服务失败。只有异常集合变化或恢复时通过已有 Resend 向维护者邮箱通知，失败发信不提交通知状态，后续重试。正常状态不发邮件。
- 摘要受控验收：生产代码与真实 Resend，独立临时 SQLite，引用真实模型记录并控制更新时间。首次关注不补历史、首次发送1封、重复执行0封、退订后0封；未修改真实用户和公开数据。Resend 接受请求，当前发信密钥查询邮件状态返回401（restricted_api_key，仅允许发信）；实际收信仍待维护者确认。
- 告警真实发信验收：隔离验收状态触发异常邮件1封，同状态重复检查0封，恢复邮件1封；邮件明确标记验收，无真实故障。Python 默认 User-Agent 被邮件服务拦截，已加应用标识并通过真实发信验收。
- 已核对重试 timer 自然执行成功，queued/sent/failed/review 全部为0。新增健康 timer 于16:45自然执行成功，无异常、无邮件。

首次安装备份路径选在 root 管理的 state 根目录，因权限失败；已改为现有 maasagent 专属 accounts 目录，未放宽共享目录权限，随后成功。临时验收数据库和脚本已清理。

## 自然运行验收（2026-10-04）

- 每日摘要首次自然运行已于2026-10-04北京时间09:15:07触发、09:15:09成功结束（Result=success，ExecMainStatus=0），queued/sent/failed/review均为0。本次没有排入匹配摘要，保持静默，不能据此声称用户实际收信。
- 08:45:01备份自然触发，08:45:02完整性与隔离恢复验证成功，保留2份；目录0700、文件0600。
- 健康检查与重试于09:30、09:45自然执行成功，alerts为空，投递计数均为0。下一次每日摘要为2026-10-05北京时间09:15。
- 原始证据：[natural-run-2026-10-04.txt](acceptance/operations-2026-10-03/natural-run-2026-10-04.txt)。本次只读检查，未触发额外投递。

## 待验证

- 维护者邮箱实际收到此前的摘要验收邮件仍待确认。

## 备份恢复

运维入口为 `ops/account-maintenance.py`，安装于 `/usr/local/lib/maasweekly/account-maintenance.py`。两个新 service/timer 是 `ops/maas-account-{backup,health}.{service,timer}`。服务复用 root 管理的 agent.env；告警收件人保存在 `/srv/maasweekly/shared/account-operations.env`（root:maasagent 0640），凭据不入仓库。

手动备份：`systemctl start maas-account-backup.service`。结果只记录快照文件名和验证状态。检查：`systemctl status maas-account-backup.service maas-account-health.service`、对应 journal 和 `systemctl list-timers --all 'maas-account-*'`。

当前自动恢复演练只恢复到隔离临时库，不覆盖真实账号。实际灾难恢复须在维护窗口停止两个 API 槽位及账号摘要/重试任务，备份当前 DB/WAL/SHM 和环境配置，确认目标快照完整性，再恢复主库、清除与旧主库对应的 WAL/SHM，恢复 0600/maasagent 权限，启动原先运行的槽位和任务，验证登录、关注和配置。不把历史快照覆盖在线主库。恢复历史快照可能恢复旧投递状态，重新启用摘要前须与邮件服务核对最近投递，避免跨幂等窗口重复发信。当前快照与主库同机，覆盖数据恢复但不覆盖整机丢失；异机备份尚未实施。

## 失败与人工复核

1. 告警到达后先查看健康服务计数与摘要/重试 journal，核对 timer 与备份是否正常。不要把无更新的0封判断为故障。
2. pending 超过1小时：核对 Resend 服务、额度、发件域名、网络和任务租约。修复后执行已有 retry service；不要改幂等 key 或冻结正文。
3. review 表示超过幂等保护窗口且结果不确定，自动任务不会继续发送。由管理员在受限终端查询 `mail_jobs` 的 id、created、status，并从私密冻结正文找到原 `digest-<id>` 幂等 key，在邮件服务核对投递结果。当前生产密钥仅有发信能力，需要邮件服务控制台或有读取权限的独立凭据。
4. 已确认发送：事务中仅将指定 `status='review'` 的任务标为 `sent`，lease=0，保留 mail_items 去重记录。确认未发送且决定不再投递：标为 `cancelled`，保留去重记录。记录任务id、核对结果、操作者与处理时间。未知结果保持 review；不批量重置为 pending。
5. 确需补发未投递邮件时，单独审核目标任务与邮件正文，先核实无已投递邮件，再使用新的补发任务与明确幂等 key；当前不提供一键补发，避免误发。

告警自身依赖 Resend 和服务器正常执行；同机离线或邮件服务完全故障时不保证主动通知。状态存储只在通知成功后前进，发送失败会让 health service 失败并在下次运行重试。

## 回退新增运维任务

`systemctl disable --now maas-account-backup.timer maas-account-health.timer`。保留已产生备份和状态；此回退不影响原账号摘要与重试任务。无需回退网站 release 或用户数据库。

验证：运维测试3项通过（WAL在线备份/恢复/保留/权限；队列健康；通知去重与发送失败保留状态）；既有账号测试10项全部通过。新增运维脚本的服务器 SHA256 与仓库核对一致。原始计数与生产运行状态保存在 `acceptance/operations-2026-10-03/`。
