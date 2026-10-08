# T06 邮件投递与服务健康

2026-10-04，本地实施。入口 `/admin/delivery/`、`/admin/health/`；保留T01–T05与原工作区改动。没有生产部署、真实发信、服务重启、生产备份恢复、回滚、新调度或自动通知；未开发T07。完整API/采集字段见统一合同T06。

## 实施前数据映射

| 实际来源 | 实际语义 / T06处理 |
| --- | --- |
| account-store mail_jobs/mail_items | 用户对变化ID+revision去重、enqueue尊重普通偏好与关注基线；同任务冻结mail、key=digest-JOB_ID。payload/退订token不能进入后台；展示eventKey关联摘要 |
| pro-store pro_mail/pro_reports | 首次compose冻结同用户/period，INSERT OR IGNORE、key=pro-JOB_ID；更正单独任务；专业偏好独立且要求有效权益。后台不改变compose历史补发限制 |
| 原claim/lease/status | pending租约5分钟，原超时后可重领，23小时旧任务review；原sent只表示send返回。现在过期租约及超时均unknown/review，停止自动重发；failed仅明确未接受。原pending/sent/review/cancelled表保持兼容 |
| 原Resend send | 原成功未解析ID，异常丢失分类。现在解析ID/供应商，明确拒绝与未知分离。成功仍为accepted；历史sent不回填虚构消息ID/发送时间 |
| 本地outbox | 私有文件保存，无网络；返回local模拟ID。只用于隔离验收；真实送达须真实供应商证据 |
| T05 monitor_runs | 复用私有表的最近任务结果/检查时间，48h预算；运行成功、校验通过与出版分别判断，未产生新SSH/API日志读取能力 |
| DatasetHolder / API | 当前合法数据对象、重载错误标志、当前鉴权/数据库请求；失败不返回原路径/错误。加载正常不保证新数据采集完整 |
| 发布 | 当前API启动的MAAS_RELEASE_DIR合法RID；另存受控status/online verify记录。运行版本不证明全站同版本；没有查询生产机器 |
| account-maintenance backup/health | SQLite backup API包含WAL；已有独立复制、integrity/foreign-key和逐表比较。新增可选私有记录输出，backup/restore分别保存；恢复验证只代表这项隔离SQLite检查，不称生产全机可恢复 |

## 实现与处置

统一分页检索两类任务，详情仅必要白名单；失败明确重试、未知/review先受控CLI查供应商或保存验签回执，再在页面核对证据。管理员不能直接填pending或“已送达”。重试只恢复原任务的queued，保留ID、冻结body、供应商key和业务去重；发送前再查当前用户偏好/权益。退订/撤权后禁止重试；发送中的退订不能隐瞒已接受/未知结果。异步发送在事务外，结果按领取租约匹配写入，迟到尝试仍保留记录。

新增本地/真实签名回执导入器：严格envelope、Svix raw-body HMAC、签名时钟容差、事件ID去重/冲突、事件发生时间和收到时间，匹配已保存供应商消息ID。较老/重复事件不降级新状态；同时间确定性优先送达。已送达保留终态，后续矛盾事件可在证据历史核查。Resend GET查询仅在运维CLI执行，固定origin与消息ID、超时/大小边界、来源认证；返回正文不存。查询观察时间不伪装成事件时间。

重试与核对使用T01事务审计/版本/幂等，所有普通/Plus账号无管理权限。API没有导入回执、任意重启、shell、SSH、回滚或恢复入口；未增业务订阅/邮件群发/历史补发。

## 生产接入与回滚

