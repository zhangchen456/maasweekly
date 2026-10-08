# T02 用户、权益与反馈处理

优先级P0｜依赖T01已合入｜目标：运营在后台完成一次用户问题排查、权益处理和反馈闭环。

## 1. 范围

包含用户检索/详情、Plus权益解释及手工授权/撤销、撤销会话/专业凭证、反馈列表/详情/私有截图、内部记录、公开说明、修复与验证记录。不包含支付、替用户订阅邮件、修改密码、模拟用户登录、自动修代码或发布、自动回复邮件。

所有管理员身份、API响应、分页、审计和写入幂等复用T01；浏览器不直接访问SQLite，不通过后台拼接shell命令调用CLI。

## 2. 当前实现约束

- `account-store.ts`：users本身无created字段；`account_profiles.created`为资料建立时间，不应无条件称为注册时间。首版显示“资料建立时间”，缺失为未知；不可根据会话到期反推最后登录。
- `pro-store.ts`：`entitlement()`优先判断有效公测，再判断手工服务期；`PRO_BETA_ENABLED=false`影响公测。UI必须调用同一判定逻辑。
- `grant()`内部已有事务、专业审计和事件；撤销还会取消pending专业邮件。新增管理写入必须保留这些副作用，并解决与T01事务的嵌套问题。
- `feedback-store.ts`已有list/detail/screenshot/update；list最多100条且无分页，后台另增分页查询，不能直接当全量数据。
- `feedback-cli.ts`是已有维护入口；不能在新后台增加版本机制后仍允许CLI绕过而无记录。

## 3. 页面

### 用户列表 `/admin/users/`

默认每页25条；邮箱或userId检索，支持有效Plus/Free、公测/手工来源筛选。列表展示邮箱、昵称、资料建立时间、当前权益状态/来源、关注数量。effective entitlement的筛选在SQL或等价查询层正确完成，不能取一页后在内存过滤导致分页失真。

### 用户详情 `/admin/users/detail/?id=...`

采用静态详情壳和运行时API加载，不为每位用户生成Astro静态页面。展示账户摘要、手工权益记录、公测记录、最终生效解释、免费/专业邮件偏好、关注数量、近30天专业事件摘要、反馈入口和管理员操作历史。

敏感动作提供明确对象、影响说明、原因输入和提交结果。手工服务期使用带时区时间，在服务器转毫秒并校验starts < ends。开通手工权益不会伪造付费记录，也不自动开启邮件。

### 反馈列表与详情

`/admin/feedback/`支持用户、内部阶段、优先级、时间筛选，默认未完成优先、再按updatedAt DESC/id DESC。`/admin/feedback/detail/?id=...`同屏展示用户描述、图片、用户摘要、内部备注、公开回复、修复链接和验证记录。公开与内部字段有明确文字标识，不共享输入框。

首版不做复杂分派；operatorId记录最近处理人即可。优先级为urgent/high/normal/low，只是分诊字段，不自动承诺SLA。

## 4. 数据变更

通过T01迁移框架新增：

| 表 | 字段与作用 |
| --- | --- |
| admin_user_versions | userId主键、version；仅用于本任务管理操作并发控制，不能声称覆盖所有用户自行修改 |
| feedback_ops | feedbackId主键、stage、priority、version、updatedAt、operatorId、resolutionType、relatedFeedbackId可空 |
| feedback_notes | id、feedbackId、actorId、body、createdAt；追加式内部备注 |
| feedback_verifications | id、feedbackId、kind(code/content/data/other)、artifactRef、releaseRef可空、result、checkedAt、actorId、note |

现有feedback.status/reply继续是用户公开视图。首次迁移open→triage、investigating→investigating、resolved→resolved；历史resolved标记为legacy，不虚构验证记录或倒逼重开。

新增记录与状态变化在同一事务更新feedback_ops、公开status/reply及admin_audit。备注最大4000字；公开reply沿用2000字；链接/标识最大500字且按允许的http(s)链接或普通标识验证，显示为转义文本，不请求这些URL。

内部阶段：triage、investigating、waiting_user、fix_pending、release_pending、verify_pending、resolved。允许回退排查，但必须填写原因；从resolved重开同样留痕。

公开映射：triage→open；resolved→resolved；其余→investigating。新resolve必须有公开说明和验证记录：code至少修复引用、发布版本、通过的线上验证说明；content/data需更正对象及核验记录；other需非缺陷/重复等处理依据。重复反馈不得指向自身或形成循环，保留原反馈，不删除合并。

## 5. API

沿用`/api/admin/`前缀，拟新增以下路由；查询分页复用T01规则，排序字段不同则游标显式标记。

