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
| `nginx/maasweekly-agent-http.conf` | nginx 稳定配置（http context）：REST/MCP 限流 zone + upstream include。安装到 `/etc/nginx/conf.d/maasweekly-agent.conf` | 服务器 |
| `nginx/maasweekly-agent-server.conf` | nginx 稳定 snippet（server context）：routes include。安装到 `/etc/nginx/snippets/maasweekly-agent.conf` | 服务器 |
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
      2. 三份候选 include 全部就位（作用域严格分离，M8-B3 P0）：
         agent-upstream.inc（http ctx：upstream 槽位端口）
         site-root.inc（server ctx：root <release>/site）
         agent-routes.inc（server ctx：REST/MCP/RSS/Skill locations）
      3. nginx -t（三份候选就位后校验真实配置）
      4. reload + 指针切换
      5. 切换后入口冒烟（静态+API 同 release）
      6. 停旧槽（旧 worker 排空后）
      ↓ 任一步失败 → 三 include 全有或全无恢复，候选退回 incoming（同 RID 可重试）
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

## online verify 失败的处置判例（2026-09-20 第八代确立）

verify 失败 ≠ 一律 rollback。按失败性质分类：

| 失败性质 | 处置 |
|---|---|
| 可用性（入口不可达/5xx）、新旧混版、数据错误、版本不一致 | **立即 emergency rollback**（首发无 previous 时用 legacy 回退） |
| 纯非破坏性合同偏差（如响应头字面值），且功能实质可用、内容正确 | **保留现状**，立即修复并滚动发布下一 release |

判例来源：B3 第五次首发（rl_77f48c7b53）——四入口实质全部可用（feed 200 + 内容正确 + 分树权限验证通过），仅 RSS `Content-Type` 为 `text/xml` 而非合同的 `application/rss+xml`（nginx mime.types 对 `.xml` 的映射覆盖了 `default_type`）。判定为第二类：保留上线状态，第八代修复（feed location 局部 `types { }` 清空）后滚动发布。回退判定的裁决权在用户/维护者，不在脚本。

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

## 发布包保留与定时清理

成功激活后自动清理 `/srv/maasweekly/releases`，最多保留 3 个受管理发布包。
优先保留 `current` 和 `previous`，其余按 `gitCommitTimestamp` 和 release ID 降序补足；
因此回滚时仍保护正在使用的旧版本。历史 API 数据已内置在各包中，不再按相同数据版本或 7 天期限保留额外包。
删除前验证保留包内的历史数据清单和文件大小，异常时停止清理并报错。
清理与激活共用发布锁；清理失败不会把已完成的激活报告为失败。

`maas-release-cleanup.timer` 每天北京时间 04:00 调用同一个 `cleanup`，关机错过后补执行。
`install-production.sh` 安装并启用该任务。已有服务器仅更新激活器的清理函数并安装这两个单元，
无需重装其他生产配置。未知目录和符号链接不会删除。

```sh
/usr/local/sbin/maasweekly-activate cleanup-plan
systemctl list-timers maas-release-cleanup.timer
journalctl -u maas-release-cleanup.service
```

2026-10-04 已在生产安装清理规则并启用 timer，首次手动执行 `Result=success / ExecMainStatus=0`；
下次计划执行为北京时间 2026-10-05 04:00。旧激活器备份位于服务器
`/srv/maasweekly/shared/state/activator-before-retention-20261004`。

## T05后台监控（本地候选）

信源与任务入口、受控artifact/inbox采集、migration5、权限隔离、故障恢复及生产接入配置见 [T05交付记录](../docs/product/admin-operations-v1/T05-implementation.md)。后台API不读生产抓取/SSH密钥或原始日志，不提供抓取/发布重试。新增Actions回执适配未部署、未安装新调度。

## T06邮件投递与服务健康（本地候选）

入口、邮件状态/租约变化、受控供应商查询/验签回执与健康inbox协议见 [T06交付记录](../docs/product/admin-operations-v1/T06-implementation.md)。新版停止超时/过期租约自动重发；切换时不要混跑旧sender。维护脚本可选`--admin-records`只输出实际backup/隔离SQLite恢复/health结果，没有安装调度或新通知。后台不持有SSH、systemctl或恢复执行权限。

## T07问题辅助诊断（本地候选）

独立诊断 worker、migration7、人工查询修复/发布引用、逐条反馈验证及恢复协议见 [T07交付记录](../docs/product/admin-operations-v1/T07-implementation.md)。默认mock、付费关闭；没有生产worker/调度、代码托管自动同步、仓库写入或自动部署。回滚先停止worker，保留私有诊断材料、费用与审计；执行未知必须先核对供应商。

## T08付费订阅（部分本地候选）

本机模拟器、8/9加法迁移及readonly回调worker已本地验证；真实渠道/沙箱尚未配置，未完成收费开发与验收。合同、运行/恢复与明确缺口见 [T08交接](../docs/product/admin-operations-v1/T08-implementation.md)。默认disabled，无live密钥/真实退款/新增生产回调代理/调度；保留金融事实，不DROP新表。
