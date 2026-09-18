# Task 06 结果报告：生产发布、运行保障与 P0 首发验收

日期：2026-09-17（M1–M4）/ 2026-09-18（M5–M7）。状态：**M1–M5 完成；M6 完成（页面 §11 重构 + M7 合同修正）；M7 生产候选就绪（分支 task-06-m7-candidate，已提交未 merge）——等待授权点 A**。四入口仍为 pending（public-access.ts 未翻转）。本任务未修改生产服务器、nginx、systemd 或线上流量；DEPLOY_MODE=legacy。

## M7 生产候选（2026-09-18，分支 task-06-m7-candidate）

### /agent/ 与真实接口合同修正（全部对照 agent-api 实现核对）

| 项 | 原页面 | 修正后（真实合同） |
|---|---|---|
| Skill 更新/卸载 | `--update`/`--uninstall` 参数（install.sh 不存在） | 更新=同一 `--dir` 重跑安装器；删除虚构参数 |
| --dir 语义 | `<你的技能目录>` 尖括号占位符 | `--dir` 是最终 Skill 目录（示例 `~/.claude/skills/maas-daily`；install.sh 真实行为） |
| MCP limit | 「最大返回 200 条」 | 默认 10、最大 30（`MCP_LIMITS`，mcp-tools.ts:44） |
| REST 单页 | 未注明 | 默认 20、最大 100（`REST_LIMITS`） |
| REST 路径 | `/api/v1/item`、`/api/v1/evidence` | `/api/v1/items/{id}`、`/api/v1/evidence/{id}`（ROUTES，http.ts:34/39） |
| 查询参数 | `platform=openai` | `provider=openai`（KNOWN_PARAMS，query.ts:82） |
| 验证样例 | 手写「查 gpt-6-astra 的输入价格」 | 「查一个模型当前记录的输入价格」（不依赖具体模型名，模型会下线而合同不变） |

测试同步：access-pages.test.mjs 新增 5 项断言（provider 参数、--dir 最终目录形态、无虚构参数、无写死模型名、/items/{id} 路径），全绿。

### verify-release.sh 安全修复（任意命令面关闭）

- **原缺陷**：`current_ds_from_server` 经受限 shell 执行任意 `python3 -c`（读服务器 manifest 文件）——受限 shell 的意义被架空。
- **修复**：`maasweekly-activate status` 扩展只读 metadata 输出（datasetVersion/dataThrough/gitCommit，从 current release manifest 读）；客户端 `server_meta` 只解析固定 `status` 动作的输出。新增测试 `test_status_metadata_readonly`（激活套件 17→18 项）。
- **online verify 覆盖四入口**（此前只查 REST status/changes）：
  - REST：status + changes 同 datasetVersion
  - MCP：initialize（serverInfo）+ tools/list（五工具齐备）+ maas_get_changes 真实调用（响应含当前 datasetVersion）
  - RSS：两 feed 的 content-type（application/rss+xml）+ ETag + If-None-Match→304
  - Skill：manifest.json 结构校验 + install.sh 可达

### ops 运维文件补齐（全部候选，授权点 A 前不执行）

| 文件 | 内容 |
|---|---|
| `ops/maas-agent@.service` | 蓝绿槽位 systemd 模板（blue 8788/green 8789）；非 root 专用用户；NoNewPrivileges/ProtectSystem=strict/私有 tmp/CapabilityBoundingSet 空等硬化；env 由激活器写 slots/<slot>.env |
| `ops/nginx-agent.conf` | candidate 配置：REST `limit_req` 独立桶 + proxy 透传 ETag/错误不缓存；MCP 独立桶 + no-store + 256k body；feed rss+xml + max-age=1800 + ETag/304；`/_astro/` 一年 immutable。upstream/root 不硬编码——由激活器 include 绑定同一 release |
| `ops/maas-agent.env.example` | 仅变量名与安全默认值（HOST=127.0.0.1、限流、MCP body/Origin、CURSOR_SECRET 占位）；真实文件服务器现场生成（root:maasagent 0740） |
| `ops/install-production.sh` | 一次性幂等安装（M8 授权后执行）：前置检查（node22/nginx/磁盘）→ 双用户（maasagent/maasdeploy）→ 目录树 → 受限 shell/激活器/校验器就位 → sudoers 单行 NOPASSWD → systemd 模板 → agent.env 现场生成 secret → nginx include 位。`--dry-run` 全程可审查（已在本地实测通过） |
| `ops/README.md` | 发布协议图、status/回滚用法、故障排查表、host key 轮换流程、授权红线 |

