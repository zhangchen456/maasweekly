# 修复官方抓取与数据新鲜度，并更新已核对榜单

公开状态曾把“成功但内容未变”的来源保留为旧失败；火山/腾讯正文抓取与Kimi/Vertex价格表也因站点改版降级。本次恢复抓取，使用同一已提交输入快照中的真实运行状态，未再次观察到的历史价格保留原值并标stale。

- 火山2路、腾讯4路已由正式抓取函数实测恢复；仅读取官方正文，HTTP错误/挑战页不记成功。
- Kimi按叶子表头区分输入/输出/缓存及TTL；Vertex支持新增100K列，并继续在明确200K列读取现有Sonnet/Opus价格。
- 通过RunJournal全量刷新价格，10/10来源成功；从官方证据重新核对AA、SWE Verified mini-SWE-agent、Terminal-Bench 2.1 rev.6。
- 真实Umami脚本隔离测试生成copy/model_click各1次，所有上报被拦截，未修改追踪代码。

验证：从干净提交343944ea51执行标准发布构建，76项检查通过、0失败，clean-tree和manifest校验通过；发布包rl_343944ea51_f1b4ab685a24。英文刷新测试已改为从已翻译且有价格记录的详情页取样，保持推荐质量要求。此后的文档收尾不改变受验代码和数据。

证据：docs/operations/runtime-freshness-2026-10-26/README.md、validation.json、validation.txt。

发布：PR #10已合并，workflow40264337387成功；生产重新执行76项检查、0失败，四入口验收与独立线上核对通过，release为rl_162fb34984_f1b4ab685a24。详见本目录README.md与deployment-validation.*。

剩余：Arena的Cloudflare拦截；正式周报仍为2026-10-13；此次手工榜单复核未新增自动调度。
