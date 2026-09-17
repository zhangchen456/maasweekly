# Task 06 会话 Handoff（2026-09-17）

> 用途：重启会话后从这里继续。本文件是**会话级交接**——只覆盖 Task 06 的当前进度与下一步，不替代仓库根 `HANDOFF.md`（那是全项目长期交接文档）与 `task-06-result.md`（那是逐条验收记录）。

---

## 一、当前状态（一句话）

Task 06（生产发布/运行保障/P0 首发验收）**M1–M4 全部完成，两轮复验修复全关（第一轮 5 项 + 第二轮 4 项），已做收尾提交 `c3bf385cd`，未 push**。下一步是 **M5（工作流收敛）**，但须等用户复验确认后才开始。

## 二、关键约束（红线，重启后必须先读）

1. **未到生产授权点 A**——不得修改生产服务器、nginx、systemd、不得切换线上流量
2. **完成本轮复验前不开始 M5**——四项阻断已关闭，等用户复验确认
3. Task 04 遗留：**Codex 客户端验证保持阻断**（无 OpenAI 认证环境，不能用 curl/SDK 冒充）
4. Ubuntu 服务器只用于**只读审计与 flock 验证**（/tmp 下临时脚本，未触碰生产目录）
5. 服务器访问：`ssh -i ~/Downloads/zhangchen.pem root@47.237.135.97`

## 三、已完成（本轮会话产出）

### 第二轮复验四项修复（提交 c3bf385cd）

| 项 | 缺陷 | 修复 |
|---|---|---|
| P0 | nginx -t 校验的是磁盘旧配置，候选 include 从未参与 | 候选 include 先就位生效路径（`write_candidate_include "$EFFECTIVE_INC"`）再无参 `nginx -t` |
| P1 | rollback 失败会搬走历史 release（破坏 previous 链） | `recover_failed_activation` 加 `keep_release` 参数，rollback 失败只恢复服务/指针/include |
| P1 | flock 从未有真实证据（macOS skip，CI 未覆盖） | 真实 Ubuntu 服务器验证通过（详见下） |
| 首发边界 | 第一次激活旧 include 不存在时，reload 失败留下失效 root 残留 | 三态快照：`.rollback.inc` / `.no-inc` 标记，`_inc_restore` 精确恢复（含恢复到"不存在"） |

### 真实 Ubuntu flock 证据（复验收标准第 9 项）

- 在服务器（/usr/bin/flock）临时 release root 注入，新旧 release 并发 activate
- 结果：`final current = rl_aaaaaaaaaa_bbbbbbbbbbbb`（新 release 胜出，旧提交未倒灌），退出码 0
- **过程中修出真实 bug**：`exec 9>release.lock` 的锁 fd 被 activate-hook 起的后台服务继承 → 激活完成后锁仍被 90s 桩服务持有 → 下次激活等锁超时（服务器实测两次复现）。修复：hook/systemctl 调用统一 `9>&-` 关闭 fd 继承
- 验证脚本在服务器 `/tmp/flock-verify.py`（含 activate-hook 桩）——重启后可重跑

### 验证链

- 本地：17 项激活测试（test_release_activation.py）+ 13 项 build 测试（test_release_build.py）全绿（1 skip：macOS flock 用例）
- 真实构建：build-release.sh 完整执行退出码 0，release `rl_0465a08e77_fa0adf0f7593`（13247 文件 / 151MB），release 内 server.js 启动冒烟 status 200
- 全量回归 21/21（scripts/run-all-tests.sh）

## 四、核心文件（改动全部已提交）

| 文件 | 作用 |
|---|---|
| `ops/server/maasweekly-activate` | 激活协议核心（本轮：nginx-t 就位校验、三态 include 快照、keep_release、9>&-） |
| `ops/server/release_manifest_verify.py` | 服务器侧独立校验器（npm bin 豁免、testsSkipped 拒绝） |
| `pipeline/scripts/release_manifest.py` | manifest build/verify/compare（builder 与 server verify 共用规则） |
| `scripts/build-release.sh` | 唯一构建入口（编译→保留 dist→omit=dev 裁剪） |
| `scripts/run-all-tests.sh` | 统一回归入口（21 项真实退出码） |
| `tests/test_release_activation.py` / `test_release_build.py` | 17 + 13 项测试 |
| `docs/product/maas-daily-product-plan/task-06-result.md` | 验收记录（§0 第二轮四项 + 11 条复验收逐条结果） |

## 五、下一步（顺序固定）

1. **等用户复验确认第二轮四项修复**（P0 nginx-t / P1 rollback keep_release / P1 flock 证据 / 首发边界）
2. **M5：工作流收敛**（task-06-production-release.md 的 T13/T14 + §5）
   - 新建 `.github/workflows/release.yml`（reusable workflow_call：build job + artifact + deploy job with concurrency: production-release）
   - 改造 daily-update/weekly-update：**先 commit/push 再从精确 SHA 构建**（当前是先部署后提交，违反 §5.2）
   - deploy.yml 白名单反转（忽略 data/src-data/product-docs 等，防 Skill 源/合同/API 代码漏触发）
   - `ops/deploy-mode`（legacy|release）迁移期开关
   - SSH host key → secret + `ops/known_hosts.production` 受控
   - 客户端脚本 `ops/{deploy,verify,rollback}-release.sh`
3. **M6**：/agent/ 完善（T21/T22，public-access.ts 扩 rss surface）
4. **M7**：候选交付 → **授权点 A**（提交 commit/manifest/配置 diff/冒烟输出/回滚命令清单，申请生产切换授权）
5. M8–M11：服务器安装+首发、真实客户端（含 Codex）、状态翻转、回滚演练

## 六、重启后快速验证（确认环境无恙）

```bash
cd /Users/zhangchen/Work/maasweekly
git log --oneline -3        # 应见 c3bf385cd 在顶
git status                  # 应干净
python3 -m unittest discover -s tests -p 'test_release_activation.py' -v  # 17 项（1 skip）
```

## 七、本轮踩坑记录（避免重蹈）

1. **锁 fd 继承**：bash `exec 9>` 的 fd 默认被子进程继承——后台服务持锁导致后续激活等锁超时。任何锁场景起子进程都要显式 `9>&-`
2. **pkill 自杀**：远端 `pkill -f "模式"` 会匹配 ssh 命令行自身（含模式串）→ 会话 255。清进程按端口找 pid（`ss -tlnp | grep 端口`）再 kill
3. **python heredoc patch 静默失败**：`python3 - <<'EOF'` 内 assert 失败或字符串未闭合时无输出——patch 后必须验证真的写入（或直接用 Edit 工具）
4. **服务器上残留**：flock 验证脚本/桩服务在 /tmp（root 目录 /tmp/t06-flock-* 已清理）；每次跑完 `rm -rf /tmp/t06-flock-*`
