# 中英文发布与国家识别运维

日期：2026-10-01。状态：候选实现，尚未上线；最终版本与门禁证据另记验收文件。

## 页面对应

中文原路径对应英文 `/en/`、`/en/models/`、`/en/pricing/`、`/en/method/`、`/en/agent/`。五个模型详情对应 `/en/model/{modelId}/`：deepseek:deepseek-v4-pro、alibaba:qwen-plus、alibaba:qwen3-coder-plus、google:gemini-2.5-pro、zhipu:glm-5.2。

译本清单只包括数据校验通过的首批模型；构建后实际路径参与 sitemap。其他模型详情、日报、周报、证据、变化与接入详细配置保留中文并明确标记。英文价格查询用公开 release 原币种报价，提供搜索、平台、组件、币种与健康状态筛选，支持共享 modelId/familyId 参数；中文价格页的人民币计算器、GPU 和芯片补充数据提供中文入口，英文页不隐式换汇。

## 国家来源、信任与失败

生产域名 DNS 在核实时解析到 Nginx 服务器 47.237.135.97。已读取实际 nginx -T，未发现 real_ip、proxy_protocol 或国家头转换规则。当前方案信任 Nginx socket 地址 `$remote_addr`；若以后增加 CDN/代理，先重新核实真实地址边界，不能把客户端 X-Forwarded-For 直接接入。

新增 `GET/HEAD /_locale/country`，不属于公开 REST v1。Nginx 使用现有回环 agent_api upstream，并强制覆盖 X-Maas-Client-IP，清除 X-Forwarded-For、CF-IPCountry；客户端原值不能影响查询。agent 仅接受回环 peer 的单一合法 IP 字符串，只返回 `{country: "CN"}` 或 `{country: null}`。无原始地址/精确位置输出或新增日志，Nginx 该 location 关闭 access_log，关闭代理缓存，响应 no-store。现有站点常规访问日志不因此新增内容。

数据库随锁定的 `geoip-country@5.0.202609300220` 生产依赖打包，包含 IPv4/IPv6 数据。查询在内存中完成，没有定位外部请求。软件 Apache-2.0；数据库须保留 MaxMind 署名、CC BY-SA 4.0 和当前 GeoLite EULA，原包 LICENSE/EULA 保留于 release。已阅读官方 EULA（https://www.maxmind.com/en/geolite/eula），其中要求及时更新并在更新发布后 30 天内停止使用和销毁旧版本。数据库版本日龄超过 21 天时返回 null，停止使用旧数据，前端按回退规则工作。

维护方式：在 21 天内人工检查新版本，更新精确依赖和锁文件，跑国家查询测试与标准 release 发布。不要在线就地修改 node_modules 数据文件；保持 release 完整性。按许可在期限内清理含旧数据库的本地/服务器/构建缓存与旧 release；先确认回滚仍有可用新版本，不删其他数据。现有 daily pipeline 不更新 npm 依赖，本任务没有创建定时任务。若不能承担数据库更新与旧包清理，应停用此源并改用满足运维条件的国家数据库，不声称 IP 功能持续有效。

前端只在 `/` 且无显式 lang 时查询，约 1 秒超时；读取未过期手动选择在前，查询后再检查手动选择，避免并发覆盖。CN 中文，其他有效国家英文；失败时首选浏览器中文则中文，否则英文，无浏览器语言则中文。`/en/...` 和中文深层链接均不自动跳转。无 JS 首页静态中文；地址栏 `?lang` 导航及偏好记忆依赖 JS，但直接语言 URL 和静态核心内容始终可用。定位期间可能短暂显示中文首页，随后导航；不隐藏静态正文。

手动切换保留对应页面语义参数及锚点；无译本回到目标首页并显示提示。180 天第一方 localStorage 偏好仅由手动切换/显式首页 lang 写入，访问语言链接本身不改长期偏好。存储禁用时显式 lang 防循环。Umami 等待首页语言决策，自动导航的中间页不启动 tracker；事件类型不新增，英文模型点击保持现有 model_click，page_type 正确识别英文路径，路径区分语言。

## 发布与回滚

1. 精确提交、干净工作区，`scripts/build-release.sh --commit <SHA>` 全量构建，testsSkipped=false；核验 manifest。
2. 国家路由需要更新现有 root 激活器。候选 `ops/install-country-routing.sh --dry-run` 可审查；`--apply` 只允许已核实基线 SHA `5792816251c2f76552ea25c5d1a1ba54dca307f7eabd969a904da4fb13e0f27f` 或相同候选。持有现有 release.lock，备份后原子替换 root:root 0750，不直接 reload Nginx，不改 current。
3. 沿用 release 通道 incoming 上传、标准蓝绿激活、nginx -t、事务切换和 `ops/verify-release.sh --online --expect-release <RID>`。新路由由激活器生成，避免手工 include 被下一发布覆盖；公开四入口保持既有版本一致校验。
4. 对真实生产国家入口检查 no-store、伪造头不能改变国家和 GET/HEAD 响应；从可用真实国家出口核验 CN/US/HK。数据库样本测试不是这些国家的真实浏览器出口验收。
5. 复核英文 URL/canonical/hreflang/sitemap、百度标签、语言切换和 Umami；登录平台无条件时记录未验证，不把 HTTP 读取冒充平台验证。

基线回滚 RID：`rl_1d65039673_6fd3cc403bf9`（须发布前再核对 current）。回滚前恢复安装时记录的 activator 备份，再执行 `ops/rollback-release.sh <previous-rid> --reason "multilingual rollback"` 并 online verify。这样旧生成器移除国家 location；页面/服务/三个 include 按既有协议恢复。紧急回退若先用新激活器切旧 release，国家接口可能返回未知/404，首页回退仍可用；随后恢复旧激活器并重新生成旧路由。

## 验收边界

新增测试覆盖生成 HTML、双向语言链接、所有原币种价格逐格一致、首批详情、语言优先级与持久化、超时/存储失败、参数锚点、英文刷新分页和版本变化保留旧数据、真实国家数据库样本、请求方法和缓存。标准全量回归与生产线上验收的实际输出在完成后记录。
