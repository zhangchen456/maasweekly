# Plus 公测发布记录

用户授权上线当前功能，并要求 Plus 卡片标识反色。范围：Free/Plus 订阅页、US$9.90 计划定价及免费公测、自助开通与独立权益记录、专业情报工作空间、私有凭证/RSS/MCP、深度周报卡片和服务端全文权限、变化页面样式修复。图片采集不包含在本次发布。

独立目录 /tmp/maas-plus-release，提交 14c5422954e4cc7eaaac155080b318067b1d0de3；CI https://github.com/zhangchen456/maasweekly/actions/runs/37125793538。未包含另一个任务的浏览器时区和账户运维变更。主工作区未重置、未清理其他任务文件。

发布前 current：rl_3e0563ecfd_12fdc567c7d3；previous：rl_07d7ce23bd_12fdc567c7d3。专业接口路由激活器 SHA256 544ef070a8833d0571e9e4b39f9ec4b9f4251a04e801ac4fe9f6f8c37b4bf397；旧激活器保留于 /srv/maasweekly/shared/maasweekly-activate.pre-plus-20261003。新路由随正式版本激活切换。

状态：已上线并通过验收。生产 current：rl_14c5422954_12fdc567c7d3。CI 全量回归 60 组通过、0 失败；四个公开服务面验证成功。真实临时账号验证 14 项全部通过（开通幂等、Free 拒绝全文、Plus/凭证全文、MCP、撤销权限、匿名 API 与静态页面无全文、公开样例完整）。临时账号及远端脚本已清理，无邮件发送。线上 HTML 已确认反色 badge 与 $9.90 定价。浏览器工具超时，未取得线上截图；badge-local.jpg 为发布前已验证效果。

专业情报样例保持草稿，未代替运营审核发布；未新增专业邮件定时任务。正文图片采集另行处理。回滚可使用发布前 current。


## 变化页重定向修复（21:40 CST）

用户报告导航「变化」回首页。实测 /changes/ 返回 301 Location: /。根因：/etc/nginx/snippets/maasweekly-https.conf 遗留“变化合并到首页”两个 location，覆盖新版静态页。已在 release.lock 下移除准确匹配的旧块，nginx -t 成功后 reload；备份 /srv/maasweekly/shared/maasweekly-https.pre-changes-fix-20261003.conf。未更改发布版本。

修复后 /changes/ 与 /en/changes/ 均 HTTP 200，包含各自页面；/changes 自动转到 /changes/，变化 API 可读取。旧 301 可能在浏览器缓存中，应以带新查询参数的链接或清除该站点缓存复验。浏览器控制工具连续超时，线上响应验证通过。
