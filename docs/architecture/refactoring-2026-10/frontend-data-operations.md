# 页面数据层与价格组件维护

模型详情和中英文价格展示使用 `site/src/lib/model-pages.ts` 的一次已验证 release 与复用索引。模型目录、prices、active 最近 90 日 changes、evidence Map 均按构建快照建立；`loadVerifiedRelease()` 本身保持每次完整校验，直接读取/坏 manifest 测试不会被缓存绕过。索引保留原 release 排序，近期变化最多 10 条，不加入撤回项；未解析身份仍保留在公开价格集合中。

首页和价格页的文件访问集中在 `page-data.ts`，有类型展示模型在 `home-page.ts` 和 `pricing-workspace.ts`。价格/GPU/芯片/logo 使用 AR-03 标准输入；首页消费统一 projector 的 daily/weekly 展示投影，不独立拼接第二份摘要。构建前 projector 和档案门禁必须通过，pending 管线不能作为候选输入。缺少可选行情快照展示原空态，损坏文件必须使构建失败。

中文价格工作台由 `PriceWorkspace.astro`、`price-workspace.ts`、`price-workspace.css` 构成，不再生成或注入 HTML fragment/rendered。数据使用转义的 application/json script，模型目录取自完整校验的公开 release；处理脚本由 Astro 编译为独立 module，挂载有重复初始化保护。独立严格 TypeScript 检查通过 `site/tsconfig.page-models.json` 执行，并接入完整回归。

中文工作台保留人民币成本估算和手动汇率；英文表格保留原币种与单位，首页以已披露的一个来源档位展示估算。三个用途沿用各自已有汇率口径，不能共用一个“最低价格”函数。条件、单位、状态与时间的中文/英文格式集中在 price-display；金额仍来自 Decimal 字符串，展示估算不用于事实 ID 或归档比较。

BillingConditions/DataFreshness 渲染完整条件、观察时间和质量状态；EvidenceLinks 供中英文价格展示复用；ChangeList 展示近期有效记录及永久链接。模型刷新继续使用既有 REST 固定版本分页，服务端渲染与刷新格式均调用 price-display。GPU 与芯片保持独立行情单位，不混入 token 价格模型。页面、语言范围、canonical/hreflang/RSS/sitemap 和 analytics 入口保持原契约。

复核命令（仓库根，声明的 Python 环境和 Node 22）：

```bash
node services/agent-api/node_modules/typescript/bin/tsc --project site/tsconfig.page-models.json
node site/tests/page-models.test.mjs
node site/tests/model-identity-ui-contract.test.mjs
python3 scripts/architecture-browser-regression.py site/dist /tmp/maas-page-browser
python3 scripts/architecture-regression.py --task AR-07 --release-workspace /path/to/same-commit-clean-checkout
```

UI 契约测试读取实际构建页面，再执行相同的独立 TS 源码；构建产物缺失会失败，不再悄悄跳过。浏览器探针仅启动本地静态服务，外部请求被拦截；测试价格筛选/比较/条件详情/计算器/汇率/键盘关闭、首页复制/币种/搜索，以及两种语言模型页，保留桌面/移动截图和结构化状态。完整回归另覆盖真实 REST/MCP、SEO、多语言、记录及埋点。

旧生成器漏掉 @media/@keyframes 左花括号，内嵌旧 CSS 的移动规则因此失效；迁移样式修复该问题。移动页宽度 390px，文档宽度也为 390px，价格目录与比较表在各自容器内横向滚动。价格业务状态/详情对账与这项布局修复分开记录。

回退沿用已归档 immutable release。旧模板和脚本已从当前代码删除，所有消费者均迁移；需要回退旧生成链时，必须回退到完整旧提交或旧 release，不单独复制一个过时模板。尚未发布，无生产页面或 CDN 变更。