### 顺带修复：macOS bash 3.2 全角括号解析 bug

`"...$VAR）"`（$VAR 后紧跟全角字符）在 macOS bash 3.2 + UTF-8 locale 下触发假 `unbound variable`（闭括号 UTF-8 尾字节混入变量名；`${VAR}` 花括号形式免疫；Linux bash 5 不受影响）。全 ops/scripts 排查修复 8 处。

## 0. 第二轮复验修复（2026-09-17，四项阻断）

### P0 nginx -t 实际没检查候选配置 — ✅ 关闭

- **原缺陷**：nginx_test 接收候选 include 路径做参数校验，但生产分支 `nginx -t` 校验的是磁盘上当前生效的旧配置——候选 include 从未参与校验。
- **修复**：候选 include 先就位到生效路径（`write_candidate_include "$EFFECTIVE_INC"`），再无参调用 nginx_test——无论测试 hook 还是生产 `nginx -t`，校验的都是即将生效的配置。
- **验收**：17 项激活测试含 nginx 失败注入（FAIL_nginx_test / FAIL_nginx_reload）均验证旧可用 + 同 RID 重试成功。

### P1 rollback 失败会搬走历史 release — ✅ 关闭

- **原缺陷**：rollback 切换失败也走 `recover_failed_activation`，把目标 release 从 releases 搬回 incoming——破坏 previous 指向与历史版本链。
- **修复**：`recover_failed_activation` 增加 `keep_release` 参数；rollback 失败时传 `keep_release`，只恢复服务/指针/include 状态，release 保留原位。
- **验收**：test_rollback_incompatible_ds_rejected（rc=4 目标保留）、test_rollback_with_reason 回归通过。

### P1 并发测试不能证明 flock 生效 — ✅ 关闭（真实 Ubuntu 证据）

- **原缺陷**：TestT04Concurrent 在 macOS skip，CI 未覆盖——flock 串行从未被真实证明。
- **修复与证据**：在 Ubuntu 服务器（47.237.135.97，/usr/bin/flock）真实验证——临时 release root 注入，新旧两个 release（旧 ts 与新 ts）并发 activate，断言 final current = 新 release，旧提交不能倒灌：
  ```
  final current: rl_aaaaaaaaaa_bbbbbbbbbbbb
  expected    : rl_aaaaaaaaaa_bbbbbbbbbbbb
  OK flock 并发串行验证通过（Ubuntu /usr/bin/flock）
  ```
- **过程中修出真实 bug**：`exec 9>release.lock` 的锁 fd 被 activate-hook 起的后台服务继承——激活完成后锁仍被 90 秒的桩服务持有，下一次激活等锁直到服务退出（Ubuntu 实测超时复现）。修复：hook/systemctl 调用统一 `9>&-` 关闭锁 fd 继承。生产 systemd 调用同样受益（避免长驻服务隐性持锁）。

### 首发边界：旧 include 不存在的快照恢复 — ✅ 关闭

- **原缺陷**：第一次激活时旧 include 可能不存在；候选 include 已写入生效路径后若 reload 失败，恢复逻辑只处理"旧 include 存在"分支——残留的候选 include 指向已退回 incoming 的失效 root。
- **修复**：三态快照——`_inc_snapshot` 在事务前记录 `.rollback.inc`（旧内容存在）或 `.no-inc` 标记（原本不存在）；`_inc_restore` 精确恢复到事务前状态（含"删除候选残留恢复到不存在"）。
- **验收**：17 项激活测试首激活路径（旧 include 不存在）+ 失败注入全绿。

## 1. 第一轮复验修复（2026-09-17，五项阻断）

### P0-a builder 生产包含 dist — ✅ 关闭

