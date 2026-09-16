# Task 03 结果报告：统一公开数据投影与 REST API v1

日期：2026-09-16。状态：本地实现完成；**待 Task 04 接入 MCP/Skill、待 Task 06 生产部署**。未 commit/push（等用户指示）。

## 1. 交付文件

```text
pipeline/config/public_providers.json        # provider/sourceId 显式映射（D1）
schemas/public-v1/                            # 6 份公开 JSON schema
  common / record / change / price / evidence / weekly / status / manifest（7 文件）
pipeline/public_export/                       # 唯一 exporter 包
  canonical.py   loaders.py   projector.py   validator.py
pipeline/scripts/export-public-data.py        # CLI：默认 / --check / --dry-run / --output-dir / --input-root
data/public/v1/                               # 首个真实 release（22MB）
  manifest.json + releases/ds_fa0adf…/
services/agent-api/                           # Node 22 + TS，零运行时依赖
  src/dataset.ts  src/query.ts  src/http.ts  src/server.ts
  src/tests/（http / versioning / openapi / real / fixture）
site/public/openapi-v1.json
docs/contracts/public-api-v1.md
tests/test_public_export.py
```

顺带修复（越界修改，理由如下）：
- 删除 `data/records/obs_d908429…`（test-esc 转义测试残留：site 测试把
  fixture 写进真实归档、cleanup 中断后被 git add data/ 提交。sourceId
  不在 registry，按任务书是门禁错误）+ 同步索引（181→180）。
- `site/tests/records.test.mjs`：加 `[0]` 残留检测门禁（开始前断言
  归档无 test-esc/test-wd，残留即中止）+ `maxBuffer: 64MB`（站点
  9000+ 页构建日志超 execSync 同步管道默认 1MB 上限，ENOBUFS）。

## 2. 命令与退出码（全部实际执行）

| 命令 | 退出码 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_public_export.py' -v` | 0（12 项） |
| `python3 -m unittest discover -s tests -p 'test_record_archive.py' -v` | 0（18 项） |
| `python3 -m unittest discover -s tests -p 'test_price_archive.py' -v` | 0（56 项） |
| `python3 pipeline/scripts/validate-archive.py` | 0（180 条记录） |
| `python3 pipeline/scripts/validate-price-archive.py --check` | 0（3001 事件 / 6285 证据） |
| `python3 pipeline/scripts/export-public-data.py --check` | 0 |
| `cd services/agent-api && npm ci` | 0 |
| `cd services/agent-api && npm test` | 0（20 项：http 14 + versioning 5 + openapi 1） |
| `cd services/agent-api && npm run build` | 0 |
| `cd services/agent-api && npm run test:real` | 0（T18 真实 HTTP 3 项） |
| `cd site && npm ci && npm run build` | 0（9498 页 / 11.4s） |

## 3. 真实 release（T18）

- datasetVersion：`ds_fa0adf0f7593b4532421ae49e0bb8a2167c8d3167d1873519cc3398c68058b2b`
- dataThrough：2026-09-16；release 大小 22MB
- 实体：changes 3181（obs 180 + price 3001）/ items 3181 / prices 1335
  / evidence 6285 / weekly 23 / status（16 provider、68 sourceStreams、8 priceStreams）
- changes 覆盖：2026-09-04 → 2026-09-16
- 同输入重建：幂等零写入（T01 实测两次导出字节相同）
- 性能（真实数据，本地）：changes(limit=100) 2ms、prices(limit=100) 1ms、
  export 全量约 8s、T18 总时长 230ms

## 4. 响应样例

```jsonc
// GET /api/v1/changes?limit=1
{
  "schemaVersion": "1.0",
  "datasetVersion": "ds_fa0adf0f7593…",
  "dataThrough": "2026-09-16",
  "query": { "limit": 1, "from": "2026-09-10", "to": "2026-09-17" },
  "coverage": { "changes": { "from": "2026-09-04", "to": "2026-09-16", "count": 3181 }, … },
  "items": [ { "id": "obs_086c210d…", "recordType": "source_observation",
               "providerId": "openai", "observationDate": "2026-09-16",
               "timePrecision": "date", "quality": { "state": "fresh", … },
               "evidenceIds": [], "links": { "permalink": "/item/obs_…/" } } ],
  "page": { "limit": 1, "nextCursor": "eyJkcyI6…" }
}
```

## 5. 验收对照（T01–T18）

| # | 场景 | 结果 | 测试 |
| --- | --- | --- | --- |
| T01 | 同输入连续导出稳定 | ✅ 字节相同、无多余 release | test_public_export TestT01Stable |
| T02 | 修订/撤回 → 新版本；withdrawn 语义 | ✅ | TestT02RevisionChanges |
| T03 | 坏 JSON/未知 source/悬空证据 → 零写入 | ✅ | TestT03BadInputs |
| T04 | --check/--dry-run/隔离输出零污染 | ✅ | TestT04Modes |
| T05 | manifest 篡改 → 门禁失败 | ✅ | TestT05ManifestTamper |
| T06 | changes 默认窗口 + 组合筛选 | ✅ dataThrough 锚定 | http.test T06 |
| T07 | prices 条件完整、不丢、不选最低 | ✅ | http.test T07 |
| T08 | withdrawn 隐藏/stale 披露 | ✅（真实归档当前全 fresh：8/8 价格源 ok） | http.test T08 + partial 投影 |
| T09 | item/evidence/weekly 闭环 + 404 | ✅ | http.test T09 |
| T10 | 非法参数 400 Problem + recovery | ✅ 11 类 | http.test T10 |
| T11 | 同版本翻页无重复遗漏 | ✅ | http.test T11 |
| T12 | 翻页期间换版本；409 | ✅ | versioning.test T12 |
| T13 | ETag/304 | ✅ | http.test T13 |
| T14 | HEAD/OPTIONS/CORS/413/429 | ✅ | http.test T14 |
| T15 | 热重载成功/失败续服 | ✅ | versioning.test T15 |
| T16 | 恶意 excerpt/路径编码/超长 cursor | ✅ | http.test T16 + TestNoLeak |
| T17 | OpenAPI 与路由对照 | ✅ | openapi.test |
| T18 | 真实归档全量导出 + 服务 | ✅ | test:real 3 项 |

