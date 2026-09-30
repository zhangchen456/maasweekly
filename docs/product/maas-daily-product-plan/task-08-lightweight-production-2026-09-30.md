# Task 08 轻量一期生产验收

2026-09-30（Asia/Shanghai）。用户提供公开 Cloud Tracking Code 后启用生产配置。

- Commit：`880e8ccff135b9d22191e2d832cf011e9d440433`，已同步 main 与任务分支。
- Website ID：`4f0172a2-5aea-48cf-bb38-22eb86368fea`。
- RID：`rl_880e8ccff1_1925cbc6adaf`，22:17:51 激活成功。
- datasetVersion：`ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207`；dataThrough：`2026-09-30`。
- 本地标准 release 全量门禁：41 个检查组通过、0 失败；manifest 22,422 文件，testsSkipped=false。生产页面、公开数据及 agent-api 作为同一 release 发布。

## 发布路径

[分支手动 workflow](https://github.com/zhangchen456/maasweekly/actions/runs/36726148597) 在 main 同步后取消。[main workflow](https://github.com/zhangchen456/maasweekly/actions/runs/36726653036) 在 runner 初始化阶段迟迟未推进，也已取消；这两个 workflow 不是通过证据。

使用本地已完整构建和校验的 release，通过 `maasdeploy_ed25519` 受限 SSH 按标准协议 rsync 到 incoming，再调用现有 `remote_activate`。未绕过 manifest 校验、蓝绿候选检查或线上 verify；未直接写在线根目录。激活及 `ops/verify-release.sh --online --expect-release rl_880e8ccff1_1925cbc6adaf` 均退出 0。

REST status/changes 的 datasetVersion 一致；MCP initialize、五工具及调用通过；两个 RSS 入口 Content-Type/ETag/304 通过；Skill manifest/install.sh 可达。Nginx syntax check 成功，日志有既存其他域名重复 server name 警告，本次没有修改相关配置。

## 实际 Cloud 请求

成功下载真实 `https://cloud.umami.is/script.js`，检查其 before-send 回调和实际 gateway。用真实 SDK 验证初始 pageview、查询筛选去重、事件属性清洗。

生产 Chrome 浏览器访问首页 QA URL，确认仅一个适配器和一个 Cloud SDK。实际请求 `https://gateway.umami.is/api/send`：

- `page_view`：HTTP 200，website ID 与用户配置一致。
- 点击真实首页复制简报按钮：`copy` HTTP 200，仅 `page_type=home`、`kind=brief`，不发送简报正文。
- 验证 URL：`/?utm_source=qa&utm_medium=verification&utm_campaign=task08`，便于看板识别验收流量。

Cloud 接收已验证；原生看板内的数据展示需要用户在登录账号中核对，本次没有读取其私人账号或将看板设为公开。登录 Cloud → Websites → MaaS Daily，可查看访问、来源、页面及 Events。

回滚沿用 `ops/rollback-release.sh`，上一生产 RID 为 `rl_f684fc186c_1925cbc6adaf`。本期未部署自托管分析服务或自建看板。此前已批准安装的 PostgreSQL 前置依赖仍保留。
