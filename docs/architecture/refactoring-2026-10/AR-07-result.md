# AR-07 前端数据层与组件验收

状态：RELEASED（2026-10-02），见[线上验收](./release-2026-10-02.md)。 以下实施候选及本地验收描述保留历史记录。

模型页按构建复用已验证 release 与 model→prices/changes、evidence 索引，保留原排序、active 最近 90 日窗口及最多 10 条变化。107 个模型的价格/变化输出与旧逐页扫描完全一致；未解析价格没有被删除。索引局部五轮测量中位数约 128 ms → 2.4 ms，测量只覆盖选择与索引工作，不能据此推导整站构建同等比例提速。

首页/价格/GPU/芯片的数据读取集中到 page-data，有类型 ViewModel 与展示格式分离；模型条件、观察时间/质量、证据链接和变化列表抽取组件。中文台账完整迁移为 Astro 组件、独立严格 TypeScript 和 CSS，保留 Decimal 原值、条件分组、排序、人民币估算、比较与计算器。英文沿用原币种展示和既定模型范围。旧模板、fragment/rendered、两个生成脚本及 npm/workflow 调用已全部移除，没有保留第二条业务生成链。

修复旧 CSS 生成器遗漏 @media/@keyframes 左花括号的问题，恢复移动布局规则。390px 视口下文档宽度也是 390px，价格/比较表在自身容器滚动。实际 Chromium 验证桌面/移动价格页 13 个状态与报价详情；首页币种切换、成功复制、搜索空态与重置；中英文模型页表格、证据链接与 datasetVersion。迁移前后结构化结果完全一致，没有脚本错误。UI 契约测试使用实际构建页和相同 TS，重复挂载保护也通过；缺失页面会使测试失败。

完整标准 release 回归 **52/52，退出码 0，370.038 秒（含打包）**。新门禁包括页面 ViewModel 严格类型检查、107 模型对账和安全 JSON 注入；既有价格、模型详情、记录、SEO、多语言、analytics、复制、REST、MCP、归档及工作流门禁均通过。独立 typecheck 过程中修复两处原有 TypeScript 类型收窄问题，未改变运行时判断。

候选 `rl_a4c691f503_6fd3cc403bf9` 共 24,363 文件、702,985,890 字节；仓库外仅生产依赖实际启动通过 REST/MCP，RSS 与 Skill 八文件 hash 一致。datasetVersion 仍为 `ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`，dataThrough=2026-10-01。没有发布到生产。

证据：[完整回归](./acceptance/AR-07/regression.json)、[浏览器对账](./acceptance/AR-07/browser-parity.json)、[旧页面行为](./acceptance/AR-07/baseline/browser.json)、[最终候选行为](./acceptance/AR-07/candidate/browser.json)、[索引成本](./acceptance/AR-07/index-cost.json)、[仓库外运行](./acceptance/AR-07/standalone-release.json)。桌面/移动截图保留在 baseline/candidate 目录；局部测量不包含网络与完整构建，也不是独立生产容量指标。

维护入口、复核命令与回退说明见 [页面数据层维护](./frontend-data-operations.md)。回退使用旧 immutable release 或完整旧提交，不从孤立模板重建。后续 AR-06 只做已授权的本地存储迁移/恢复演练；AR-08 继续复核整体容量与发布指标。
