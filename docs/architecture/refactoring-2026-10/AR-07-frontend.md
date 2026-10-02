# AR-07：页面数据模型与领域组件

状态：RELEASED（2026-10-02），见[线上验收](./release-2026-10-02.md)。

## 目标与范围

页面只负责布局与交互组合，数据读取、价格条件和新鲜度计算在公共层完成。新增语言或模型页面时，不再复制完整业务计算。

本任务维持现有页面用途、URL 和主要交互，按页面逐步重构；不顺带重新设计视觉、翻译所有内容或换前端框架。

交付 ViewModel、领域组件、现有价格模板的替代实现、页面回归与 `AR-07-result.md`。

## 当前入口

- `site/src/pages/{index,pricing,changes,models}.astro`、`model/[modelId].astro` 与 `en/` 对应页面
- `site/src/lib/{release,model-pages,price-display,locales,seo}.ts`
- `site/src/components/{EnglishPriceTable,ModelPriceLinks,HomeOverview}.astro`
- `site/scripts/{build-price-fragment,render-price-ledger}.mjs`
- `site/src/data/pricing/price-ledger.template.html`、页面 scripts/styles 和相关 site/tests

## 7A. ViewModel 与索引

将页面中的文件读取、分组、筛选、证据查找与格式化整理为有类型的 ViewModel。输入为 AR-03 的标准数据/公开 release，输出为页面需要的字段。

构建期一次建立 modelId → prices/changes、evidenceId → evidence 索引；避免 `modelPage()` 对每个模型反复扫描所有价格和重新创建全部 evidence Map。

展示格式和业务值分开：货币换算、原币种、单位与条件不能在组件中各算一遍。旧中文台账的人民币估算和英文原币种展示应明确标记不同用途，不能为了共享组件改变用户看到的价格语义。

## 7B. 提取领域组件

优先复用并演进已有组件，按实际重复提取：

| 组件/模块 | 职责 |
| --- | --- |
| PriceTable | 展示价格行与排序/筛选入口，不计算事实身份 |
| BillingConditions | 完整展示单位、地区、计费模式、档位和时段 |
| DataFreshness | 展示实际观察时间、fresh/stale/unknown 与原因 |
| EvidenceLinks | 从已验证 ViewModel 渲染证据与官方来源 |
| ChangeList | 展示条目与永久链接，保留撤回和证据等级语义 |
| locale messages | 文案、日期/数字格式，不承担数据选择与身份映射 |

中英文可以有不同首页和栏目范围，共享底层模型与组件即可；不要强行把英文首页改造成中文首页的直译版。

## 7C. 逐页迁移

建议顺序：模型详情/列表 → 英文价格表 → 中文价格页 → changes → 首页。

中文价格页先记录搜索、筛选、币种、2–5 模型比较、计算器、复制、空态、dialog/键盘交互的现有行为，再把 HTML fragment/rendered 生成链逐步替换为 Astro 组件与独立 TS 脚本。GPU/芯片分区可继续独立消费自身数据，不强塞进 token 价格模型。

所有消费者迁移后才删除模板生成脚本及 package.json/workflow 中的调用。不能先删构建步骤让未迁移页面失去数据。

## 7D. 页面契约

保持 URL、永久链接、canonical/hreflang、结构化数据、RSS 指向与 sitemap 一致。数据缺失与 stale 状态不能静默隐藏成看似正常的 fresh 价格。

页面只有一个 analytics 入口；`model_click`、`outbound_click`、`copy` 保留既有语义和字段白名单，组件重用不增加重复监听。复制成功才上报，不记录正文。

## 验收标准

- [x] 页面中业务数据读取经统一入口完成，目标页面不再散落 fs + any 的独立计算。
- [x] 多模型构建使用复用索引，模型数增长时不反复建立全量证据 Map。
- [x] 价格原值、单位、条件、freshness、证据链接和排序与迁移前一致。
- [x] 搜索/筛选/比较/计算器/复制等现有交互通过浏览器验证，桌面与移动宽度可用。
- [x] 中英文模型页同 datasetVersion，保留各语言既定功能范围；切换语言不丢失对应模型。
- [x] SEO、多语言、价格、记录、模型详情及 analytics 现有测试通过，无重复埋点。
- [x] 所有调用方迁移后清理旧模板/脚本，没有并存的第二套业务计算。

测试以用户行为、输出数据与页面语义为主，不新增只检查组件文件名/内部 HTML 拼接的脆弱测试。视觉复核保留少量关键页面截图或浏览器验收记录，不能仅以构建成功代替。

## 发布与回退

按页面拆分提交或短期保留旧页面入口用于对照，每一批均可独立验证。正式发布后回退使用既有 release；旧生成链只能在所有页面迁移验收后删除，避免回退时缺少输入。
