# T01 后台权限、框架与审计

优先级P0｜依赖现有账号服务｜目标：交付后续模块可直接复用的后台基础，而非只有导航的Demo。

## 1. 范围与完成标准

管理员使用现有邮箱验证码/密码登录，进入`/admin/`；普通Free或Plus用户不能取得任何后台数据。管理员撤销后，已有会话下一次请求立即失去后台权限。提供管理导航、身份状态、审计查询和少量可验证的系统状态。

首版只有administrator一种角色，不开发角色编辑器、用户经营页面、流量分析或任务调度器。未实现的模块只在说明中列出，不伪造数字或可点击空入口。

## 2. 已核对的代码基础

- `services/agent-api/src/server.ts`：当前分别路由`/api/account/`和`/api/pro/`，在这里接入`/api/admin/`。
- `account-http.ts`：现有会话Cookie、Origin校验、限流、no-store响应模式。
- `account-store.ts`：`AccountStore.user(session)`与共享SQLite；`transaction()`使用BEGIN IMMEDIATE，不支持简单嵌套。
- `site/src/components/AccountAccess.astro`及账号页面：复用登录入口，禁止复制一套独立账号协议。
- `ops/server/maasweekly-activate`：生产路由由该脚本生成，新增API路由需同步此处及相关路由测试。

## 3. 页面与交互

`/admin/`显示后台标题、当前管理员、已接入模块导航及系统摘要；`/admin/audit/`显示操作记录。匿名用户显示现有登录入口，登录后重新检查管理员资格；普通用户显示“无后台访问权限”，不能先渲染私有数据再隐藏。

摘要只包括API当前时间、已加载数据版本/数据截至、数据库是否可用。发布版本若无可靠运行时来源，显示“未提供”，禁止用前端构建版本猜测API发布版本。

静态壳允许匿名下载，但不得包含管理员名单、业务指标和真实用户数据。退出或会话失效时清空页面内存数据；多标签页权限变化在后续请求发现，不需要首版实时推送。

## 4. 数据设计

拟新增`admin-store.ts`，复用`AccountStore.db`：

| 表 | 主要字段/规则 |
| --- | --- |
| admin_schema_migrations | version主键、appliedAt；显式顺序迁移，失败回滚 |
| admin_members | userId主键且关联users、role=administrator、enabled、createdAt、updatedAt；不能由注册或Plus激活写入 |
| admin_audit | id、actorType(user/cli)、actorId、action、targetType、targetId、reason、beforeJson、afterJson、requestId、createdAt |
| admin_commands | actorId、action、idempotencyKey联合唯一、requestHash、resultJson、createdAt；只保存小型脱敏结果 |

审计按createdAt/id建索引；幂等记录首版保留，不引入自动清理。before/after使用字段白名单；不保存Cookie、密码、密钥、令牌、验证码、图片或完整请求体。

授权初始化通过拟新增`admin-cli.ts grant --user-id ... --actor ... --reason ...`完成，只授权已存在账号；另提供list/revoke。CLI操作者为显式的运维身份，不能冒充网页用户，写入同一审计。首版不开放HTTP授予管理员接口；首次部署由维护者执行CLI。

## 5. API合同

拟新增`docs/contracts/admin-api-v1.md`作为后三项共享合同：

| 方法与路径 | 返回/用途 |
| --- | --- |
| GET /api/admin/me | 管理员id、展示名、role、capabilities；不返回凭据 |
| GET /api/admin/overview | 各摘要项的value、asOf、availability；不可用不等于0 |
| GET /api/admin/audit | action/targetType/targetId/from/to/cursor/limit筛选 |

分页默认25、最大100，按createdAt DESC,id DESC的稳定游标；游标携带并校验筛选条件，非法游标返回400。审计查询返回items/nextCursor，无需计算全量总数。

统一错误`{code,message,requestId}`：401未登录，403非管理员/跨源，404对象不存在，409版本或幂等冲突，413超限，415类型错误，429限流，503依赖不可用。允许GET/POST，其余405。所有私有响应包括错误均no-store、nosniff、Vary: Cookie。

后续写接口统一要求`Idempotency-Key`及JSON中的reason；涉及可修改对象时要求expectedVersion。相同操作者、动作、键和请求体重放返回原结果，不重复写审计；同键不同请求体409。版本冲突不覆盖，UI重新读取并提示。

## 6. 鉴权与原子性

拟新增`admin-http.ts`和`admin-auth.ts`。每次请求先解析现有Cookie并调用AccountStore.user，再读取admin_members；禁止接受请求体actor、邮箱白名单前端判断、Plus凭证或通用Bearer作为管理员资格。

POST要求精确匹配配置Origin且拒绝cross-site，先鉴权再读取正文；沿用限流工具。拒绝JSON未知敏感字段；SQL参数绑定。

抽出可复用的同步command执行器：事务内检查幂等与expectedVersion → 业务写入 → 审计 → 保存结果 → 提交。禁止在事务回调中await。后续调用现有自带transaction的服务方法前，必须拆出明确的事务内实现或在原方法内增加受控回调，不能BEGIN嵌套，也不能先提交业务再单独写审计。

不为失败请求写完整业务审计；记录脱敏的拒绝类型与requestId即可，避免请求攻击撑大业务审计表。

## 7. 前端与部署改动

拟新增`site/src/layouts/AdminLayout.astro`、`site/src/pages/admin/index.astro`、`audit.astro`、`site/src/lib/admin-client.ts`与后台样式。client统一处理401/403/409及加载错误；不依赖localStorage判断管理员。

激活器新增`/api/admin/`代理，与当前蓝绿API槽位一致，默认请求体16KiB，不缓存，不添加开放CORS；为T03正文接口保留后续精确路由扩容位置。静态后台页noindex，不把noindex当权限控制。仅修改候选配置，不在此任务安装生产激活器。

## 8. 实施步骤

1. 固定合同与迁移框架，完成管理员CLI和鉴权单测。
2. 接入HTTP、事务/审计/幂等基础和只读摘要。
3. 完成页面壳、审计列表与失效状态。
4. 修改候选代理配置，执行隔离集成与浏览器验收。
5. 更新后端test/test:compiled入口和统一发布检查，使后续发布自动覆盖新增测试。

## 9. 验收

- 匿名401、普通Free/Plus均403；伪造actor/role无效；撤销管理员或会话后立即拒绝。
- 跨源POST403；私有API及错误不缓存；构建产物不含测试账号和审计详情。
- 迁移可重复执行，旧账号库升级保留用户/会话/反馈/专业数据。
- command执行器用真实SQLite验证重复请求只执行一次、冲突409、业务或审计失败均整体回滚。
- 实际HTTP分页无同时间戳重复/漏项；非法参数有明确错误。
- 隔离浏览器走通匿名→登录→管理员首页→审计；普通用户无权限、注销清空页面。
- API构建、相关账号回归、站点构建、激活器路由测试通过。演示使用临时库与本地邮件适配，不用生产数据。

## 10. 交付与回滚

交付代码、admin-api-v1合同、管理员初始化/撤销操作说明、测试结果及截图。新表随现有账号库备份；应用回滚保留新增表。旧版本没有admin路由时，新代理返回不可用，不允许fallback到公开数据。给T02/T03说明鉴权入口、command执行器、分页类型和组件实际路径。
