# AR-04：信源适配器与可恢复管线

状态：RELEASED（2026-10-02），见[线上验收](./release-2026-10-02.md)。

## 目标与范围

厂商改版只需修改相应适配器；一次来源失败可以重试或离线重解析；抓取并行时不会竞争覆盖事实和站点文件。

先改造已有价格管线，再将同样的运行协议应用到通用信源/榜单。保留当前调度平台，不引入外部任务队列。交付适配器模块、运行记录、重跑命令、fixture 回归与 `AR-04-result.md`。

## 当前入口

`pipeline/pricing/{extractors,providers,registry,normalize,archive}.py`、`pipeline/scripts/{fetch-prices,fetch_sources,fetch-leaderboards}.py`、`tests/test_pricing_extractors.py`、`tests/fixtures/pricing/`。

## 4A. 拆分适配器

建议结构：

```text
pipeline/pricing/adapters/
  common.py
  openai.py
  anthropic.py
  google.py
  deepseek.py
  kimi.py
  glm.py
  doubao.py
  qwen.py
```

统一适配器协议：输入为 ContentSnapshot 与 SourceSpec，输出为既有 ExtractionResult。解析阶段不写归档、不更新 current、不访问站点目录；获取网页与解析内容分离。

保留 source_key、extractor_version、Evidence locator、Decimal 金额与归一规则。纯文件拆分不提升适配器语义版本；真正改变抽取逻辑才升版并描述影响。原 `get_extractor` 暂作兼容入口，调用方迁完后再移除。

## 4B. 明确运行记录与幂等

每次执行有唯一 runId，并记录 sourceId、attemptId、输入 contentHash、extractorVersion、规则/Schema 版本、输出 hash、开始/结束时间与状态。复用 `data/price-runs` 已有记录，扩展前先登记差异，避免平行创建另一套 price run。

区分三种身份：一次执行 runId、来源的多次尝试 attemptId、同一输入/处理版本的幂等键。新的 HTTP 观察即使内容相同也可能更新观察时间；离线重解析必须保留原 fetchedAt，不能冒充今天的新观察。

状态至少区分：成功、无变化、部分成功、失败、未运行。`--only` 未运行的来源不得误标失败，也不得刷新它的 lastSuccessAt。

## 4C. 并行与提交

先设置有界并发（初始 2–3，按基线调节）、每域限速、请求超时、重试次数与退避。复用浏览器实例时保证 context/page 释放；不要一次为所有 URL 创建无限浏览器任务。

各来源写入独立 run 暂存目录，全部产出交给单一归档/投影阶段提交。原子替换单文件不足以保证多个文件的一致性，应设计 staging + 校验 + 提交标记/current 指针流程。进程中断后可明确识别已提交与未提交产物。

外部请求失败可重试；解析/Schema 失败应保留快照供诊断，不无限重试。可选来源失败保留旧事实并标 stale；全失败的退出码与现有工作流健康状态保持可判定。

## 4D. 重跑与离线复现

提供并记录以下 CLI 能力，具体参数名由实现固定：

- 只重跑指定 run 的失败来源。
- 指定 source 与历史 snapshot，用指定 extractor 版本离线解析。
- dry-run：输出差异，不写真实归档或 current。
- 对同一已提交输入重试：不重复产生事实修订和变化事件。
- 从崩溃暂存恢复或清理指定未提交 run，不触碰已提交归档。

所有命令在 `AR-04-result.md` 给出可复制示例；参数不能要求执行者手工修改代码常量。

## 验收标准

- [x] 拆分前后所有厂商 fixture 的事实、证据、warning 一致。
- [x] 一个厂商适配器异常，其余来源正常产出，失败来源状态和沿用事实正确。
- [x] 同一输入重试两次不产生重复事件；同日成功后失败不会回退到昨天。
- [x] 抓取中断、归档前中断、提交时中断均可恢复，current 没有半成品引用。
- [x] 离线重解析不联网、不更改原观察时间，dry-run 不写生产数据。
- [x] 并发上限与单写入边界通过测试，资源释放后没有残留浏览器进程。
- [x] fixture 回归、价格归档/公开导出回归通过，真实少量来源冒烟作为独立证据记录。

现有基础命令：`python3 tests/test_pricing_extractors.py`、`python3 -m unittest discover -s tests -p 'test_price_archive.py'`，再增加有意义的运行恢复和幂等测试。日常 CI 使用离线 fixture，真实网站访问不要成为所有代码提交的强制测试依赖。

## 发布与回退

先以串行模式运行新适配器与新调度，再启用有界并发。适配器拆分与并发启用分别提交，便于定位问题。回退时停用新调度并恢复兼容入口；保留已归档的合法事实和证据，未提交 staging 按 run 清理。
