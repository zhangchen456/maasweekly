> 状态更新：用户已明确回复“同意操作”，本清单已执行；结果见上级README和验收证据。以下保留当时审批范围。

# 待明确批准的生产验收动作

发布门禁已通过，current=rl_6e9fac6db9_22c3472abbdf；指定真实管理员已授权。自动批准审查拒绝下面一组生产写入/服务启停，需要用户明确批准后才执行。

1. 将已提交的ops/account-maintenance.py安装到现有/usr/local/lib/maasweekly/account-maintenance.py；保留maintenance.before；创建两个受控私有inbox，导入77条公开归档任务、71信源的白名单投影。执行一次不带notify-state的实际SQLite backup/隔离恢复，导入真实检查记录。不新增通知或定时导入器。
2. 启用并启动已安装的maas-editorial-worker与maas-diagnostic-worker，模型为mock，两个ALLOW_PAID=false；只处理管理员手动入队任务，无自动审核/出版/邮件。正式真实模型配置与质量仍待单独验收。后续代码更新需按运行说明停止/重启worker，避免旧worker代码留驻。
3. 恢复此前维护暂停的maas-account-digest.timer、maas-account-digest-retry.timer。恢复的是原正常业务调度，可能发送真实用户已订阅的业务邮件；不手动发送验收邮件，不混跑旧sender（原current已切新版）。health timer始终保持运行。
4. 执行synthetic-online.mjs和synthetic-browser.py：只创建acceptance-admin-20261008-ordinary@example.test和acceptance-admin-20261008-admin@example.test两个合成账号，后者临时管理员，会话30分钟；验证Free/Plus隔离、Origin、正文限额、幂等/冲突、撤权，及零证据期次/独立mock诊断任务。临时管理员成员资格在清理时撤销/删除，不声称有自动成员到期机制。普通账号邮件偏好关闭，不发送邮件/模型真实请求/支付。

验证结束仅按脚本的精确合成ID/前缀检查删除合成账号、机构、关联测试材料与临时凭据。指定真实管理员保留，审计和幂等历史保留，不改其他用户资料。若中断，先核对合成文件并执行同样受控清理，不重跑init。真实用户数据不作为测试夹具或传出服务器。

服务原配置备份在/srv/maasweekly/shared/state/admin-release-20261008。合成数据cleanup不会删除任何已出版内容；发现意外publication即中止。T08 disabled，禁止真实支付/退款；正式用户内容不因本次验证被出版。
