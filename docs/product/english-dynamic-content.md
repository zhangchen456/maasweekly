# 英文动态内容：4B离线翻译

2026-10-12。本次为中文摘要增加英文译文，保留现有摘要生成模型。范围为首页与日归档的要点、平台总评、信源解读、周度串讲；原始证据、API数据事实、正式Plus深度报告正文不在这次动态摘要翻译范围。

`pipeline/scripts/translate-dynamic-en.py` 消费标准数据，由3个并发请求调用 `spark-x2.5-4b`，关闭思考，max_tokens=8192。只让模型输出纯文本，失败或校验不通过最多尝试4次（最后一次用保留字面值的短提示词，再验证同一组事实）；不保存未经校验的模型输出和错误响应体。

中文内容SHA256和提示词版本驱动缓存，位于 `data/derived/translations/en.json`，受现有输入快照及流水线写入锁管理。金额、数字、模型名、参数和日期先保护后还原；验证中文残留、截断、占位符缺失/重复、数字改变、多余格式、不确定语气和网页移除被强化为服务下线。

缓存经唯一 `data_store.project_site` 边界生成 `site/src/data/translations-en.json`，英文页面在渲染前替换完整内容字段，保留实体高亮与原始证据。中文不改变。未译或失败字段明确显示 `English translation pending. Please see the Chinese version for the original.`，原文继续在中文版提供；英文摘要不回显中文，也不复用已过时内容。英文页面的中文残留检查继续阻断其他意外混入的中文。

2026-10-22 修复：保护数字前将中文折扣规范化为应付比例（五折 → 50%、九五折 → 95%），再使用同一占位符和数字完整性校验。准确的折扣翻译不再误报 `numbers_changed`；金额、倍数、数字增减及占位符遗漏的检查保留。

每日和周报工作流在中文摘要生成后、投影提交前运行翻译。专用 `TRANSLATION_API_KEY` 配置为GitHub Actions加密secret，不替换 `LLM_API_KEY`。可选 `TRANSLATION_MODEL`、`TRANSLATION_URL` 覆盖模型和调用地址；客户端不持有密钥，也不触发翻译。缺少密钥时保留已有缓存，不阻塞中文发布。

操作：`python3 pipeline/scripts/translate-dynamic-en.py` 增量回填；`--check` 离线检查当前动态内容是否都有匹配译文，缺译时退出非零。恢复/隔离操作沿用 `run_protocol` 的 `--root`、`--recover`、`--discard-run`。

翻译校验并不能证明每个语义都正确。后续修改提示词或术语时提升 `PROMPT_VERSION`，对新旧译文抽样复核。英文原文中已有推断仍保留，不利用翻译悄悄纠错中文。

本次与跟随系统/浅色/深色主题一起上线；提交、发布ID和线上验证另记录在发布结果中。