- **原缺陷**：步骤 4 先 `rm -rf $PKG/dist` 再 `npm ci --omit=dev`，`dist/server.js` 从未进入 release。
- **修复**：改为完整依赖编译（npm ci → npm run build → 断言 dist/server.js 存在）→ 删 node_modules → `npm ci --omit=dev` → 断言两个生产依赖存在。临时目录 `trap EXIT` 清理。
- **验收证据**：
  - 真实仓库完整执行 `scripts/build-release.sh` → 退出码 0，release `rl_0465a08e77_fa0adf0f7593`（13247 文件 / 151515525 字节）
  - `dist/server.js`、`package.json`、`package-lock.json`、`node_modules/@modelcontextprotocol/sdk` 全部存在
  - 顺手修出两个真实 bug：release 内 data 需保持 `public/v1` 层级（`rsync` 目标路径）；npm `.bin` 符号链接是合法运行时结构（builder 与 verify 两处均加 realpath 逃逸判定）

### P0-b 蓝绿切换真正切 nginx — ✅ 关闭

- **原缺陷**：只覆盖 agent-upstream.inc、无 nginx -t/reload/静态 root 同步；停旧槽后 nginx 仍指旧端口。
- **修复**：`switch_service_tx` 完整事务——候选槽位起服务+冒烟 → 候选 include（**site root 与 upstream 绑定同一 release**）→ nginx -t → 原子替换 → reload → 切换后入口冒烟 → 旧 worker 排空后停旧槽。include 备份保留到事务**全部成功**（reload 成功即删备份会导致 entry_smoke 失败无法恢复——已修）。
- **验收证据**：MAAS_NGINX_TEST hook 模拟调用顺序（test 先于 reload）、include 内容断言（root/upstream 同 rid）、五种失败注入全绿。

### P1-a 槽位映射键 — ✅ 关闭

- **原缺陷**：slots.json 用绝对路径键，`slot_of_release` 用 rid 查——永远查不回。
- **修复**：双向映射 `rid_to_slot` / `slot_to_rid`，原子写入（tempfile + os.replace），写新映射时清理旧槽指向。
- **验收证据**：`test_blue_green_blue`——A→blue（8788）→ B→green（8789）→ C→blue（8788）；每次断言候选端口、当前槽、旧槽停止（hook.log 记 stop blue/green）、映射正确（C 取代 A，A 旧条目清理）。

### P1-b 候选失败恢复不可达 — ✅ 关闭

- **原缺陷**：`switch_service` 内部 `die` 直接 exit，外层 `if ! switch_service` 的恢复分支不可达；失败 release 滞留 releases、同 RID 无法重试。
- **修复**：事务返回码（5 候选/7 nginx），`recover_failed_activation` 统一恢复：停候选槽、恢复旧 include/current/slots、清 slot env、**release 退回 incoming**（同 RID 可重试）。
- **验收证据**：五种失败注入（candidate start 失败 / status 冒烟失败 / nginx -t 失败 / nginx reload 失败 / 切换后入口冒烟失败）全部：旧 current + 旧 include 不变；同 RID 重新上传并成功激活（rc=0）。

### P1-c 统一全量回归入口 — ✅ 关闭

- **新增 `scripts/run-all-tests.sh`**：供开发、builder、CI 共用——4 门禁（export --check / validate-archive / validate-price-archive / skill --check）+ Python 六套（record/price/public_export/skill_package/release_build/release_activation）+ site build + 六测试（access-pages/rss/pricing/platform-logos/leaderboards/records）+ agent-api 四套（build/REST/MCP/MCP real）。
- **真实退出码逐项判断**（不 grep 文本、不 tail -1 吞日志；失败输出测试名+关键日志）。
- **--skip-tests 在 manifest 写 `testsSkipped: true`**，激活器（release_manifest_verify）拒绝激活——开发调试产物不能进生产。
- **records.test.mjs**：内部写真实归档 fixture + 开头残留检测（Task 04 加固）；Astro build 绑定仓库路径无法临时目录化——已记录为已知限制（构建中断时残留检测兜底）。

## 2. 复验收逐条结果（复验完成标准 1–11）