1. 按现有发布流程审核并部署API/静态页；部署前由受控运维完成已有SQLite backup。暂停旧digest worker后换新版，避免旧进程继续自动重发未知任务；不同时混跑新旧sender。
2. 新表为幂等加法migration6；历史尝试缺失保持未知。回滚保留新表、审计与回执，停止投递/处置；旧代码会自动重试未知或把所有send结果当sent，必须在恢复worker前核对任务，不能靠应用回滚恢复旧自动重发。
3. 为受控CLI配置原MAAS_ACCOUNT_DB、私有MAAS_DELIVERY_INBOX，API帐号无需读inbox。`npm run delivery --prefix services/agent-api -- query digest:JOB_ID`使用仅CLI的RESEND_API_KEY，真实查询权限需现场核验；不把密钥放浏览器或命令参数。
4. 可用query完成首期，无需上线Webhook。若接回执，外部受控接收器保存精确raw及三个Svix header、及时投送CLI；MAAS_MAIL_RECEIPT_SECRET来自真实endpoint，独立于local模拟。`delivery receipt PACKET.json`重新验签；±5分钟超时包要求供应商真实重放。接收器与权限/传输尚未部署，不能修改旧包时间或把本地签名当真实证据。
5. 在既有维护动作显式加`--admin-records /real/private/inbox`后分别`delivery health FILE.json`导入backup/restore/health。不是后台触发备份；本次没有改systemd或原自动通知默认行为。release.status/verify和mail.adapter的白名单记录由受信运维根据实际检查生成，必须保留原检查时间，不使用导入时间/文件mtime代替。没有生产自动拉取器或定时导入器。
6. 重启、回滚、恢复继续走ops/README既有流程。备份结果不能替代应用启动、全机恢复或公网验收；恢复记录必须明确隔离SQLite验证范围。

CLI查询缺消息ID、404或异常时保持未知，不能证明未发送。历史sent及发送超时没有已存ID的任务不能被本次安全查询适配自动解决；须在供应商控制台人工排查，不允许自由绑定ID/重置pending。Resend查询last_event缺事件时间，明确timeBasis=query；真实email.delivered表示收件服务器接受，不证明阅读。依据：[Resend查询](https://resend.com/docs/api-reference/emails/retrieve-email)、[事件语义](https://resend.com/docs/webhooks/event-types)、[验签](https://resend.com/docs/webhooks/verify-webhooks-requests)、[Svix算法](https://docs.svix.com/receiving/verifying-payloads/how-manual)。

## 本地验收与演示

隔离演示复用 `python3.12 scripts/admin-browser-smoke.py --focus delivery --output /private/tmp/maas-admin-browser-t06`：临时SQLite、真实本机API/静态壳、模拟签名回执与文件outbox；不连接生产，运行后清理私有库/进程，保留截图和脱敏报告。页面路由为 `/admin/delivery/`、`/admin/health/`，不能绕过原管理员登录。供应商送达、真实Webhook网络入口、生产查询权限、生产库迁移、真实备份恢复、蓝绿运行版本/公网全站一致性与大数据量性能均未真实验证。


最终检查记录：

| 检查 | 实际结果 |
| --- | --- |
| API build / 公共合同生成检查 | 通过 |
| 全量 `npm run test:compiled --prefix services/agent-api` | 162/162通过，含16项T06、普通账号/专业投递与T01–T05回归 |
| 最后供应商字段补充复验 | 普通/专业/T06相关39/39通过；未重复无关全量测试 |
| T06专项 | 超时未知、过期租约/派发前过期、确认拒绝重试、冻结body/key、并发领取、重复提交/审计/版本、退订/权益撤销、晚到接受不能伪装取消、回执重复/乱序/时钟差、签名/过期/冲突/ID匹配、官方Svix独立向量、模拟查询/404不证明未发送、健康缺失/过期/依赖失效、权限/Origin/no-store、无远程导入/执行入口均通过 |
| Python `test_account_maintenance.py` | 6/6通过，原WAL备份/隔离恢复/retention/通知mock回归及新记录独立性、失败恢复未知、无新增通知 |
| page-models TypeScript | 通过，含admin-delivery-client |
| Site build | 通过，47461页，含两个noindex私有运行时页面壳；公共归档与价格门禁通过 |
| T06浏览器 `--focus delivery` | 8流程（3个基础+5个T06），真实临时SQLite/HTTP/CLI，桌面与390px移动端；无页面错误、静态无私有数据、本地签名回执明确标模拟 |
| 原T01–T05浏览器回归 | 16流程，0错误；原双窗409、权限撤销与注销清理通过 |
| 工作区检查 | `git diff --check`通过；已有改动保留，不创建提交或部署 |

初次把T06追加到全模块浏览器串行流程后，在原T02双窗测试等待超时；没有把这次组合运行计为通过。T06拆成独立`--focus delivery`隔离进程后，T06与原16流程分别通过；生产限流没有调整。详细材料在 [acceptance/T06](acceptance/T06/summary.json)，截图为模拟投递与健康结果，不能证明真实邮件送达或生产状态。私有临时SQLite、outbox和测试服务已由演示脚本清理。
