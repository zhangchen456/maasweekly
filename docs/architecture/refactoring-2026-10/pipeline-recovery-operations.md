# 管线运行与恢复（AR-04）

以下命令在仓库根执行，Python 3.12 与 `requirements.lock.txt` 一致。未部署到生产；运行脚本会修改指定输入根，`--input-root` 可指定隔离演练目录。需要原配置文件与合法标准数据，不能给空目录凭空创建业务事实。

## 价格采集

```bash
python3 pipeline/scripts/fetch-prices.py --only deepseek,qwen --concurrency 2 --dry-run
python3 pipeline/scripts/fetch-prices.py --only openai --run-id prices_review_001
python3 pipeline/scripts/fetch-prices.py --retry-failed data/price-runs/2026-10-02/prices_review_001.json
python3 pipeline/scripts/fetch-prices.py --only openai --offline-snapshot data/price-runs/2026-10-02/prices_review_001.json --extractor-version openai-1 --dry-run
python3 pipeline/scripts/fetch-prices.py --only openai --offline-snapshot data/price-runs/2026-10-02/prices_review_001.json --extractor-version openai-1
python3 pipeline/scripts/fetch-prices.py --recover prices_review_001
python3 pipeline/scripts/fetch-prices.py --discard-run prices_review_001
```

`--recover` 保留原日期、来源范围、抓取时间和已有快照，不要求再传 `--only`。失败抓取可以再尝试；已抓到的快照只重解析。指定版本必须是当前代码实际可提供的版本，不虚构旧适配器的执行能力。语义升级后的快照复核应创建新的离线执行，而不是改写原中断任务的处理版本。

离线执行只补充不可变证据/事实版本，保留原观察时间；不覆盖当前事实选择、来源健康状态、台账历史或价格事件。相同输入/处理版本幂等；新 HTTP 观察有新的尝试 ID 和实际观察时间。后续正常采集再更新 current 和站点投影。`--dry-run` 解析和打印差异，不写快照、归档、输入指针或站点文件。全来源失败退出码 2；部分失败退出码 0 且 outcome=partial。未运行来源 outcome=not_run，不刷新 lastSuccessAt。

## 通用信源、榜单与其他写入方

```bash
python3 pipeline/scripts/fetch_sources.py --platform OpenAI --max-sources 2 --run-id source_review_001
python3 pipeline/scripts/fetch_sources.py --recover source_review_001 --platform OpenAI --max-sources 2
python3 pipeline/scripts/fetch_sources.py --retry-failed data/pipeline-runs/2026-10-02/source_review_001.json
python3 pipeline/scripts/fetch_sources.py --offline-snapshot data/pipeline-runs/2026-10-02/source_review_001.json
python3 pipeline/scripts/fetch-leaderboards.py --only session-cost --run-id boards_review_001
python3 pipeline/scripts/fetch-leaderboards.py --recover boards_review_001 --only session-cost
python3 pipeline/scripts/fetch-leaderboards.py --dry-run --only session-cost
```

通用信源/榜单离线执行在该 run 的 offline-preview/ 下生成复核产物，不替换 canonical diff、榜单或原始快照槽位，也不自动应用到站点。新的真实采集才更新这些产物。

通用同步写入方的恢复需重传原业务参数，协议检查 argv 一致。通用信源重试限制到失败 URL；榜单重试限制到失败的逻辑数据集，排名类会连同配对的比较窗口取回。榜单 dry-run 不写原始响应、注册表或图标；没有 API key 时 outcome=not_run，保留数据。通用信源及摘要/导入写入方的 dry-run 跳过执行并打印说明，不生成差异。

信源和榜单沿用串行传输与原 curl 超时（30/40 秒），增加一次有退避的传输重试；价格初始并发 2，允许 1–3，同域串行、开始间隔至少 1 秒，整体请求超时 120 秒、一次退避重试。解析/Schema 失败不重新联网。抓取与解析可以并行，归档、current 与投影只有一个写入方，`data/.pipeline.lock` 还防止不同入口竞争。

受协议管理的 CLI：价格、通用信源、榜单、diff 同步、daily/weekly 摘要、周报导入与结构化提取、默认 source/price backfill、logo refresh。导入后的 Markdown 与结构化周报在同一执行中提交。显式 `--archive-root` 的旧隔离调试入口与 `--check` 保留既有语义，不创建正式运行；不要用调试入口修改正式路径。

## 提交、撤销与现场留存

开始写入前固定 `data/inputs-current.json` 及不可变输入 manifest，原有事实/证据/修订引用原文件，可变输入才复制到内容寻址对象。公开导出读取固定输入 view；原始事实 ID、内容身份、Decimal 与公开 datasetVersion 算法不变。

运行期间 `data/pipeline-pending.json` 阻止另一写入方、候选站点构建和 CI 数据提交。完整产物校验后，原子替换输入指针是提交点；随后写唯一运行记录并删除 pending。指针前中断：恢复先还原可变输入，再复用快照重跑。指针后中断：只补齐提交记录，拒绝撤销。不能通过删除 pending 跳过恢复。

撤销会还原可变输入与本次覆盖的原始快照；新产生、尚未提交的不可变归档叶子移入该 run 的 `discarded/` 隔离区，保留字节，避免孤立修订影响校验。原有已提交历史不移动。完成执行的输入检查点只保留当前与上一份，淘汰仅限此协议新建的 input-manifests/input-objects 缓存；不清理事实/证据历史、原始来源快照、公开 cursor 版本或部署 release。旧输入 hash 仍在运行记录和对应 Git 提交中，可在历史 checkout 复核。

CI 有 pending 时生成并上传 `pipeline-recovery-<run>-<attempt>` artifact，保留 14 日。恢复时使用该 workflow 的精确代码 SHA、新的隔离 checkout，解压其中相对路径到仓库根，按 journal.family 选择原 CLI，再使用 `--recover <runId>`（或 `--discard-run`）和原 argv。先完成恢复及全量校验，再按现有发布流程提交；不要直接覆盖线上 release。artifact 只含标准数据、输入检查点、暂存记录与来源内容，脚本不读取环境凭据。

这些是进程中断与单写入方协议，未宣称分布式事务、主机断电持久性或实际 GitHub 恢复演练已通过。远端存储、历史清理与实际通知接入按后续任务处理。
