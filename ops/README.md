# ops/：发布、激活、回滚与生产运维

Task 06 产物。本目录是发布协议的客户端与服务器侧脚本 + 生产配置候选。
**未到授权点 A 前所有服务器文件均为候选**（install-production.sh 不会被执行）。

## 文件总览

| 文件 | 作用 | 执行位置 |
|---|---|---|
| `deploy-mode` | 部署通道**回退配置**（永久 `legacy`）。通道切换不走此文件——每次发布用 `MAAS_DEPLOY_MODE` 环境变量注入（M7 P0：改 tracked 文件会污染 clean worktree，build-release preflight 会拒绝） | 双侧读取 |
| `lib-release.sh` | 公共库：受控 host key SSH 封装、deploy-mode、RID 校验、`server_meta`（经固定 status 动作取服务器只读 metadata） | 本地 |
| `deploy-release.sh` | 发布入口：build-release.sh 构建 → 上传 incoming → 激活 → 公网冒烟 | 本地 |
| `verify-release.sh` | 验收：`--offline` 校验产物 manifest；`--online` 四入口（REST/MCP/RSS/Skill）与服务器 current 同版本 | 本地 |
| `rollback-release.sh` | 回滚入口：`<rid> --reason`（必须留原因） | 本地 |
| `maas-agent@.service` | agent-api 蓝绿槽位 systemd 模板（blue=8788 / green=8789） | 服务器 /etc/systemd/system/ |
| `maas-agent.env.example` | 环境变量样例（仅变量名与安全默认值；真实 secret 现场生成） | 服务器 /srv/maasweekly/shared/agent.env |
| `nginx-agent.conf` | nginx candidate 配置：REST/MCP 限流与代理、feed/Skill 行为头 | 服务器（候选 diff） |
| `install-production.sh` | 一次性幂等安装（M8 授权后执行；`--dry-run` 可审查） | 服务器 root |
| `known_hosts.production` | 受控 host key（禁运行时 ssh-keyscan；轮换流程见下） | 本地 |
| `server/maasweekly-deploy-shell` | maasdeploy 受限 shell：只放行 rsync-to-incoming / activate / rollback / status | 服务器 /usr/local/bin/ |
| `server/maasweekly-activate` | root 激活器：flock 互斥、manifest 校验、蓝绿事务（含 nginx）、指针、retention | 服务器 /usr/local/sbin/ |
| `server/release_manifest_verify.py` | 服务器侧独立 manifest 校验器 | 服务器 /usr/local/sbin/ |

## 发布协议（release 通道）

```
本地: build-release.sh --commit <SHA>        # 唯一构建入口（含全量测试）
      ↓ release/ 目录 + manifest（RID = rl_<git10>_<ds12>）
rsync → 服务器 incoming/<rid>/               # 受限 shell 只允许写这里
      ↓
maasweekly-activate activate <rid>            # flock 串行 → 校验 → 蓝绿切换
      1. 候选槽位起服务 + /api/v1/status 冒烟
      2. 候选 nginx include（root 与 upstream 绑定同一 release）
      3. nginx -t（候选 include 就位后校验真实配置）
      4. 原子替换生效 include + reload
      5. 切换后入口冒烟（静态+API 同 release）
      6. 停旧槽（旧 worker 排空后）
      ↓ 任一步失败 → 恢复旧状态，候选退回 incoming（同 RID 可重试）
verify-release.sh --online --expect-release <rid>   # 四入口验收
```

## 服务器 status（只读 metadata）

```bash
ops/verify-release.sh --online --expect-release <rid>
# 内部经受限 shell 执行固定动作 `status`，返回：
#   current / previous / slots / releases / incoming
#   datasetVersion / dataThrough / gitCommit（M7 新增——verify 依赖，
#   替代了此前任意 python3 -c 读文件的面）
```

## 回滚

```bash
ops/rollback-release.sh <rid> --reason "<原因>"
ops/verify-release.sh --online --expect-release <rid>
```

服务器侧规则：目标 release 必须覆盖当前 datasetVersion（防数据回退丢公开 ID）；
失败时只恢复指针/include/服务，目标 release 保留原位（P1 复验修复）。

## 故障排查

| 症状 | 排查 |
|---|---|
| 激活失败 exit=5 | 候选服务起不来——看 `journalctl -u maas-agent@<slot>`；incoming 保留，修复后同 RID 重试 |
| 激活失败 exit=7 | nginx -t 或 reload 失败——旧 include 已自动恢复，线上无变化；查 `nginx -t` 输出 |
| 公网冒烟 datasetVersion 不匹配 | 新旧混版阻断——verify-release.sh --online 会 fail；查 current 与 include 是否同 release |
| 持锁超时 | 确认无残留服务持有 release.lock（激活器已统一 `9>&-` 防 fd 继承） |
| 服务器 status 不可读 | `ssh maasdeploy@host status` 直测；检查 sudoers 单行 NOPASSWD 与 deploy-shell 就位 |

## host key 轮换

`known_hosts.production` 由管理员核验后提交（不做运行时 ssh-keyscan）。
服务器密钥轮换时：管理员在受控终端重新核验指纹 → 更新本文件 → 单独 commit
（消息注明轮换原因与核验人）。

## 授权边界（红线）

- 未显式注入 `MAAS_DEPLOY_MODE=release` 时（默认/仓库文件均为 legacy）：
  deploy-release.sh 走旧 rsync 直写通道，服务器无新机制。
- release 通道首发（`MAAS_DEPLOY_MODE=release` + `--commit <approved-sha>`）
  与执行 `install-production.sh` 是**同一受控操作**，前置条件：M7 授权包
  （APPROVED_COMMIT/APPROVED_RID/manifest/配置 diff/冒烟输出/回滚命令）获用户批准。
- 仓库 tracked 文件 `ops/deploy-mode` **永久保持 legacy**——不得通过修改它切换通道
  （会污染 clean worktree，build-release.sh preflight 拒绝生产构建）。
- 不把 secret 写进 systemd unit、命令行、Actions 参数或日志；
  `CURSOR_SECRET` 只存在于服务器 `shared/agent.env`（root:maasagent 0740）。
