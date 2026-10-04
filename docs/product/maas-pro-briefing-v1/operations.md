# 专业情报运营与部署

2026-10-03，开发阶段。没有执行生产激活、收费、生产数据导入或外部发送。复用现有账号库备份和邮件适配，不另建账号或邮件供应商。

## 配置

账号服务继续使用MAAS_ACCOUNT_DB、MAAS_ACCOUNT_SECRET、MAAS_ACCOUNT_ORIGIN、RESEND_API_KEY、MAAS_MAIL_FROM。PUBLIC_DATA_ROOT必须是已校验发布目录。不要在命令参数、文档或日志中填写真实秘密。

专业服务随账号库启用。新增表与现有用户/关注/免费邮件表隔离；所有免费状态保留。反向代理新增/api/pro/私有路由，16k请求体、同源写入、不缓存、不记录包含RSS秘密的URL。新增专业MCP是/api/pro/mcp；公共/api/mcp仍为五工具。

生产开通前先做现有SQLite一致性备份，验证新增表可恢复。回滚程序版本会忽略新增表，不自动删数据。账户秘密轮换会让已加密RSS地址无法解密，需要生成/分发新私有地址；通用Token哈希验证独立，仍应按运维策略撤销。

## 编辑与发布

在services/agent-api目录运行npm run build，再用npm run pro -- 子命令。下面使用占位内容，时间和操作人需按实际替换。

```sh
npm run pro -- draft /secure/path/content.json editor-name
npm run pro -- review content-id 1 reviewer-name '已逐项核对来源、条件、模型归属、时间精度、局限'
npm run pro -- publish content-id 1 publisher-name '批准出版，本期覆盖说明已核对'
```

review只把不可覆盖的草稿转入审核状态，并记录审核身份和清单。publish必须加载有效PUBLIC_DATA_ROOT并校验目录与证据，发布新版本会取代旧版。纠错：draft导入version+1，correction写具体改动，重大影响critical=true；再review/publish。withdraw需要ID、当前版本、操作人、原因；立即停止全文读取，RSS显示撤回状态，相关报告标撤回。撤回不恢复旧版本。

6份样例位于samples/，都是待审草稿。统计周尚未完成，不应当作正式一期投递。sample=true只表示该份完整内容公开，不能把专业全文当预览。

## 权益与申请

```sh
npm run pro -- applications
npm run pro -- grant user@example.com 2026-10-06T00:00:00+08:00 2026-11-03T00:00:00+08:00 operator-name '已确认试点服务期和约定'
npm run pro -- revoke user@example.com 2026-10-06T00:00:00+08:00 2026-11-03T00:00:00+08:00 operator-name '撤销原因'
npm run pro -- audit
npm run pro -- metrics
```

只能开通已注册账户，开始/结束必填，操作与原因留痕。grant不是支付记录或自动扣款。报价、服务期、延期及退款约定在收款前确认。metrics是近30天事件/去重账号计数，不能当成交额或续费证明。申请与audit含运营信息，输出只在受控终端查看，不对外发布。

## 组合与投递

```sh
npm run pro -- compose 2026-10-05 partial
npm run pro -- compose 2026-10-12 normal --queue
npm run pro -- deliver
```

日期是统计结束周一，对应[上周一00:00，本周一00:00)北京时间。运营检查实际数据覆盖后显式选normal/partial/failed，不因无条目就选normal。首次compose冻结范围并只选择非样例详解与专题；重复不会重写或再次入队。未加--queue仅生成网站可读报告，之后同周期不能靠重跑补发。发布与入队前复核这项选择。

用户先显式开启专业邮件，--queue才为新报告创建任务；不会补发已有报告。普通免费提醒退订互不影响。deliver只有现有专业pending任务，发送前再查当前权益/开关。关键修订或撤回自动创建独立更正任务，未开邮件的人在网站/查询中看更正。

租约5分钟，未确认超过23小时转review，不自动重发。失败退出与review计数须监控；处理前核对邮件供应商投递状态和幂等键，不直接把review改为pending。正文已冻结的未知尝试必须保留原消息；后续更正另发独立任务。

尚未安装周报定时任务。建议周二北京时间10:00，需确认编辑/复核负责人后再配置systemd调度。时间未确认前使用上述人工流程。开发验收只使用隔离本地服务，不向真实邮箱发信。

## 本地验收

npm run test:pro检查权限与状态。npm run test:compiled包含专业回归；公共MCP回归仍单独运行。构建网站后可运行node scripts/pro-preview.mjs：创建临时账户库、6份本地审核样例，打印临时目录；不向外发信。另用python3 scripts/pro-browser-smoke.py 临时目录/fixture.json进行Chromium验收。结束用SIGTERM停止预览，会删临时库和会话信息。截图与browser.json留在acceptance/作为复核材料。

上线前仍要核对至少两类实际Agent客户端、一个真实RSS阅读器，以及经授权试点邮箱实际收信。SDK协议测试和RSS解析通过不能代替这些实用验收。
