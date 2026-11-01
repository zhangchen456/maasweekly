# 正式收费接入与操作（2026-11-01）

正式商品 `PROD_4at9FbSOvaC5bLYEVGe0Ln`，店铺 `STO_5XRDhjxtHscwJdETFLbN1w`，USD 9.99/月。用户已授权上线；已有免费 Plus 公测用户保留启用时起 7 天体验，到期自行订阅，不自动扣款。Free 保留。本文说明实现与发布步骤；实际启用时间、生产版本及实测结果以工作区 operations/waffo-live-20261101/RESULT.md 为准。

## 发布条件

运行统一门禁 `python scripts/test-runtime.py`（CI 必须使用独立 PostgreSQL），再完成官方测试环境下的真实订单、取消与权益核对。先发布代码且维持收费关闭，再核对生产商品与签名通知入口、配置后使用 runtime-control 的 stage/activate 切换相同已验证代码；避免直接重启在线槽。云盘备份保持暂停。

服务器私密 agent.env 必需配置：`MAAS_PAYMENT_MODE=waffo`、`WAFFO_LIVE_ENVIRONMENT=prod`、`WAFFO_LIVE_PRIVATE_KEY_FILE`（服务器正式私钥文件）、`WAFFO_LIVE_KEY_SHA256`（该文件原始字节 SHA256）。私钥不得进入仓库、浏览器、日志或工单。产品可见范围及 prodEnabled/payinEnable 必须再次核验；仅配置 environment 不会改变请求签名密钥的环境。

同时设置 `PRO_BETA_ENABLED=false`、`PRO_BETA_GRACE_START` 与 `PRO_BETA_GRACE_END`（毫秒时间戳，差值精确为 7 天）。仅启用前已激活且未被撤销的 beta 账号享有过渡体验。网页、API、MCP、私有 RSS 与专业邮件使用同一权益判断，不生成付费订单或扣款授权。生效时间须记录到发布回执。

## 交易与权益

- 用户只提交本地请求标识，身份、商品、金额均由服务端绑定。固定幂等标识创建收银台，账号切换后不交付旧账号链接。未付款、测试通知或付款返回页均不授予正式权益。
- `/api/payment/waffo/live/webhook` 校验 Waffo 官方 RSA 签名、正式环境、店铺及事件重复冲突，持久保存后应答。支付通知只是核对触发器；权益来自签名 API 读回的付款、当前计费周期、实际金额、身份及商品。
- 每 5 秒领取一个到期核对任务，通常每订单 60 秒核对；多进程通过 SQLite 租约与 fencing 避免旧请求覆盖新状态。通知丢失可轮询补偿。取消订单每小时、未成交且已过期的结账每天复核，仍可被新通知唤醒。
- 支付、退款、争议事实及供应商证据保留不可变记录；重复通知和轮询不会重复记账。续费失败不延长权益；部分退款保留相应周期、全额退款取消相应付款贡献的权益。手工授权与 beta 权益独立保留。
- 用户在账单页取消续费或进入 Waffo 客户中心查看账单、取消与申请退款。停止新销售不应阻断取消和客户中心。退款由 Waffo 商户后台执行；本站管理员按钮拒绝把真实退款记成未执行的内部任务。退款与取消续费是独立动作，处理退款时需核对后续续费是否同时取消。
- 历史付款缺少可验证的计费周期时，不推算周期或多送权益，保存供应商证据并报 `historical_period_requires_review`；需人工核对后补充可信周期，再重跑核对。首次上线前无正式历史订单；长期停机跨过多个周期后的自动补账不冒充完全恢复。

## 监控和处置

现有五分钟监控增加 `payment_verification_pending`（正式订单有核对错误，或未完成订单超过 10 分钟未核对）及 `payment_monitor_failed`。后台可查看付款事实与有效权益。退款申请处理仍需要运营人员查看 Waffo 客户中心工单/商户后台，不声称已自动审批退款。

故障时设置 `MAAS_WAFFO_CHECKOUT_ENABLED=false` 并滚动加载配置，仅关闭新购买，保留签名通知与核对服务及已付款权益；不得删除付款事实。若供应商金额、身份、商品或环境不符，保持待核对并联系支持，不人工伪造付款成功。正式首单需核对 Waffo 已结算事实、本站付费周期及各访问渠道；无实际扣款时不可宣称完成正式资金闭环。

官方实现依据：https://docs.waffo.ai/zh/integrate/skill ，SDK 固定 @waffo/pancake-ts 0.27.0。
