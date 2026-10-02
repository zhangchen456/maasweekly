# 本地存储迁移与恢复操作

当前阶段仅提供本地 filesystem adapter 和演练，不启用远端、不从 Git 删除原始文件、不改写历史。目标对象按 exact raw SHA-256 寻址；semanticContentHash、psnap/evidence/fact ID 原样保留。无现存原始字节的历史内容标 legacy_raw_missing，不创建假对象、不用今天网页替代旧观察。

固定提交的清单记录 sourceCommit、datasetVersion、可用的 inputVersion、原逻辑路径、blobId、bytes、contentType、元数据 hash 及证据引用。迁移清单是存储视图，migrationVersion 不替代公开 datasetVersion。源数据必须与固定 Git commit 一致，pending 管线或活跃 writer 阻止生成清单；复制时再次核对原始字节，源变化将产生失败报告。

以下命令在仓库根使用已安装声明依赖的 Python 3.12 环境和 Node 22 执行。目录变量仅指本轮创建的临时环境：

```bash
MIGRATION_COMMIT="$(git rev-parse HEAD)"
STORAGE_WORK="$(mktemp -d /tmp/maas-storage.XXXXXX)"
python3 pipeline/scripts/storage-migration.py manifest --commit "$MIGRATION_COMMIT" --output "$STORAGE_WORK/manifest.json"
python3 pipeline/scripts/storage-migration.py copy --manifest "$STORAGE_WORK/manifest.json" --blob-root "$STORAGE_WORK/blobs" --report "$STORAGE_WORK/copy.json"
python3 pipeline/scripts/storage-migration.py verify --manifest "$STORAGE_WORK/manifest.json" --blob-root "$STORAGE_WORK/blobs" --report "$STORAGE_WORK/verify.json"
# 只续传 verify 报告中的失败对象；随后仍需完整 verify。
python3 pipeline/scripts/storage-migration.py copy --manifest "$STORAGE_WORK/manifest.json" --blob-root "$STORAGE_WORK/blobs" --failed-report "$STORAGE_WORK/verify.json" --report "$STORAGE_WORK/retry.json"
```

copy/verify 失败、受控部分复制或未完成恢复退出 2。正常幂等重跑退出 0；部分复制不表示清单已经可启用。upload 使用原子 create-if-absent，已有对象必须通过完整 hash/bytes 校验，损坏对象不会被覆盖。修复损坏对象应在隔离副本中确认来源后进行；工具没有生产删除命令。

完整空目录演练推荐直接运行：

```bash
python3 scripts/architecture-storage-drill.py --commit "$MIGRATION_COMMIT" --workspace "$STORAGE_WORK/drill" --evidence "$STORAGE_WORK/evidence"
```

该脚本从固定 Git archive 恢复代码和元数据，排除所有 data/snapshots 原始文件，随后仅从 blob store 恢复。保留事实、修订、证据和公开历史版本在元数据包中；兼容工具链接独立处理，不从外部工具目录恢复依赖。执行归档校验、公开导出、七集合逐字节对账及完整 Astro 构建。Node 依赖使用本机锁定缓存，不代表已测冷网络 npm 下载。

单独恢复已有代码/元数据环境：

```bash
python3 pipeline/scripts/storage-migration.py restore --manifest "$STORAGE_WORK/manifest.json" --blob-root "$STORAGE_WORK/blobs" --destination "$STORAGE_WORK/recovered-code" --cache "$STORAGE_WORK/build-cache" --cache-mib 64 --report "$STORAGE_WORK/restore.json"
```

recovered-code 应事先恢复固定版本代码与元数据，不能把仅恢复 raw 的空目录当成完整应用。restore 与管线共用 data/.pipeline.lock；中断保留 storage-restore-pending.json，构建、其他管线 writer 与工作流数据提交被阻止。用相同 manifest 重跑即可续接；已有目标文件与 hash 不同则拒绝覆盖。全部 raw 复核后才移除 pending 标记。验证候选之后按现有 immutable release/蓝绿协议另行发布。

构建缓存为每个恢复/构建实例独占目录，64 MiB 为 payload 上限，不是整个存储库或 filesystem 分配字节上限。启动与显式审计扫描一次，常规读写复用 LRU 索引；hash 每次读取均校验。缓存可删除后重新取回，完整 blob store 的保留期不能由缓存淘汰决定。SnapshotReader 可验证旧路径读取，旧文件缺失时按清单取 blob；损坏旧文件不会静默被 fallback 掩盖。

候选故障与 last-known-good 运行包独立。以下探针在本地启动已封装 API，模拟缺对象/损坏/不可达候选，确认服务及固定版本 cursor 继续可用：

```bash
python3 scripts/architecture-storage-fault-smoke.py /path/to/sealed-release "$STORAGE_WORK/evidence/migration-manifest.json" "$STORAGE_WORK/drill/blobs" "$STORAGE_WORK/lkg.json"
```

drill 的 manifest 实际位于 --evidence 指定目录，上例应按实际 evidence 路径填写。该探针不切换线上 release。

清理只生成 dry-run，明确传入所有历史迁移/回滚依赖清单：

```bash
python3 pipeline/scripts/storage-migration.py cleanup-plan --manifest "$STORAGE_WORK/manifest.json" --blob-root "$STORAGE_WORK/blobs" --grace-days 14 --report "$STORAGE_WORK/cleanup.json"
```

事实/证据历史、公开 cursor 当前+7日+上一版、可回退部署包是三种独立保留。14 日只用于这个原始对象清理候选的宽限期，不缩短任何证据历史。manifest 列表不完整不能据报告删除对象；本工具没有删除阶段。正式切换、停止 Git 冗余与清理均 DEFERRED。首次真实清理前必须重新证明恢复和全引用覆盖。

远端后续工作需要实际区域/桶、认证与收费输入，再补充 BlobStore 实现、重试/权限/配额、writer 引用切换和候选取回流程。API/RSS/Skill 继续从完整本地 release 服务，不把远端存储加入单次查询路径。既有历史 Git pack 不会因未来 git rm --cached 自动缩小。
