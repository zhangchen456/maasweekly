# 首页选模分组

用户要求：各家旗舰（效果）与主力型号（性价比）优先，专用编程模型独立展示。

首页分组选择独立于SEO历史五型号样本，维护于site/src/config/home-model-selection.ts。每项含稳定型号标识、官方名称、定位说明、官方来源与核对日期。中英文首页共用同一选择与报价模型；全部公开ID、API数据及历史页面保持原合同。

旗舰8项、主力8项、编程专项2项。官方型号未进入本地catalog或没有fresh+complete的报价时，仍保留型号与官方定位链接；不虚构详情页或以旧型号代替。Preview/上一代明确标注。分组表示官方产品定位，不表示独立评测排名。

报价为发布快照中实时/标准档，按国内→global→其他地区、非时段→高峰→非高峰、低上下文档、稳定ID选取，绝不按金额取最低价。输入/输出/缓存必须同来源、型号、币种、单位、地区、计费模式、服务档、上下文及时间条件。仅fresh+complete可展示，已知现价差异的DeepSeek V4 Pro与Kimi K3暂显示价格变更待核验；DeepSeek V4.1 Flash不借用旧调用名报价。

本次只修改首页呈现与选择规则；官网核对发现的价格快照差异未通过手工改数写入公开数据。后续需由正常价格采集与证据协议补齐；展示待核验及官方入口供用户核对。

## 官方核对（2026-10-02）

- [OpenAI型号](https://developers.openai.com/api/docs/models)：Astra旗舰，6.1 Sol平衡能力与成本。
- [Claude型号](https://platform.claude.com/docs/en/models/overview)：Opus5.5长程工作、Sonnet5.5速度与能力均衡。
- [Gemini型号](https://ai.google.dev/gemini-api/docs/models)：3.1Pro预览、3.8Flash当前主力，2.5不充当最新型号。
- [千问型号](https://help.aliyun.com/zh/model-studio/models)：3.8Max、3.7Plus。
- [DeepSeek型号与价格](https://api-docs.deepseek.com/quick_start/pricing/)：V4Pro、V4.1Flash（deepseek-flash）；旧V4Flash调用名与当前版本区分。官网现价与已归档快照存在差异，未沿用旧调用名/旧价冒充最新价。
- [GLM型号](https://docs.bigmodel.cn/cn/guide/start/model-overview)：5.3旗舰与5.3Flash普惠档。
- [Kimi型号](https://platform.kimi.com/docs/models)：K3旗舰、K2.6仍可用通用型号、K2.7Code编程专项；K3官网现价与归档快照有差异。
- [豆包定价](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)：2.1Pro/Turbo不同能力成本档。只采用官方文档，不采用火山社区文章中的互相冲突价格。

验收：类型、选择/缺失/同条件报价测试；首页中英文、汇率切换、分组跳转、缺报价位置、可达详情链接；正式发布全量门禁及四入口。结果随后归档。

回归修复：英文详情从旧5型号扩展至旧URL与本次catalog内型号的并集（16页）；空内容页面维持noindex且不进sitemap，实际页面和hreflang可达。真实浏览器使用明确zh-CN语言，避免自动语言导航误测为英文首页。SEO、多语言、选择/场景匹配及本地浏览器均通过。
