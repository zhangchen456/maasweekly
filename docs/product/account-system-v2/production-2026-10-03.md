# 账户体系线上验收 · 2026-10-03

候选代码：`3e0563ecfd522857b9fa5bc2faf8e1ba034dd9ec`。[正式 CI](https://github.com/zhangchen456/maasweekly/actions/runs/37108977754)。线上域名：https://daily.maas.click。

本地账户 API 10 项测试通过；严格 TypeScript 检查通过；网站完整构建通过。真实 Chromium 13 个账户与跨语言场景通过，无脚本错误，包括全站验证码登录、跳转前保存、昵称与导出、失败重试、刷新保留关注、模型详情关注、手机布局、退订、对比用量保存、无本地配置的浏览器恢复、双用户隔离、中英文价格工作台共享配置、联系邮箱与英文移动布局、全设备退出。

桌面与移动端登录弹窗的屏幕位置有额外断言和截图复核。结果见 acceptance/browser.json 及同目录截图。

正式 CI 成功；完整门禁 60/60 通过，REST / MCP / Skill / RSS 四入口线上验证成功。当前生产 release 为 `rl_3e0563ecfd_12fdc567c7d3`，上一版本 `rl_07d7ce23bd_12fdc567c7d3` 保留用于回退。数据版本仍为 `ds_12fdc567c7d3e70fd11f64bd2c28fe27a56c40744950e9ab2185e4ebb4723bf5`。

真实 Resend 验证码邮件已收到，Chromium 成功登录并核验 Secure / HttpOnly / SameSite=Lax 会话、原页面登录、账户中心、跳转前保存、新浏览器恢复、退出和测试偏好恢复。英文价格工作台、联系邮箱与英文手机登录入口亦通过。结果见 `acceptance/production-browser.json`，无页面脚本错误。

账户数据库使用共享持久化路径，目录权限 0700，数据库权限 0600，账户用户为 maasagent。每日 09:15（北京时间）的邮件提醒与每 15 分钟重试计时器均启用。配置备份和激活工具备份保留用于回退；验收记录不含密钥、验证码、会话或用户导出数据。

发布工具：48 项激活测试执行，47 项通过、1 项因本地权限环境不适用而跳过；等待冷启动的窗口扩展为 30 秒，失败恢复识别实际候选环境并停止残留服务。服务器工具校验 SHA256 与仓库相同：`ecf614d06391587fa0e73611a08dbc9d3a13d065e9db70848cb64201cd7d10fa`。原工具备份于 `/srv/maasweekly/shared/account-activate-backup-20261003`。