| # | 要求 | 结果 |
| --- | --- | --- |
| 1 | 真实完整执行 build-release.sh 退出码 0 | ✅ `rl_0465a08e77_fa0adf0f7593`（13247 文件） |
| 2 | release 含可运行 dist/server.js | ✅（结构 4 项存在） |
| 3 | release 内启动 server，status 200 + 正确 datasetVersion | ✅ ds_fa0adf0f7593b4532421a / dataThrough 2026-09-16 / 8 priceStreams；changes 窗口 09-10→09-17 |
| 4 | Task 01–05 全量回归 | ✅ 21/21（门禁 4 + Python 6 套 + site build + 6 测试 + agent-api 4 套） |
| 5 | 三 release blue→green→blue | ✅ test_blue_green_blue（端口/槽/停槽/映射全断言） |
| 6 | 静态 root 与 API upstream 同 release | ✅（include 内容断言 + 切换后入口冒烟） |
| 7 | 五种失败注入保持旧可用 | ✅（全部旧 current+include 不变） |
| 8 | 同 RID 可重新上传激活 | ✅（每种失败后重试 rc=0） |
| 9 | 并发发布 flock 串行 | ✅ 真实 Ubuntu 服务器验证通过（/usr/bin/flock，final current = 新 release，旧提交不倒灌；另修出锁 fd 继承 bug——见 §0 第三项） |
| 10 | 旧 commit 拒 + rollback 留原因 | ✅（test_stale_commit_rejected / test_rollback_with_reason） |
| 11 | 工作区干净/临时清理 | ✅（无 maas-release-pkg/t06-act 残留、无残留进程、git clean） |

## 3. 提交记录（M5–M7，分支 task-06-m7-candidate）

```
aefc7af2d  docs: Task 06 M7 handoff（候选就绪待授权点 A）
<prev>    fix: 补同步 09-17 抓取漏掉的 price-ledger.rendered.html
<prev>    fix: 注册 Hello Minds/InclusionAI logo，修复 platform-logos 测试
<prev>    fix: run-all-tests 失败分支的 bash 3.2 全角括号解析 bug
<prev>    data: 公开投影 2026-09-18（随每日抓取合入）
<prev>    merge origin/main（每日信源抓取 2026-09-17）
<prev>    feat: Task 06 M7 候选（/agent/ 合同修正 + verify 四入口 + ops 运维文件）
<prev>    feat: Task 06 M6 /agent/ 页面完善（main）
<prev>    feat: Task 06 M5 工作流收敛（main）
```

## 4. 剩余工作（M8–M11，待授权点 A）

- **授权点 A（当前）**：M7 授权包见下节；批准后开 M8
- M8 服务器安装+首发（install-production.sh → 首次 activate → 公网冒烟）
- M9 真实客户端（含 Codex 认证环境；阻断不得冒充）
- M10 状态翻转（四入口 pending→available + changelog 真实日期）
- M11 回滚演练与收尾

## 4b. M7 授权包（申请生产切换授权）

> **最终候选（P0 修复后重新构建；原 aefc7af2d/rl_aefc7af2d4 已作废）**
>
> - `APPROVED_COMMIT` = `<P0 修复 commit 的完整 SHA，构建后填入并冻结>`
> - `APPROVED_RID` = `<P0 修复后 release build 的 RID，构建后填入并冻结>`
> - 冻结纪律：本节填入后不再追加任何影响 release 的代码变化；后续文档性提交不改变 APPROVED_COMMIT。

**候选 commit**：aefc7af2d（已作废，见下方 P0 修复）→ 以 APPROVED_COMMIT 为准（分支 task-06-m7-candidate，PR → main）
**候选 release**：`rl_aefc7af2d4_8b9fb7b09ead`（已作废）→ 以 APPROVED_RID 为准（14575 文件 / 218,946,348 字节量级；datasetVersion `ds_8b9fb7b09ead…` / dataThrough 2026-09-18；contracts rest 1.0 + skill 1.0.0；testsSkipped=false）
**配置 diff**：`ops/nginx-agent.conf`（candidate）+ `ops/maas-agent@.service` + `ops/install-production.sh --dry-run` 输出（全部为新增候选文件；现有 server 块/静态行为不动）
**离线 smoke 输出**（2026-09-18 实测）：

```
$ ./ops/verify-release.sh --offline dist-release/rl_aefc7af2d4_8b9fb7b09ead
✓ release 校验通过
✓ 离线验收通过: dist-release/rl_aefc7af2d4_8b9fb7b09ead
（manifest：files 14575 / bytes 218946348 / testsSkipped false / contracts rest:1.0 skill:1.0.0）

$ PORT=8799 PUBLIC_DATA_ROOT=<release>/data/public/v1 node <release>/agent-api/dist/server.js
[agent-api] 已加载数据版本 ds_8b9fb7b09ead…（release 内服务启动）
GET /api/v1/status → 200：datasetVersion=ds_8b9fb7b09ead… / dataThrough=2026-09-18 / counts 3806 changes · 1383 prices
POST /api/mcp initialize → serverInfo: maas-daily 1.0.0（Streamable HTTP）
```

