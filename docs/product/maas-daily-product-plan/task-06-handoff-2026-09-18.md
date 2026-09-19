# Task 06 会话 Handoff（2026-09-18，M7 候选就绪）

> 用途：重启会话后从这里继续。本文件是**会话级交接**——只覆盖 Task 06 的当前进度与下一步，不替代仓库根 `HANDOFF.md` 与 `task-06-result.md`（逐条验收记录）。

---

## 一、当前状态（一句话）

Task 06 **M1–M7 完成；M8 进行中**（B1 Node22 ✓ / B2 systemd+用户+sudoers ✓ / B3 前发现并修复 nginx mixed-scope P0）。最终候选在分支 `task-06-m7-candidate`（PR #1 → main、未 merge）：`APPROVED_COMMIT`=`6bc9b0b7cc5f…` / `APPROVED_RID`=`rl_6bc9b0b7cc_8b9fb7b09ead`（第六代）。**B3 已试三次：CHDIR P0 → 双 P0（MDWE/权限）→ 双消费者 P0（分树）。第三次 activate 成功但静态层 404 → 已 emergency rollback 回 legacy。下一步=B2.4 幂等重跑 → B3 第四次**

## 二、关键约束（红线，重启后必须先读）

1. **未到授权点 A**——不得修改生产服务器、nginx、systemd、不得切换线上流量
2. `ops/install-production.sh` 与 release 通道首发是**授权后 M8 的同一受控操作**；通道经 `MAAS_DEPLOY_MODE=release` 运行时注入，**仓库 tracked 文件 ops/deploy-mode 永久保持 legacy**（有红线测试锁定）
3. Task 04 遗留：**Codex 客户端验证保持阻断**（无 OpenAI 认证环境，不能用 curl/SDK 冒充）
4. 服务器只用于只读审计（`ssh -i ~/Downloads/zhangchen.pem root@47.237.135.97`）
5. main 分支只经 PR 合入；工作分支 `task-06-m7-candidate`

## 三、M7 交付内容（2026-09-18）

### /agent/ 合同修正（全部对照 agent-api 实现核对）

| 项 | 修正 |
|---|---|
| Skill 参数 | 删虚构 `--update`/`--uninstall`；更新=同一 `--dir` 重跑；`--dir` 是最终 Skill 目录 |
| MCP limit | 默认 10、最大 30（MCP_LIMITS）；REST 20/100 注明 |
| REST 路径 | `/api/v1/items/{id}`、`/api/v1/evidence/{id}`；参数 `provider`（非 platform） |
| 验证样例 | 去手写 gpt-6-astra，改不依赖具体模型名 |

### verify-release.sh 安全修复

- 删受限 shell 任意 `python3 -c`（`current_ds_from_server`）→ `maasweekly-activate status` 返回只读 metadata（datasetVersion/dataThrough/gitCommit）；激活测试 17→18 项（新增 `test_status_metadata_readonly`）
- online verify 覆盖四入口：REST（同版本）+ MCP（initialize/tools/list/真实调用）+ RSS（content-type/ETag/304）+ Skill（manifest/install.sh）

### ops 文件补齐

`maas-agent@.service`（蓝绿 systemd 模板）、`ops/nginx/`（http conf + server snippet 稳定配置，M8-B3 P0 后取代单文件 nginx-agent.conf）、`maas-agent.env.example`、`install-production.sh`（OPS_DIR 自适配 + nginx 接线段）、`ops/README.md`

### M8-B3 前 P0：nginx mixed-scope include（B2 后只读检查发现）

- **缺陷**：activate 把 root（server ctx）与 upstream（http ctx）写进同一个 agent-upstream.inc——真实 nginx 下任何 include 位置都必然 nginx -t 失败。未 activate，线上零影响
- **修复**：三 include 动态文件（agent-upstream/site-root/agent-routes，作用域严格分离）+ conf.d/snippet 两个稳定配置；事务全有或全无恢复；install-production 生成首发兼容态（site-root=/var/www/maasweekly、routes 空——旧站行为完全不变）
- 激活套件 18→**27** 项（三 include 边界/失败恢复×3/首发兼容态/routes 合同/install 路径/配置作用域红线）

### 数据修复（随 M7 分支）

- 注册 Hello Minds（hellominds.ai svg）/ InclusionAI（HF 官方头像）logo——09-17 抓取新上榜条目
- 补同步 032f95f86 漏提交的 price-ledger.rendered.html（CI 抓取流程缺 render 步骤）
- 合入 origin/main 09-17 抓取 + 提交公开投影 ds_8b9fb7b0…（dataThrough 2026-09-18）

### 踩坑（新增）

1. **macOS bash 3.2 全角括号 bug**：`"...$VAR）"`（$VAR 后紧跟全角字符）触发假 unbound variable（`${VAR}` 免疫；Linux bash 5 无此问题）——已全 ops/scripts 修复 9 处。教训：ops 脚本内变量一律 `${...}` 形式
2. **CI 抓取流程缺 render-price-ledger 步骤**：ledger.json 更新但 rendered.html 漏提交（032f95f86）；本地发现于 release build 的 tracked-diff 检查
3. **数据未合入先构建会失败**：分支构建前先 `git fetch` 看远端是否有新每日抓取提交

## 四、验证链（M7 完成时）

- 全量回归 22/22（激活套件 27→34 项：M8-B3 P0 后加候选 release 防混版 7 项）
- 激活测试 18 项全绿（1 skip：macOS flock）
- access-pages 含 M7 合同断言（provider/--dir 形态/无虚构参数/无写死模型名/路径）全绿
- platform-logos 修复后全绿（Hello Minds/InclusionAI 注册）
- release build：见 task-06-result.md §4b 离线 smoke 输出

## 五、下一步（顺序固定）

1. **B2.1 重跑（下一步）**：从新 APPROVED_COMMIT 重制 staging → 幂等重跑 `install-production.sh`（覆盖旧 unit + 新增 maas-agent-run wrapper，daemon-reload；nginx 接线已就位不变）→ 确认 blue/green inactive、旧首页零变化
2. **B3 首发**：本地 `git checkout <APPROVED_COMMIT>`（detached HEAD 干净区）→ `MAAS_DEPLOY_MODE=release ops/deploy-release.sh --commit <APPROVED_COMMIT>` → `verify-release.sh --online --expect-release <APPROVED_RID>` 四入口验收；任一步失败 rollback（通道回退=下次不注入环境变量，无仓库状态要恢复）
3. **M9**：真实客户端（Claude Code + Codex 阻断则保持）+ RSS 真实阅读器
4. **M10**：四入口状态翻转（public-access.ts pending→available）+ changelog 真实日期 + 最终 release
5. **M11**：回滚演练与收尾

## 六、重启后快速验证

```bash
cd /Users/zhangchen/Work/maasweekly
git branch --show-current        # task-06-m7-candidate
git log --oneline -5             # 应见 M7 系列 + logo/rendered 修复
git status                       # 应干净
python3 -m unittest discover -s tests -p "test_release_activation.py"  # 43 项（1 skip）
./scripts/run-all-tests.sh       # 22/22
```

## 七、历史踩坑（M3/M4 轮遗留，仍有效）

1. **锁 fd 继承**：bash `exec 9>` 的 fd 默认被子进程继承——起子进程统一 `9>&-`
2. **pkill 自杀**：远端 `pkill -f` 匹配 ssh 自身 → 按端口找 pid 再 kill
3. **python heredoc 静默失败**：patch 后必须验证写入（或用 Edit 工具）
4. **服务器残留**：/tmp/t06-flock-* 每次跑完清理