失败注入与分页测试全部临时目录；真实归档只读（`--dry-run`/`test:real` 零写入断言）。

## 6. 已知限制

1. **T08 stale 场景未在真实数据出现**：当前 8/8 价格源 ok、Task 01
   记录全 active——真实 release 的 quality 全 fresh。stale/503 行为由
   fixture 测试覆盖。
2. **Task 01 sourceStreams 时间精度为日**：daily_changes 滚动窗口约
   60 天，窗口外 unknown（17 源从未出现）——合同已声明，不伪装精确时间。
3. **datasetVersion 每日必变**：current.json 的 latest_attempt_at 进
   status 实体 → release 日增；保留策略 7 天 + 上一版已实现。
4. **observedAtRange 覆盖度**：6285 证据中 3194 被 pfv 引用，其余
   relatedFactIds 为空数组（合法历史证据，无列表端点）。
5. changes 的 `q` 只搜 title+summary；prices 的 `q` 只搜 modelKey
   （合同已写明）。
6. 限流是进程内令牌桶（匿名共享、可配置）；nginx 层限流留 Task 06。

## 7. 本地体验

```bash
python3 pipeline/scripts/export-public-data.py           # 已发布 ds_fa0adf…
cd services/agent-api && npm run build && npm start      # 127.0.0.1:8787
curl http://127.0.0.1:8787/api/v1/status
curl 'http://127.0.0.1:8787/api/v1/changes?provider=openai&limit=5'
curl 'http://127.0.0.1:8787/api/v1/prices?provider=alibaba&model=qwen-max&component=input'
```

OpenAPI：`site/public/openapi-v1.json`（构建后随站点发布）。
合同：`docs/contracts/public-api-v1.md`。

## 8. 设计要点存档

- **provider 映射**（D1）：`public_providers.json` 显式表。关键：pricing
  命名空间与平台命名空间错位（qwen:pricing→alibaba-pricing、
  doubao:pricing→volcengine-pricing、glm:pricing→zhipu-pricing），
  名称匹配会静默错配，必须显式映射 + 门禁双向校验。
- **datasetVersion**（D2）：六集合规范内容摘要 → 拼接 dataThrough 再
  SHA-256；manifest.files[].sha256 是文件字节哈希（两套哈希分离）。
- **零运行时依赖服务**（D3）：Node 22 原生 http；query.ts 无 HTTP
  依赖（Task 04 MCP 直接 import）。
- **cursor 携带查询参数**（D4）：翻页时服务端从 cursor 恢复查询
  （客户端只传 cursor），qh 与 qp 自洽校验防篡改。
- 时间窗口统一 `[from, to)` 语义（默认窗口 to = D+1 使含当日共 7 天）。


## 9. 复验修复（2026-09-16 验收驳回后）

验收发现两个破坏公开 API 契约的 P1，已修复并全量回归：

### P1-1 历史 release 绕过完整性校验

- **原缺陷**：cursor 读旧版本时直接解析六个 JSON，不校验 hash，元数据（generatedAt/dataThrough/coverage）丢失。实测篡改旧版本文件后服务返回 TAMPERED 内容。
- **修复**：exporter 为每个 release 写 per-release `manifest.json`（含 generatedAt/dataThrough/coverage/files hash）；`Dataset.loadDirect` 读历史版本时执行与当前版本完全相同的路径/bytes/SHA-256/结构校验。篡改 → 拒绝加载（cursor → 409 dataset_version_expired——不可信历史 release 与已清理同等对待）。幂等逻辑同步升级（缺 per-release manifest 的旧形态目录会被重写补齐）。
- 测试：p1-fixes.test.ts（篡改 prices.json → getOrLoad 返回 null；恢复后可加载；元数据取自 release 自身）。

### P1-2 cursor 可伪造绕过查询限制

- **原缺陷**：qh 是无密钥哈希，调用方可改 qp（limit/窗口/枚举）后自行重算 qh 绕过全部参数校验。实测伪造 limit=10000 一次返回 3181 条。
- **修复（双层）**：
  1. cursor 增加 HMAC-SHA256 MAC 签名（服务端密钥，timingSafeEqual 比对；默认进程内随机，多实例部署设 CURSOR_SECRET 共享）。无密钥伪造 → 400 invalid_cursor。
  2. 防御纵深：cursor 恢复 qp 时重新送全量规范化校验（limit/窗口/枚举/类型与第一页同规），且规范化结果与 qp 比对一致——即使密钥泄露（P1-2b 场景）非法参数仍被拦截。
- 复测：验收报告原攻击场景（改 limit=10000 + 重算 qh）→ 400 invalid_cursor；签名有效但参数非法 → 400 invalid_limit；合法翻页不受影响。
- 测试：p1-fixes.test.ts 5 项。

### P2-3 提交边界

- .gitignore 补 `services/agent-api/node_modules/`、`dist/`（`__pycache__` 已有）；未跟踪条目 271 → 11（全为源码/数据/文档）。

### 回归（修复后全绿）

Python 86 项（12+18+56）、TS 26 项（http 14 + versioning 6 + openapi 1 + p1-fixes 5）、test:real 3 项、三门禁、export --check、site 9498 页构建。

此前 §2 命令表中 `npm test` 现为 26 项。