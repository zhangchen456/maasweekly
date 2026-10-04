# 2026-10-04 全部本地候选统一上线

用户明确要求提交全部本地改动到线上。工作区快照 104501ba0 与最新 main/今日数据/logo 修复合并，实际运行提交 ff7ad3a22f762f30ec802486aecef110040416b2。

生产 release：rl_ff7ad3a22f_06271d209e3d。数据截至 2026-10-04，datasetVersion 为 ds_06271d209e3d343f108455222e239e0cbc323f7e42595ba246c0b28b62923c22。

流水线 https://github.com/zhangchen456/maasweekly/actions/runs/37174137038 成功，完整回归66组通过，0失败。REST/MCP/RSS/Skill四服务面均通过，独立复验见four-surfaces.txt。

范围包含本地反馈功能、浏览器时区展示、logo通用图标和厂商输出校验、今日摘要归属修正及全部累积文档/运维代码。已有Plus/密码登录/多选功能在合并中保留。未发布的专业内容样例仍为草稿，代码发布不代替内容审核。

服务器激活器仅新增反馈上传专用9m路由；安装在发布锁下，SHA256 be97dee857204bf4acf930e37e2e660bc0f13c0a4f39866d74ae03f6f1d946af。旧激活器备份 /srv/maasweekly/shared/maasweekly-activate.pre-ff7ad3a22。账号运维及发布清理脚本与service/timer逐项SHA256一致，无需重复安装。原生产current为rl_eede7f0d8a_12fdc567c7d3，保留为previous供回滚。

线上验收：反馈10项通过，覆盖超过8KiB的上传、图片内容和响应头、跨账号404、匿名401、其他账号列表为空。临时账号/反馈/截图和远端脚本已清理，不发送邮件。脚本初次用了本地Cookie名称，改为生产__Host-maas_session；随后按HTTP语义归一代理与应用重复的no-store/nosniff响应头。最终结果见feedback-online.txt。

真实Chromium在上海和洛杉矶时区、390px手机宽度下检查首页/中英文反馈页/变化页/英文账户页，共10项通过、无页面脚本错误、无横向溢出。截图与报告见browser-online.json及feedback-*.png。

原失败运行保留历史状态，本次成功运行完成恢复。全部候选已提交；此目录仅记录上线验收，不触发额外生产构建。
