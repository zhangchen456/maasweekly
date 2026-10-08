# 缺陷与可派发修复清单

## D01 / P1 / T03、T05联合链路：监控失败不参与覆盖与出版判断

类型：代码/集成缺口。验收版本：snapshot SHA256 `2dc83b127fd6af7e2f1f135b6295992e3cbc2620f61604a910af57e47d4f8346`，Git基线5c48d8e34cc2cab31a3f62e8bdf4b2bd5c58c972及未提交交付。严重程度P1：阻塞“信源失败→覆盖限制→出版判断”联合要求，未发现权限泄露或金融损失。

复现步骤：

1. 在临时SQLite初始化AccountStore/AdminStore/AdminMonitor/EditorialStore，加载快照真实历史公开Dataset。
2. 导入`google-vertex-changelog`在2026-09-27T10:00Z的合成抓取失败，coverage=missing，monitor健康degraded。该时间属于2026-09-28期次统计窗口，同期素材包含Google Vertex release-notes。
3. 模拟公开Dataset信源状态未同步失败（sourceStreams=[]），保留真实历史素材与dataThrough；这是隔离故障夹具，未修改原始公开档案。
4. 创建该期次，prepare选择normal，mock生成、保存revision、六项人工审核、publish。
5. 运行保存的`source-publication.mjs`，查看`source-publication.json`。

预期：工作台能发现同窗口相关信源失败，明确披露冲突/覆盖限制，并要求确认相应限制后才审核/出版；不能仅因公开投影未同步就无提示放行normal。不要求所有历史抓取失败永久阻断所有内容。

实际：monitor为degraded/missing、consecutiveFailures=1，editorial issue仍coverage=normal且state=published。prepare只检查Dataset.status.sourceStreams；审核/出版checkPackage校验冻结与当前Dataset，无T05监控关联或异常提示。

影响：监控已知失败与公开Dataset状态不同步时，编辑可能误判覆盖完整；单模块T03/T05测试全部通过不能覆盖此风险。

证据：source-publication.mjs（自编独立复现）、source-publication.json；快照`services/agent-api/src/editorial-service.ts` prepare/review/publish，`editorial-checks.ts`；同目录snapshot-manifest.json绑定源码。

可直接派发：请实现T03与T05的同窗口、同来源覆盖关联，明确数据版本与任务观察时间关系；工作台展示相关失败与投影不同步，不以未运行/无变化误判失败。保留人工partial/覆盖说明出版路径，相关状态变化使放行依据重新核验；增加实际HTTP或浏览器联合验证。不要简单让任意历史异常阻止所有期次，也不要自动改公开事实。验收方不修业务。

## B01 / T08 / 配置缺失与未交付

无支付渠道。真实供应商适配、金融写入任务、托管结账和供应商沙箱未完成；候选价格/币种/周期/生效规则待决。模拟测试通过，整体状态“验收阻塞”。用户已要求挂起，不等待或补实现，不作代码失败、不收费。

## E01 / 外部与生产验证未完成

真实Umami、真实邮件供应商查询/回执网络、真实模型质量/费用、代码托管及生产发布验证、生产迁移/nginx/systemd/备份恢复没有本轮证据。属于待验证，并非独立证实代码缺陷；不得由开发summary或合成online引用替代。

未独立确认其他可后续修复的代码缺陷。不要把首版已注明的JSON编辑、纯文本渲染、人工核验引用或未接入任务误作失败。
