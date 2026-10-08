# T01–T07生产部署验收（进行中）

用户2026-10-08授权提交代码并进入生产部署验收，管理员为zhangchen3508@gmail.com。T08继续禁用，不启用付费模型或额外邮件发送。

代码提交48c38ed35，空白修正9a986c18d。需合入最新main/公开数据，再绑定最终部署版本；生产读取到current rl_9cb41382fe_755b2c83d439，previous rl_1c96bd6d89_d3701d79dd63，公开数据截至2026-10-07，最新main 463195d4e3442b2689c8674ca86b71cb4b0f7f3b。

生产账号存在（仅布尔检查），SQLite quick_check=ok，25张表。管理员尚未授予，后台尚未部署。原账号digest及retry timer运行，切换时应暂停旧sender并确保无执行中作业；升级一致性backup与隔离恢复、保留表、当前激活器备份、生产配置只增加禁用支付/付费模型安全开关，secret不输出。

最终需全量release门禁和manifest、线上四入口同版、nginx私有路由/头部与请求大小、匿名/普通用户拒绝、明确账号管理员授权、数据库迁移保留及幂等、邮件新旧切换、工作台运行时静态壳与真实浏览器。不以本地证据冒充生产完成。真实统计供应商/邮件送达/付费模型质量仍单独未验证。若旧应用回退，暂停sender与管理写入，保留新表/审计，不能恢复旧未知任务自动重发。


## 发布推进记录

已合入main最新463195d4e，数据截至2026-10-08；合并21938aea6推送main后，GitHub拒绝工作流解析（job级env使用runner.temp不可用），run37714865757没有执行测试/激活。修复提交1b98e162a在step通过GITHUB_ENV设置相同目录，18项workflow合同测试通过；该作业因新候选替代在构建阶段取消。

最终候选1b356a99292fedcc37166d8478dad7047f7e9956修正editorial unit与release布局不一致的路径，数据库沿用agent.env；增加相同权限边界的diagnostic unit。实际worker模型配置mock、paid=false，unit已systemd验证但尚未启动。

当前正式发布流水线：https://github.com/zhangchen456/maasweekly/actions/runs/37715522486 。完整门禁进行中，不使用skip-tests。

发布前实际一致性备份/恢复通过，服务器证据在/srv/maasweekly/shared/state/admin-release-20261008/：before.sqlite（留在生产受限目录，不下载作夹具）、agent.env.before、activator.before、preparation.json。原25表逐表比较的隔离恢复副本验证后已删除。当前候选激活器SHA256 e7de9fe16b84fe0eacc4273fd5b8b2dc795451e5cac6d69cb38ec8dc67a8efb1，安装时持有原发布锁。原current仍保留，timer停止期间没有手动发送邮件。

自动批准审查曾拒绝“门禁尚未完成时替换维护脚本、写持久inbox与导入记录”；该命令未执行。等待门禁完成后再按实际证据推进，没有绕过拒绝。


## 完整门禁实质失败与修复

37715522486未激活，68组通过、2组失败：cross-platform测试强制每个平台必须有新鲜完整输入/输出价格，与P2-01合同“报价缺失显示缺失”及现有页面等待证据状态不一致；测试修正为可用报价须fresh/complete、平台/时间/口径一致，不可用时不隐瞒有效报价、不回退旧价，并核对实际HTML缺失提示。未修改价格事实、未下调质量阈值。

leaderboards门禁AA周榜09-28快照超过10天；进一步核对同样周周期的SWE-bench及Terminal-Bench2.1。官方来源实际更新三个榜单观察快照为10-08，保留HTML/哈希及官方Harbor DOM证据于manual-board-evidence/。SWE只取Verified下mini-SWE-agent同环境，Terminal-Bench官方首页已4.0，但经Benchmarks导航找到2.1 rev.6官方归档，不混合基准。日期表示此次观察，不宣称所有评测重新发布；新鲜度门禁仍10天。人工榜单仍人工维护，不声称接入自动抓取。
