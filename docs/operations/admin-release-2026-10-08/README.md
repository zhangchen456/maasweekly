# T01–T07生产部署验收（写入与运行验收通过）

当前结论（2026-10-08批准后最终复核）：代码f6ad9f25d7d191f0458ec279bd780b3e55f624a2已部署，release rl_f6ad9f25d7_22c3472abbdf，数据截至2026-10-08；CI完整门禁70/70与四入口成功。独立公开HTTP四入口8检查、匿名管理接口12检查、生产迁移/数据库健康/原业务主键保留通过，真实浏览器后台匿名登录入口正常。指定zhangchen3508@gmail.com已由CLI授予管理员并审计。

用户随后明确同意四项操作，已安装维护脚本并导入77条公开归档任务、71信源；实际SQLite backup和隔离恢复通过。原digest/retry及health timer保持active。两个mock worker已启用并持续运行，付费模型开关false，T08 payment disabled。合成账号生产HTTP写入与worker任务验收通过；浏览器首次等待超时保留为失败，独立重验8页权限可见、无页面错误、390px无横向溢出。撤权立即403，两个临时账号及精确关联测试数据均清理，审计保留。真实管理员保留。

启动验收发现current符号链接导致worker入口判断跳过，修复为node --preserve-symlinks-main，生产unit已安装验证，提交f6ad9f25d。后续发布流水线37742831591成功，最终current=rl_f6ad9f25d7_22c3472abbdf；站点/API业务代码与6e9fac6db9相同。两个worker已重启加载最终release并确认active。临时凭据已删除。CLI preservation首次受备份WAL目录权限限制未算通过，改用immutable备份与只读线上库独立核对通过，六张原业务表主键缺失均为0，合成账号残留0。

已完成的生产核查来自实际HTTP、服务器只读数据库比较及实际CLI授权，不仅是代码检查。原本本机verify-release.sh因maasdeploy SSH凭据不可用中止，保留four-surfaces-online.txt，未算通过；改按同一HTTP/RPC合同独立核对四服务面并结合root只读status绑定版本，结果见four-surfaces-independent.json。CI原封装四入口也成功。

证据：ci-success.json、ci-success-build.txt、database-online.json、anonymous-admin-online.json、four-surfaces-independent.json、runtime-state.json。真实Umami/邮件送达、真实模型质量/费用尚未做本轮验证，不将mock或配置存在算作外部能力通过。

回滚边界：previous为rl_9cb41382fe_755b2c83d439（数据截至10-07）。本次没有执行生产回滚；旧数据不覆盖当前10-08数据，直接回退会受既有防数据回退门禁限制。需要旧代码回退时先停管理写入/新worker/投递，按既有协议准备保留当前公开数据的兼容旧代码或修复release；保留所有新私有表/审计/费用，不DROP或用旧sender重发未知任务。原env/activator备份仅在服务器受限目录；共享配置恢复不是release回滚的自动组成部分。

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


最新部署候选6e9fac6db9885a0d51ee84c246aea7f8533346b8，流水线 https://github.com/zhangchen456/maasweekly/actions/runs/37718488790 。两个失败专项已在重建52443页站点后通过。待完整CI门禁/激活与生产独立复核后才能宣称上线通过。

恢复入口：/private/tmp/maas-admin-online-20261008.mjs与maas-admin-online-browser-20261008.py为待执行的生产合成验收脚本（只模拟用户、mock任务，不出版正式内容/发邮件/支付），/private/tmp/maas-monitor-production-20261008为77条公开归档任务投影。执行前核对current=最新RID和完整门禁成功；不得把旧CI失败、取消构建或本地专项算作生产通过。原sender timer已暂停，health timer保留运行；worker unit installed但未启动。后续结束时需要恢复原sender timer或明确留给协调处理，不能遗漏维护状态。管理员指定邮箱已确认，不需重问。


## 批准后验收证据

http-write-online.json记录浏览器前已执行通过的HTTP与任务断言；browser-page-recheck.json及两张截图为独立浏览器重验；revocation-online.json为撤权403。worker-first-attempt.json保留worker首次失败。所有测试任务均为合成、无出版、无验收邮件、无付费模型、无支付。外部Umami、真实邮件送达和真实模型质量仍未验证。

最终发布证据：worker-fix-ci.json，current和worker重启后运行状态见runtime-state.json。实际无告警健康检查见health-final.json。
