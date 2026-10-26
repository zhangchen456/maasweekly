# 运行与数据新鲜度修复（2026-10-26）

状态：**本地候选已验证，尚未推送、合并或发布**。基于生产提交 `6fb8e2b7517d099aca4fa27822af8a889ce961a8`。

## 问题与修复

公开来源状态此前仅联查“发生变化”和“抓取失败”，成功但未变化的来源会保留旧失败或显示 unknown。
现在优先读取同一 committed InputView 的 `data/normalized/source-runtime.json`；来源最后尝试、最后成功时间均来自实际运行，历史没有运行记录才使用旧窗口。失败原因只公开固定代码。

火山模型列表与更新公告旧链接已跳转到新版 JavaScript 文档站；腾讯的 WAF Cookie 转交 curl 流程失效。
保留原始正式来源，在 curl 无有效正文时，直接在无登录浏览器上下文读取官方正文容器，校验最终域名、HTTP 状态及内容，关闭浏览器后返回文本。
HTTP 错误与挑战页不会变成成功快照。火山2路、腾讯4路的正式抓取函数联网复测均成功。

Kimi 当前两张价格表有分组表头，K3为六列、K2为四列。按叶子标签映射输入、输出、缓存命中与缓存写入5m/1h。
Vertex Anthropic 增加100K列，Sonnet/Opus继续只读取明确的200K列，未知表头继续拒收。适配器版本分别升为 `kimi-4`、`vertex-3`。
联网复测分别接受24条/89条事实，0拒绝。

复核还发现：来源恢复成功后，未再次观察到的历史价格仍可能被整体标成 fresh。
现在保留价格版本、金额与观察时间，但将这类价格的 quality 标为 stale / `not_observed_in_latest_fetch`，避免用来源的新日期替旧报价背书。

AA、SWE-bench Verified、Terminal-Bench 2.1 rev.6三份榜单从官方原始页面重新核对，通过 RunJournal 写入标准输入及站点投影。
SWE保留mini-SWE-agent环境并记录每行版本，Terminal保留2.1口径；观察日期与评测发布日期明确区分。
原始来源与哈希见 [official-sources.json](official-sources.json)，原文由对应 RunJournal 的 contentPath 留存。

## 功能事件

使用当前真实Cloud Umami脚本，在隔离Chromium内模拟复制与模型链接点击，分别生成1次正确事件；跳转后有正确的页面浏览。
所有上报由本地路由拦截，生产发送0次，没有未知外联。未发现埋点故障，没有修改追踪配置或事件代码。
见 [隔离上报结果](analytics-isolated-result.json)。这验证到客户端请求生成，不代表生产接收端或真实用户转化已经改善。

## 尚未解决

- Arena官方页面在无登录抓取环境仍返回Cloudflare拦截，保持失败披露；未切换到第三方榜单，未自动解验证码。
- 最新正式周报仍为2026-10-13。周报需要独立编写与事实核对，本次未把素材汇总当作新周报发布。
- 手工榜单此次完成重新核对，未新增自动调度。

## 验证

标准发布构建提交：`343944ea51de570b7333b0002b2113341c95e580`；**76项完整检查通过、0失败**，构建后clean-tree检查与manifest校验均通过。
包括价格/归档/恢复、SEO/多语言/页面行为、REST/MCP真实数据以及后台隔离浏览器验收。Python 3.12.14、Node 22.22.3，依赖采用项目锁定版本。

第一轮75通过/1失败的英文刷新测试已修正：从已翻译且有价格记录的详情页选择刷新样本，不依赖推荐列表必定非空，不放宽推荐条件；第二轮完整构建通过。

本地发布包：`dist-release/rl_343944ea51_f1b4ab685a24/`；75,352个文件，2,384,569,087字节，已保留供审批和后续使用。
公开数据版本：`ds_f1b4ab685a244b3358a36713c2d89cf59ac62b0ebe206fc86320e4f82bb1456b`，数据截至2026-10-26。
候选状态为67路正常/1路Arena失败，10路价格正常；历史未再观察到的报价保留原金额和时间并标stale。

完整构建记录见 [validation.txt](validation.txt)，机器可读结果见 [validation.json](validation.json)，候选覆盖状态见 [candidate-data.json](candidate-data.json)。
实际读取证据见 [信源复测](sources-live-result.json) 与 [价格复测](prices-live-result.json)。

Git推送被自动批准审查拒绝，未向远端提交本次源码或数据；本地完成后需用户明确批准推送并创建PR。