构建链全绿：build-release.sh 完整执行（含 run-all-tests 21/21 + tracked-diff 复查 + manifest 生成）。
**线上 smoke 命令**（M8 首发后执行）：

```bash
ops/verify-release.sh --online --expect-release <rid>
# 覆盖：服务器 current/datasetVersion/dataThrough/gitCommit（固定 status 动作）
#      + REST status/changes 同版本 + MCP initialize/tools/真实调用
#      + RSS 两 feed content-type/ETag/304 + Skill manifest/install.sh
```

**回滚命令**：

```bash
# 查看可回滚版本（服务器只读）
ops/verify-release.sh --online --expect-release <current-rid>   # 或 ssh ... status
# 执行回滚（必须留原因；目标须覆盖当前 datasetVersion）
ops/rollback-release.sh <previous-rid> --reason "<原因>"
# 回滚后验收
ops/verify-release.sh --online --expect-release <previous-rid>
```

**授权后动作序列**（M8，一次授权内连续执行；P0 修复后的收敛执行链）：
1. 服务器执行 `ops/install-production.sh --dry-run` 审查 → 正式执行
2. 本地 checkout 到 **APPROVED_COMMIT**（detached HEAD，工作区干净）
3. `MAAS_DEPLOY_MODE=release ops/deploy-release.sh --commit <APPROVED_COMMIT>`（运行时注入通道；构建与激活锁定同一 SHA，RID 应等于 APPROVED_RID）
4. `ops/verify-release.sh --online --expect-release <APPROVED_RID>`（四入口验收）
5. 任一步失败：`ops/rollback-release.sh <previous-rid> --reason "…"`；通道回退=下次发布不注入 `MAAS_DEPLOY_MODE`（无任何仓库状态需要"改回"——这是 P0 修复的核心收益）

### P0 修复：部署模式运行时覆盖 + 候选 SHA pin（2026-09-18 授权点 A 前复验）

**发现的阻断**（用户复验提出，两项）：
1. 原流程"先改 `ops/deploy-mode` 为 release 再发布"会修改 tracked 文件 → 工作区脏 → `build-release.sh` preflight（`git status --porcelain` 必须为空）直接拒绝生产构建；且留下"忘记改回"风险。
2. 原候选 commit `aefc7af2d` 之后已有文档提交前进——M8 若默认执行 `deploy-release.sh`（构建 HEAD），实际构建的不是已审核的候选，RID 也会变化。"候选已验收"与"实际部署构建什么"未锁死。

**修复**：
- `deploy_mode()` 优先级改为：`MAAS_DEPLOY_MODE` 环境变量 > `ops/deploy-mode` 文件 > 默认 legacy。仓库 tracked 文件**永久保持 `DEPLOY_MODE=legacy`**（含红线测试 `test_repo_file_permanently_legacy`）。首发显式 `MAAS_DEPLOY_MODE=release ops/deploy-release.sh --commit <approved-sha>`，不污染 worktree、无状态需要恢复。
- M8 执行链改为：checkout approved SHA（detached HEAD、干净区）→ `MAAS_DEPLOY_MODE=release deploy-release.sh --commit <approved-sha>`——构建与激活都锁定已批准的完整 SHA。
- 新增 `tests/test_deploy_mode.py`（7 项：默认 legacy / 文件值 / 环境变量覆盖 / 无文件环境变量 / 非法值拒绝×2 / 仓库文件永久 legacy 红线），挂入 run-all-tests。
- 本修复产生新 commit → 原 `aefc7af2d` 不再是最终生产候选；**最终候选以本节 APPROVED_COMMIT / APPROVED_RID 为准**（见下，重新构建后填入并冻结）。

## 5. 已知限制

1. flock 并发用例在 macOS 本地 skip——已由真实 Ubuntu 服务器验证补齐（§0 第三项）；本地以 mkdir 原子锁降级验证单线程路径
2. records.test.mjs 无法完全临时目录化（Astro 构建绑定仓库路径）——残留检测兜底
3. 切换后入口冒烟（entry_smoke）在 MAAS_SMOKE_URL 未设时跳过（生产由 deploy-release.sh 设公网 URL）
