# 独立数据更新与代码发布

生产读者使用 `/srv/maasweekly/shared/public-data/v1/publication.json` 固定公开数据和页面输入。结构化数据在 PostgreSQL `maas_data`，原始材料在 `/srv/maasweekly/shared/data-store/blobs`；均独立于代码目录。没有对象存储。生产是否已启用及实际版本以 [运行状态](data-code-runtime-2026-10-29.md) 和服务器 `shared/runtime.json` 为准。

## 日常操作

- 每日工作流北京时间 05:00 执行采集、摘要、投影、入库、校验和发布，不提交 Git、不构建 Astro、不重启网站。手动勾选 `skip_fetch` 直接从数据库已提交输入重新生成数据，不恢复缓存、不重复导入。
- 周报工作流北京时间周一 09:00 执行；`aggregate` 仅准备材料并入库，`import` 导入 `data/weekly` 稿件后发布，`full` 完整采集后导入并发布。稿件来源 commit 和正文 SHA 记录在导入来源中。
- 修改功能、规则、模型注册表后推送 main，由 `deploy.yml` 调用 `release-deploy.yml` 构建仅代码的 SSR 包。上传后先进行 Linux 数据/SSR 验证，再蓝绿切换。数据保持当前已发布版本。

CI 仅调用 maasdeploy 受限 SSH 固定动作 `data-update` / `runtime-activate <rid>`；没有任意 root shell。数据库使用 Unix peer，不传数据库密码。LLM 凭据经 stdin 进入任务，只交给需要的子程序，不进入浏览器采集进程或命令参数。

## 查看与排障

root 在服务器执行 `python3 /usr/local/lib/maasweekly/runtime-control.py status` 查看实际代码/槽位。数据任务由 `maas-data-update.service` 托管；日志在 `shared/data-store/reports/writer-<time>-<mode>.log` 及 `data-unit.*.log`，保持私有，避免复制原始日志到公开评论。

结构化输入先入库，`writer_heads` 指向最新完整采集结果；公开指针仅在候选文件和 18 项 SSR 验证通过后切换。失败继续服务旧版本；重试使用最新完整输入。中断缓存放入 writer/recovery，保留现场，不自动删除证据。执行日志单独写 `writer_run_logs`，不改变业务输入版本。

代码切换失败自动恢复 Nginx 配置；中断事务在下一次控制命令时按 `runtime-switch-pending.json` 恢复。显式代码回退：root 执行 `python3 /usr/local/lib/maasweekly/runtime-control.py rollback`，仍读取当前共享数据。旧静态站只允许在数据版本未改变时回退。旧 `activate`/`rollback` 静态发布入口在 runtime-mode 下被拒绝。

数据回退需选择数据库中仍完整的输入/页面候选，先完成相同验证，再用显式 `allow_rollback` 激活器；不要手改 publication.json 或把旧代码包里的 manifest 覆盖到共享目录。公开 ID 和历史修订不随代码回退删除。

## 备份与容量

每次真正发布前生成本机事务一致的 PostgreSQL dump。blobs 为内容寻址的不可变文件，必须和数据库一起备份；初次切换已完成服务器恢复演练和本机仓库外副本。持续异机备份尚无调度。本机备份、候选、缓存、物理历史文件尚不自动清理；按磁盘余量定期核验，不能把它们当作无限容量。

## 本地与构建

标准生产构建入口为 `bash scripts/build-runtime-release.sh --output <仓库外新目录>`，要求干净固定提交、Node 22/Python 3.12，包不含运行数据。单元测试使用固定小样本，真实数据验证在服务器独立完成。

本地完整网页预览需要独立的测试 PG/公开数据目录和 `MAAS_SITE_ENTRY`，可用 `scripts/verify-runtime-site.mjs --package-root <包> --data-root <外部候选>` 做隔离验收。旧 `npm run build`/`build-release.sh` 保留历史静态链路，需要完整本地输入；不再是生产发布入口。不要为构建向 Git 重新加入业务数据。

## 低内存服务器与中断入库恢复

输入清单按流式 canonical JSON 计算原有校验值；文档导入/验证同时受 128 条和 2 MiB 原始数据批量限制，单个更大的文档独立处理。容器最多使用 1536 MiB 内存及 1024 MiB 交换空间；主机需要先配置交换空间，交换不是容量扩容的替代品。

代码切换在新路由冒烟通过、恢复信息落盘后，等待 30 秒排空旧请求再停止旧 API 槽位。旧包仍保留，回滚会重新启动对应槽位；停止失败只发出警告，不撤销已经成功的发布。

若采集和归档校验已经完成、任务在入库阶段中断，先读取 writer/data/inputs-current.json 并保留故障日志，再通过受限 data-update 动作提交 `{"mode":"resume","inputVersion":"in_<完整64位哈希>"}`。此模式不重新抓取、不用数据库旧版本重置缓存，仍执行归档验证、固定版本入库、候选验证、备份和原子发布。输入版本不匹配、有未完成流水线标记或重算版本不一致时拒绝恢复，不修改公开指针。不要对仍在运行或未完成采集的任务使用此模式。

root 管理的 `/usr/local/lib/maasweekly/runtime-control.py` 与 `data-update.py` 分别来自 `ops/runtime-control.py` 与 `ops/data-writer/launch.py`，需要显式备份和安装；仅代码包发布不会自动替换 root 控制器。
