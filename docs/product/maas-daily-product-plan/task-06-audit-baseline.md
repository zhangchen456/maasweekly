# Task 06 生产审计基线（2026-09-17 只读审计，M2）

> 全部经 root 密钥只读执行；敏感值（密钥内容/fingerprint）已脱敏。
> 服务器现状与任务书假设的差异已在结果文档解释。

## 环境基线

| 项 | 值 |
| --- | --- |
| 主机 | aliyun-099（47.237.135.97），Ubuntu，2 vCPU / 3.4Gi 内存 |
| 磁盘 | /dev/vda3 40G，已用 8.6G（23%），可用 29G——release 目录充足 |
| nginx | 1.28.3 (Ubuntu)，active；sites-enabled：maasweekly.conf + skill4u.conf + **skill4u.conf.bak（已知 warn 源，与本项目无关）** |
| Node | /opt/node-v24.19.0/bin/node（v24，满足 ≥22.12；不在 PATH——systemd unit 用绝对路径） |
| flock | /usr/bin/flock ✓ |
| systemd | 259 ✓ |
| maasagent 用户 | 不存在（install-production.sh 创建） |

## 证书与域名（任务书 R1 风险消除）

- **daily.maas.click 证书已存在**：certbot，有效期至 2026-12-03（77 天），域名 daily.maas.click
- 旧域名证书并存：week.maas.click / mw.zhangchen456.xyz（均 301 到主域名）
- **DNS 已解析**：daily.maas.click → 47.237.135.97（本机 getent 确认）
- 线上 HTTPS 200（127.0.0.1 resolve 自测）

## nginx 现有结构（改造基础）

- `sites-available/maasweekly.conf`：80 端口统一 301 → 443；两个旧域名 server 块（证书+301）；主域名 server 块 include snippet
- `snippets/maasweekly-https.conf`：TLS 配置 + `root /var/www/maasweekly` + gzip + /changes 旧路由 301 + `/_astro/` immutable 一年 + `/` no-cache
- **改造点**（与任务书 §8 的差异）：root 改 current 符号链接；新增 /api/v1/、/api/mcp、feed 双 location、limit_req 两桶；保留全部现有 301/缓存行为

## 部署通道现状

- 站点根：/var/www/maasweekly（maasdeploy:maasdeploy 755）；最近部署 2026-09-17 07:36（CI daily-update 的 Task 04 版本——/agent/ 404 确认 Task 05 未上线，符合基线预期）
- 受限 shell：/usr/local/bin/maasweekly-deploy-shell——**只放行 `rsync --server *`，其余拒绝**（与 HANDOFF 记录一致；扩展 activate/status/rollback 动作需替换此文件）
- authorized_keys：`command="...deploy-shell",no-pty,no-agent-forwarding,no-port-forwarding,no-X11-forwarding`（前缀限制完整，替换 shell 即扩展能力，key 本身不动）
- sudo 可用（root 登录路径；sudoers.d 用于 NOPASSWD 精确授权）

## 服务器目录计划（审计确认）

- /srv 存在且为 root 属主（空）——**采用 /srv/maasweekly 作为 release 根**（与 / 同文件系统，mv 原子成立；磁盘 29G 可用支撑多 release × ~200MB）
- 旧 /var/www/maasweekly 保留为迁移期回滚保险（Task 06 首发后 7 天归档删除）

## 工作流与线上状态

- 三条 workflow 现走裸 rsync --delete 直写 /var/www/maasweekly（改造目标 D7）
- 线上 /agent/ /feed.xml /api/v1/status 均 404（Task 05 未推送；首发时一并上线）
