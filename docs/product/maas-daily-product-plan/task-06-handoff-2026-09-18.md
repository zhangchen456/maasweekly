# Task 06 会话 Handoff（2026-09-18，M7 候选就绪）

> 用途：重启会话后从这里继续。本文件是**会话级交接**——只覆盖 Task 06 的当前进度与下一步，不替代仓库根 `HANDOFF.md` 与 `task-06-result.md`（逐条验收记录）。

---

## 一、当前状态（一句话）

Task 06 **M1–M7 全部完成**。M7 生产候选在分支 `task-06-m7-candidate`（PR 已开到 main、未 merge），**等待授权点 A（生产切换授权）**。四入口仍 pending；生产服务器零改动；DEPLOY_MODE=legacy。

## 二、关键约束（红线，重启后必须先读）

1. **未到授权点 A**——不得修改生产服务器、nginx、systemd、不得切换线上流量
2. `ops/install-production.sh` 与 deploy-mode 翻转（legacy→release）是**授权后 M8 的同一受控操作**
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

### ops 文件补齐（候选，授权前不执行）

`maas-agent@.service`（蓝绿 systemd 模板）、`nginx-agent.conf`（候选 diff）、`maas-agent.env.example`、`install-production.sh`（--dry-run 实测过）、`ops/README.md`

### 数据修复（随 M7 分支）

- 注册 Hello Minds（hellominds.ai svg）/ InclusionAI（HF 官方头像）logo——09-17 抓取新上榜条目
- 补同步 032f95f86 漏提交的 price-ledger.rendered.html（CI 抓取流程缺 render 步骤）
- 合入 origin/main 09-17 抓取 + 提交公开投影 ds_8b9fb7b0…（dataThrough 2026-09-18）

### 踩坑（新增）

1. **macOS bash 3.2 全角括号 bug**：`"...$VAR）"`（$VAR 后紧跟全角字符）触发假 unbound variable（`${VAR}` 免疫；Linux bash 5 无此问题）——已全 ops/scripts 修复 9 处。教训：ops 脚本内变量一律 `${...}` 形式
2. **CI 抓取流程缺 render-price-ledger 步骤**：ledger.json 更新但 rendered.html 漏提交（032f95f86）；本地发现于 release build 的 tracked-diff 检查
3. **数据未合入先构建会失败**：分支构建前先 `git fetch` 看远端是否有新每日抓取提交

## 四、验证链（M7 完成时）

- 全量回归 21/21（scripts/run-all-tests.sh，修 run-all-tests 失败分支 bug 后真实跑通）
- 激活测试 18 项全绿（1 skip：macOS flock）
- access-pages 含 M7 合同断言（provider/--dir 形态/无虚构参数/无写死模型名/路径）全绿
- platform-logos 修复后全绿（Hello Minds/InclusionAI 注册）
- release build：见 task-06-result.md §4b 离线 smoke 输出

## 五、下一步（顺序固定）

1. **授权点 A**：用户审阅 task-06-result.md §4b M7 授权包（候选 commit/release manifest/配置 diff/离线 smoke/线上 smoke 命令/回滚命令）→ 批准生产切换
2. **M8**：服务器 `install-production.sh`（先 --dry-run）→ deploy-mode 翻转 release → `deploy-release.sh` 首发 → `verify-release.sh --online` 四入口验收
3. **M9**：真实客户端（Claude Code + Codex 阻断则保持）+ RSS 真实阅读器
4. **M10**：四入口状态翻转（public-access.ts pending→available）+ changelog 真实日期 + 最终 release
5. **M11**：回滚演练与收尾

## 六、重启后快速验证

```bash
cd /Users/zhangchen/Work/maasweekly
git branch --show-current        # task-06-m7-candidate
git log --oneline -5             # 应见 M7 系列 + logo/rendered 修复
git status                       # 应干净
python3 -m unittest discover -s tests -p 'test_release_activation.py'  # 18 项（1 skip）
./scripts/run-all-tests.sh       # 21/21
```

## 七、历史踩坑（M3/M4 轮遗留，仍有效）

1. **锁 fd 继承**：bash `exec 9>` 的 fd 默认被子进程继承——起子进程统一 `9>&-`
2. **pkill 自杀**：远端 `pkill -f` 匹配 ssh 自身 → 按端口找 pid 再 kill
3. **python heredoc 静默失败**：patch 后必须验证写入（或用 Edit 工具）
4. **服务器残留**：/tmp/t06-flock-* 每次跑完清理