| 路由 | 内容 |
| --- | --- |
| GET users | q、entitlementStatus、source、cursor、limit |
| GET users/:id | 经过白名单裁剪的详情、effectiveEntitlement、manual/beta来源、adminVersion |
| POST users/:id/entitlement | operation=grant/revoke、服务期、reason、expectedVersion |
| POST users/:id/revoke-sessions | 撤销该用户全部网页会话、reason、expectedVersion |
| POST users/:id/tokens/:tokenId/revoke | 撤销所属专业凭证、reason、expectedVersion |
| GET feedback | userId、stage、priority、时间、cursor、limit |
| GET feedback/:id | 用户公开字段、ops、内部备注及验证记录的有界分页/子资源 |
| GET feedback/:id/images/:index | 管理员专用私有图片读取 |
| POST feedback/:id/update | stage、priority、publicReply、reason、expectedVersion |
| POST feedback/:id/notes | body、reason、expectedVersion |
| POST feedback/:id/verify | kind、artifactRef、releaseRef、result、note、reason、expectedVersion |

POST均要求Idempotency-Key。resolve通过update完成，验证记录预先追加，执行resolve时再次检查记录有效性。用户不存在404；版本冲突409；接口不能直接接受任意SQL字段或用户提交的actorId。

## 6. 权益与兼容细节

1. DTO只返回专业凭证元数据，永不返回hash/encrypted或RSS secret。撤销网页会话与撤销专业凭证是不同按钮。
2. grant后若公测仍生效，UI应显示实际source=beta及手工记录，不声称用户已切换为付费。revoked→grant沿用现有语义，可能恢复公测；提交前说明、提交后展示服务端最终判断。
3. revoke无现有手工服务期时，由受控服务为现有用户建立合法的撤销标记及所需时间范围，保留原grant副作用；不要要求运营编造服务期，也不要直接删除公测记录。具体算法与边界测试写入合同。
4. adminVersion只保护管理员并发修改；授权命令事务内重新计算权益。CLI权益变更也要经过共享服务更新版本和审计，避免绕过；公测激活保持原业务语义，返回最终状态。
5. AccountStore.logoutAll与ProStore.revoke若提取事务内实现，原用户接口行为保持不变。
6. 反馈CLI保留list/export/status兼容：status调用同一业务服务；open→triage、investigating→investigating；resolved缺少新验证材料时返回明确提示并支持补充参数。导出仍私有；CLI不得将内部备注混入用户接口。
7. 管理员图片端点调用受控读取；原`/api/account/feedback/:id/image/:index`继续只允许提交者。保持图片no-store、nosniff、CSP sandbox和索引/MIME限制。

## 7. 建议文件划分

新增`admin-users.ts`、`admin-feedback.ts`承载应用服务；`admin-http.ts`挂载路由。扩展现有store的事务内方法，避免将全部业务堆进HTTP文件。新增用户/反馈页面、组件和共享请求客户端调用。

用户与反馈列表使用索引避免每行重复查询。详情最多返回最近一页事件/备注，更多数据走分页。首版数据库规模未知，验收用数千用户和反馈验证查询有界，不承诺未经测量的吞吐量。

## 8. 实施步骤

1. 完成迁移、查询DTO和有效权益口径测试。
2. 提取共享事务业务方法，接入审计/版本/幂等；同步CLI。
3. 完成反馈状态及验证流程，再接私有图片。
4. 实现用户与反馈UI和跳转；加入总览待处理数量，标注计算口径与时间。
5. 隔离验收与回归，更新后台合同及操作指南。

## 9. 必须验收的场景

- beta/manual/expired/revoked/未授权及公测关闭组合，后台最终权益与原用户API一致。
- 双窗口修改409；重复提交不重复审计；在审计写入处注入失败，权益/反馈变化整体回滚。
- 管理员可读取反馈图片，普通用户不能通过admin路径读取；原所有者权限保持，第三方仍404。
- 内部备注不出现在原用户列表、导出公开内容或网页构建产物；用户只看到公开状态与回复。
- 新code反馈未填发布和验证记录不能解决；记录通过后解决，原用户页刷新可见；重开留痕。
- 原CLI更新与网页并发不会静默覆盖；已有历史resolved可以查看，不伪造新验证。
- 撤销会话后原会话失效；撤销专业凭证后原凭证失败；grant/revoke保留专业邮件取消规则。
- 构建、账号/Plus/反馈/后台测试通过；真实隔离浏览器走通用户检索→反馈→公开回复→验证→解决，以及普通用户查看结果。

## 10. 交付

交付代码、新增合同、迁移兼容说明、临时数据浏览器验收记录、CLI使用变更。加法表随账号库备份；旧程序回滚仍读取feedback.status/reply及原权益表，但旧CLI可能绕过新审计，回滚期须暂停管理写入并在操作说明中明确。不进行生产操作或真实消息发送。
