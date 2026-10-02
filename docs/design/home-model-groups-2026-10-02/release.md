# 首页模型分组线上验收

状态：RELEASED，2026-10-02。commit `e8388dbcd56a77bbf17c9a3bd6eb305eae71f73c`；current `rl_e8388dbcd5_0da7f0c0f2bc`；previous `rl_4e2496d2f8_0da7f0c0f2bc`。
[正式CI](https://github.com/zhangchen456/maasweekly/actions/runs/36981337804)成功：完整53/53、标准构建、蓝绿激活、REST/MCP/RSS/Skill四入口、诊断artifact均通过。原始构建/发布日志与job结果归档于ci-artifacts和ci-run.json。

首页独立维护旗舰8项、主力8项、编程专项2项。八家主要厂商按官方资料定位分组，包含Preview/上一代标识；当前可展示报价分别2/5/2项，其余明确待补齐或待核验。型号缺报价不再从首页消失，也不以旧型号替代当前型号。完整选择依据与已知采集差异见README.md及site/src/config/home-model-selection.ts。

本地严格类型、模型输出对账、选模与同条件报价匹配、SEO、多语言测试通过。真实Chromium本地及线上1440px/390px检查三组数量、专用编程隔离、缺报价位置、定位链接、分组锚点、币种/自定义汇率/非法输入、报价条件，无页面脚本错误和全页横向溢出。中英文首页均18项；新增英文详情（包括无报价页面）真实HTTP200。

英文详情保留旧五型号页面，并增至16个已进入catalog的入选/历史型号；空内容维持noindex，sitemap不列入空内容页面。公开稳定ID、API金额与数据版本未改。DS `ds_0da7f0c0f2bcd5df62281a262539b65a1742e3fbd710a14724359b58675c1b13`、dataThrough2026-10-02。

证据：local-browser.json、online-browser.json、online-http.json、桌面旗舰与移动主力截图、build.txt、seo.txt、multilingual.txt、selection-tests.txt。线上中文测试显式使用/?lang=zh，避免海外测试IP自动导航英文；这符合站点语言选择协议。

回退沿用标准helper：

```bash
/usr/local/sbin/maasweekly-activate rollback rl_4e2496d2f8_0da7f0c0f2bc --reason homepage-model-groups-rollback
```

随后检查四入口、current/previous和中英文首页。本次没有API运行配置变更。临时浏览器/构建日志与脚本已清理；保留验收摘要、截图及CI原始artifact。

后续价格数据工作：最新OpenAI/Claude、Gemini Pro、Qwen Max与DeepSeek Flash缺可展示的完整报价；DeepSeek Pro、Kimi K3快照与官方现价差异暂被首页抑制。需经正式采集/归档/投影协议补齐，不通过首页代码手工伪造新事实。本次交付为首页分组和展示规则改造。
