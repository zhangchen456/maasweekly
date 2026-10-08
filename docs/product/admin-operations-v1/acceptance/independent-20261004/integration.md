# 跨任务联合验收

版本、环境与证据边界同README。表中“通过”仅描述该已实测链路，任务整体状态使用README限定状态。

| 链路 | 本轮独立实际结果 | 证据与边界 |
| --- | --- | --- |
| 权益变更→网站/API/MCP→专业邮件资格 | 本地通过 | API195项中的account/pro/admin-operations/payment-integration实际权益与拒绝、MCP成功事件/支付来源、T06发送前重查偏好/有效权益；browser-main的Plus全文/普通用户拒绝，browser-payments的paid/full退款。不是一次真实供应商端到端邮件送达 |
| 周报出版→Plus读取→事件→分析 | 本地通过 | browser-main先历史创建/冻结/4 worker/编辑/审核/出版/compose，再Plus读取与匿名预览，再analytics真实SQLite去重/回访；weekly-evidence.json、browser.json及截图。mock模型，真实内容质量未验证 |
| 信源失败→任务异常→覆盖限制/出版判断 | 不通过，D01 | source-publication自编独立复现。T05能够显示异常，T03不读该异常，公开status正常时normal出版。期次相关性通过同窗口Google Vertex changelog夹具明确；来源时间/投影冲突需要实现关联 |
| 反馈→问题诊断→修复版本→上线验证→用户结果 | 本地模拟通过 | browser-problems双反馈关联、选定材料mock、候选/合并/发布独立、失败复验、逐条T02门槛；browser-main用户看公开结果。真实PR/提交/发布包含关系/online影响范围未验证，引用为合成数据 |
| 支付成功/退款/到期→权益→内容访问→对账 | 模拟通过，真实沙箱验收阻塞 | payment/payment-integration实际HTTP/MCP与邮件权益、并发退款/worker、browser-payments服务端模拟paid、取消、pending/partial/full退款和对账；不能证明供应商沙箱、真实扣款/退款 |
| 管理鉴权/审计/幂等/版本统一 | 本地通过 | 复跑admin/admin-operations/editorial/analytics/monitor/delivery/problems/payment专项的真实HTTP及SQLite故障回滚/冲突/重放断言。源码admin-http共同认证/来源/no-store，服务共享AdminStore.command；CLI显式actor，幂等请求绑定，未出现第二套管理协议 |

未额外执行无意义全量重复。信源复现是现有全绿测试未覆盖的独立检查；不能因为195项通过宣称所有联合要求通过。实际生产/供应商验证均未执行，无生产私有用户夹具。
