# 中英文实现与发布准备验收

2026-10-01（Asia/Shanghai）。状态：本地实现、真实浏览器验收、标准 release 门禁与发布材料完成；生产上线等待用户明确批准。

## 明确版本与产物

- 代码提交：`f5fb68b32328da45ad4c6546a47ffc3032a8c783`。
- 分支：`codex/multilingual-seo`，已推送 origin；main 未推送，仍为 `9dae94680fb6c72e70f3b37f2d4761e6b262cdc1`。
- 候选 RID：`rl_f5fb68b323_6fd3cc403bf9`。
- 目录：`dist-release/rl_f5fb68b323_6fd3cc403bf9/`。
- datasetVersion：`ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`，dataThrough `2026-10-01`。
- 标准构建：`scripts/build-release.sh --commit HEAD`，从干净的上述精确提交执行，使用临时 Python 3.12 环境安装仓库 requirements.txt。

```text
通过: 45 | 失败: 0
全部通过 ✓
[3/6] tracked diff 复查
[4/6] agent-api 生产包（完整编译 → omit=dev 裁剪）
[5/6] 组装 release
[6/6] manifest
✓ manifest: rl_f5fb68b323_6fd3cc403bf9（24336 文件，648183646 字节）
✓ release 校验通过
✓ release rl_f5fb68b323_6fd3cc403bf9 → dist-release/rl_f5fb68b323_6fd3cc403bf9
```

manifest 的 testsSkipped=false，builtAt `2026-10-01T03:59:44Z`。原发布协议 suite 在 macOS 依既有规则跳过 1 个 flock 平台用例；生产真实激活的 flock/nginx 事务仍须线上验收。REST、MCP、RSS、Skill、中文价格页、模型身份与详情、埋点、复制、归档、SEO 和新增中英文/国家检查均通过。

首轮完整门禁为 44 通过、1 失败：原 access-pages 内链检查把首页 lang 查询当作输出文件名。修正为按 URL pathname 校验后，该组和最终全部门禁通过。另一次准备性测试因沙箱禁止回环监听、Python 环境缺少 bs4 未通过；这些尝试不作成功证据。最终使用允许本地测试服务的环境和声明依赖执行，无跳过测试构建。

## 新功能验收

`site/tests/multilingual.test.mjs` 检查 10 个英文静态页面的正文、lang、绝对 canonical、双向 hreflang、内部链接和 sitemap；全部 1,435 条价格记录的 11 个事实/条件/状态单元格与同一校验 release 逐格一致。五个候选详情保留原始价格与数据版本。无英文详情的模型明确链接中文页，不生成虚构译本。

语言检查覆盖 CN/US/HK 默认值、手动优先、显式语言入口、偏好过期/禁用存储、失败回退、英文与中文深层链接不改写、参数与锚点、无译本提示；英文刷新检查固定版本分页与版本变化后保留现有内容。

`services/agent-api/src/tests/country.test.ts` 使用随包真实数据库检查 `223.5.5.5 → CN`、`8.8.8.8 → US`、`1.36.0.1 → HK`、Google DNS IPv6 → US；拒绝非回环 peer、非法地址、X-Forwarded-For/CF-IPCountry 的影响。真实本地 HTTP 验证 no-store、只返回国家、拒绝 POST；数据库超过 21 天返回未知。这是数据库与入口逻辑模拟，不是三国真实浏览器出口验收。

## 真实浏览器

Codex in-app browser 使用本地 Astro preview：

- 桌面英文首页有完整导航、五个重点模型和数据时间；中文切换成功，刷新保留中文；用键盘 Enter 切回英文，再访问无参数首页进入保存的英文版本。
- 390×844 移动视口语言入口可见、导航换行、页面无横向主体溢出；搜索 DeepSeek 得到 12 条记录，叠加 CNY 筛选显示英文空结果提示。
- 英文 DeepSeek 详情有 6 条静态记录和对应中文路径；预览无 API 时点击刷新显示英文失败提示，并保留全部 6 条记录。
- 临时禁用 JavaScript 后，英文详情仍显示标题、正文和 6 条价格。已恢复 JS 与正常视口。浏览器该调用返回异常缓慢，但结果已取得，未以 HTTP 读取冒充浏览器验收。

## 生产状态与审批

上线前 `ops/verify-release.sh --online --expect-release rl_1d65039673_6fd3cc403bf9` 通过四入口同版本验收。生产仍为此 RID，数据版本与候选相同。没有上传候选 release 到 incoming，也没有激活英文站点。

已准备并核验最小国家路由安装包；生产临时目录 `/tmp/maas-country-routing.2ChVpJ/` 保留待审批。候选激活器 SHA-256：`51ba87af3c18df7a6725a431e4156ea467dd2e2dc7cdf164750c994da52eb1d3`。安装脚本 dry-run 通过，备份安装曾成功，随后因生产发布审批拒绝而恢复原激活器；已实际核验恢复后的 SHA-256 为 `5792816251c2f76552ea25c5d1a1ba54dca307f7eabd969a904da4fb13e0f27f`，current 指针不变，未 reload Nginx。备份：`/usr/local/sbin/maasweekly-activate.pre-country-20261001T040031Z`。

自动审批拒绝动作 `git push origin codex/multilingual-seo:main`，理由：main push 会触发生产自动发布；用户授权实现与准备发布材料，但尚未明确授权触发上线。未通过受限 release 路径或其他方式绕过该拒绝。

待批准范围：同步实现代码到 main、安装上述最小激活器升级、使用候选 release 按现有 incoming/蓝绿/四入口验收协议上线。避免 main workflow 与本地已构建 release 重复激活。回滚目标 `rl_1d65039673_6fd3cc403bf9`；先恢复旧激活器，再执行标准 rollback 并 online verify，具体见 multilingual-seo-deployment.md。

## 剩余线上验收

生产英文 URL、国家接口的真实连接地址/伪造头/缓存行为、真实 CN/US/HK 出口、Umami 真实接收、百度实际抓取标签和 Search Console/百度后台仍未验证。IP 功能目前仅候选实现完成，未声称生产已支持。原平台注册、支付与调用的海外可用性未核实。GeoLite 数据许可署名、21 天回退和人工更新/旧数据库清理规则见部署说明；本任务未创建自动任务。
