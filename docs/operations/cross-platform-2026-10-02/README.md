# 跨平台同模型比较验收

状态：已上线，最终 CI 60/60，生产四入口及跨平台接口验收通过。

- Commit：45b0f13b190b11df6ec529217a9a8bce76fad619
- CI：https://github.com/zhangchen456/maasweekly/actions/runs/37042182687
- Release：rl_45b0f13b19_7ce1e40d78d2
- Dataset：ds_7ce1e40d78d251d919041ba58cece40283086450f7e5aa9498ce4964e64f1501
- 页面：https://daily.maas.click/compare/
- 生产平台过滤查询返回 41 条 Sonnet 云平台报价，6 个可用关系与版本一致。
- 浏览器验收：1440px 和 390px；19 行条件报价，无整体溢出，手机首行高约 127px。

本地完整回归第二轮 59/60，唯一失败为站点投影覆盖了图标别名；已修正规范来源并通过 final-logo-regression.txt 针对性复验。final-regression.txt 保留真实失败，不能写成 60/60。最终发布工作流已对固定提交执行全部 60 组检查，60 通过、0 失败，原始凭据见 ci-artifacts/*/release-build.txt。

## 范围

首批支持 Gemini 3.8 Flash、Claude Sonnet 5.5、Claude Opus 5.5。分别比较第一方 API 与 Google Cloud。模型开发者、调用平台、API 标识和历史查询命名空间分别记录；保持原有 modelId、事实身份和历史接口兼容。

关系须有官方模型文档证据，不通过名称相似推断。价格只在相同平台、观察时间、币种、单位、地区、上下文与时间条件下组合输入、输出和缓存。标准实时报价单独展示，批处理、优先档和缓存写入保留在详情中。缺失、过期或证据不完整的报价明确显示待补齐。

## 验证资料

- evidence/：官方页面快照及来源校验信息。
- final-live-collection.txt：最终完整来源采集日志。
- targeted-python.txt、targeted-api.txt、targeted-site.txt：针对性回归。
- full-regression.txt、final-regression.txt：两轮完整回归原始日志，保留发现的问题及真实退出码。
- final-logo-regression.txt：最后修正规范来源后的图标回归。
- browser-result.json、compare-390.png、compare-1440.png：最终浏览器检查及截图。
- site-build.txt、api-build.txt：构建日志。

## 已发现并修正

局部采集会把未运行来源标为 not_run，因此最终发布使用完整采集。Claude 云平台表格的模型名称省略 Claude 前缀，证据现保留真实章节标题，并仅对明确的云平台命名空间验证标题与精确 Sonnet/Opus 5.5 型号；不允许任意别名匹配。

## 后续依赖

2026-10-03 01:35 尝试读取现有 Chrome，会话控制返回 Mac 已锁定且无法自动解锁。Search Console、百度和 Umami 后台状态仍需用户解锁后通过现有已登录会话验证；对象存储桶尚未提供，保持延期。自然定时运行的结果不能由手动采集代替。
