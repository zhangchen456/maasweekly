# 账号与模型关注生产上线

状态：RELEASED，2026-10-03。

账号运行版本 `rl_07d7ce23bd_12fdc567c7d3`，commit `07d7ce23bdffd3ebaaa79e425d82c929e878ec6e`，previous `rl_9c21f5fee5_12fdc567c7d3`。数据版本保持 `ds_12fdc567c7d3e70fd11f64bd2c28fe27a56c40744950e9ab2185e4ebb4723bf5`，dataThrough 2026-10-03。

[正式 CI](https://github.com/zhangchen456/maasweekly/actions/runs/37098593460)完整 60 项门禁全部通过；标准不可变构建、蓝绿激活、REST/MCP/RSS/Skill 四入口验收通过。原始证据见 acceptance/production-ci。

## 生产配置与验收

- Node v22.22.3。账号数据库位于 `/srv/maasweekly/shared/state/accounts/accounts.sqlite`；目录 maasagent:maasagent 0700，数据库 0600，跨 release 共享。
- Resend 发件域名 `notify.maas.click`，发件人 `MaaS Daily <hello@notify.maas.click>`。真实本地和服务器发信均被验收邮箱收到；服务器环境配置包含 Resend 与账号密钥，未写入仓库或日志。
- 激活器仅增加 `/api/account/` 私有路由；旧环境配置与激活器保存在 root 专用备份 `/srv/maasweekly/shared/account-enable-backup-20261003T045933Z`。
- [真实 Chromium 验收](acceptance/production-browser.json)：验证码邮件到达、浏览器登录、Secure/HttpOnly/SameSite Cookie、关注刷新保留、主动开启邮件、手机无横向溢出、退订保留关注、取消关注、退出全部通过，无页面脚本错误。验收账号最后无关注、邮件关闭、会话已退出。
- 每日摘要和每15分钟重试两个 timer 已 enable --now。两个服务手动运行均 Result=success、ExecMainStatus=0，queued/sent/failed/review 全部为0，未补发历史。
- 下一次每日任务为北京时间 2026-10-04 09:15；失败重试按每15分钟执行。仅处理主动开启提醒且明确关联关注模型的后续变化，无更新不发。

本机第一次构建使用默认 Python 3.9，与最新项目代码不兼容；切换 Python 3.12 后转交正式 Linux CI 完成唯一正式构建。浏览器脚本先后修正了等待数据同步及只读取本次请求后验证码的验收时序，没有改产品实现。含维护者邮箱的临时截图未纳入公开证据。

## 恢复

代码回退使用标准 `ops/rollback-release.sh rl_9c21f5fee5_12fdc567c7d3 --reason account-rollout-rollback`，然后验证四入口。回退到无账号 runner 的代码前先停止并禁用两个账号 timer；如需恢复旧服务器配置，由管理员从上述备份恢复 agent.env 与激活器并核对 nginx 配置。账号数据库不随代码回退删除，保留用户数据。

发布完成后 root 专用配置备份保留用于回退，不属于待清场临时文件。未来数据更新可能产生新的运行 release，以服务器 current 为准。
