# 产品问题反馈（本地完成，待授权上线）

入口：全站页脚「反馈问题」、账户菜单「反馈产品问题」。中文 `/feedback/`，英文 `/en/feedback/`。登录后提交问题概述、发生问题的本站路径、描述和复现步骤。支持最多3张PNG/JPEG/WebP截图，每张2MiB；可预览、移除。不会自动收集查询参数、凭据或日志。

成功后返回反馈编号，用户可查看自己的最近100条反馈、私有截图、状态与处理说明。状态为待处理、处理中、已解决。失败保留草稿和截图，同账号刷新登录信息不清空草稿，退出或换账号清空。

后端复用现有账号数据库，新增 `feedback` 和 `feedback_images`，截图以BLOB私有保存，随账号SQLite备份一起持久化。接口：`POST/GET /api/account/feedback`；`GET /api/account/feedback/:id/image/:index`。截图只允许提交者读取，未登录401、其他账号404，响应no-store及nosniff。只接收最多9MiB JSON，其他账号请求保持8KiB；图片校验base64、大小、MIME与文件头尾，拒绝SVG。每账号滚动24小时最多10条，入口另有限流。截图不会进入公开站点、公共API或匿名数据导出。

维护者在已载入账号数据库与密钥的私有服务环境操作：

```sh
node services/agent-api/dist/feedback-cli.js list
node services/agent-api/dist/feedback-cli.js export FEEDBACK_ID /private/output/directory
node services/agent-api/dist/feedback-cli.js status FEEDBACK_ID investigating '正在排查'
node services/agent-api/dist/feedback-cli.js status FEEDBACK_ID resolved '已修复，请刷新页面'
```

`list`显示维护者需要的提交者邮箱；用户接口不返回邮箱。导出包含问题JSON及截图，权限0600。状态说明由用户刷新「我的反馈」读取，无自动邮件或外部消息。维护者操作需要服务端数据库权限，没有新增匿名管理接口。

验收：后端账号、反馈、Plus共25项通过；前端登录、多选、反馈交互4项通过；站点完整构建通过。真实本地站点代理验证提交、私有截图读取、CLI截图导出、状态回复、中英文页面成功；合成反馈和导出文件已清理。正式发布测试入口已加入反馈测试。发布激活器路由定向测试通过，验证反馈9m、其他账号8k及不缓存；首次在端口受限沙箱中运行整组激活测试被中断，解除本机端口限制后定向路由测试通过，未宣称本次反馈已完成生产全量发布回归。

上线准备：`ops/server/maasweekly-activate`新增仅 `/api/account/feedback` 的9m上传location，其他账号路径仍8k。此激活器变更目前只在工作区，未修改生产；正式发布时须按现有流程核对并安装该候选激活器，再发布准确候选并验证大于8KiB截图上传。新增功能待用户批准上线；主工作区其他任务改动需继续隔离。

本地体验：http://127.0.0.1:4323/feedback/ 。仍可使用 `demo@example.com` / `MaaS-Demo-2026!`。本地体验账号不进入生产。
