# Task 06 结果报告：生产发布、运行保障与 P0 首发验收

日期：2026-09-17。状态：**M1/M2 通过；M3/M4 两轮复验修复完成（第一轮 5 项 + 第二轮 4 项全关，含真实 Ubuntu flock 证据）；M5–M7 未开始**。未 push（授权点 A 未到）。本任务未修改生产服务器、nginx、systemd 或线上流量。

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

## 3. 提交记录

```
<latest>  fix: verify_manifest 同步 npm bin 豁免
<prev>    fix: release 内 data 保持 public/v1 层级
<prev>    chore: dist-release 构建产物入 ignore
<prev>    fix: npm bin 链接 realpath 判定
<prev>    fix: Task 06 M3/M4 复验修复（P0×2 + P1×3）
<prev>    fix: Task 06 M1-M4 生产发布基座
a07b8c43  feat: Task 05（含复验修复）
```

## 4. 剩余工作（M5–M7，未开始）

- M5 工作流收敛（release.yml + 三 workflow 改造 + deploy/verify/rollback 客户端脚本）
- M6 /agent/ 完善（T21/T22）
- M7 候选交付 → **授权点 A（生产切换授权）**
- 之后：M8 服务器安装+首发、M9 真实客户端（含 Codex）、M10 状态翻转、M11 回滚演练

## 5. 已知限制

1. flock 并发用例在 macOS 本地 skip——已由真实 Ubuntu 服务器验证补齐（§0 第三项）；本地以 mkdir 原子锁降级验证单线程路径
2. records.test.mjs 无法完全临时目录化（Astro 构建绑定仓库路径）——残留检测兜底
3. 切换后入口冒烟（entry_smoke）在 MAAS_SMOKE_URL 未设时跳过（生产由 deploy-release.sh 设公网 URL）
