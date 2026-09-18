#!/usr/bin/env bash
# install-production.sh：一次性服务器安装（Task 06 M7 候选；M8 授权后执行）
#
# ⚠️ 授权边界：本脚本属于 M7 授权包的「待执行配置」。授权点 A（生产切换授权）
# 通过前【不得执行】——执行它会修改服务器 systemd/nginx/用户/目录。
#
# 设计约束（任务书 §3/§4/§7/§8）：
#   - 幂等：重复执行不破坏已就位状态（先检查再变更）
#   - 可审查：每个动作对应 task-06-result.md M7 授权包的配置 diff 条目
#   - 最小面：只创建专用用户/目录/受限 shell/两个 systemd 单元/nginx include 位；
#     不切换流量（激活由 activate 动作完成，nginx 改造由激活器事务完成）
#   - 不落 secret 进仓库/日志：CURSOR_SECRET 由管理员现场生成
#
# 用法（root，在服务器上执行）：
#   ./ops/server/install-production.sh --dry-run   # 只打印将执行的动作
#   ./ops/server/install-production.sh             # 真实执行
set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# ---- 布局常量（与 activate/deploy-shell/release 文档一致） ----
RELEASE_ROOT=/srv/maasweekly
SERVICE_USER=maasagent
DEPLOY_USER=maasdeploy
NGINX_AGENT_INC=$RELEASE_ROOT/shared/nginx/agent-upstream.inc
UNIT_SRC="$(cd "$(dirname "$0")" && pwd)/../maas-agent@.service"
SHELL_SRC="$(cd "$(dirname "$0")" && pwd)/maasweekly-deploy-shell"
ACTIVATE_SRC="$(cd "$(dirname "$0")" && pwd)/maasweekly-activate"
VERIFY_SRC="$(cd "$(dirname "$0")" && pwd)/release_manifest_verify.py"
NODE_BIN=/usr/bin/node

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

echo "== Task 06 生产安装（M8 授权后执行；dry-run: ${DRY_RUN}） =="

# 0. 前置检查（全部经 run：dry-run 只打印，真实执行在 Linux 服务器）
run "检查 node 22" "command -v $NODE_BIN && \$($NODE_BIN --version | grep -q '^v22' || { echo '需要 Node 22'; exit 1; })"
run "检查 nginx" "command -v nginx"
run "检查磁盘剩余 >2GB（GNU df，服务器 Linux）" \
  'avail=$(df -BG --output=avail / | tail -1 | tr -dc "0-9"); [ "$avail" -ge 2 ] || { echo "磁盘不足 2GB"; exit 1; }'

# 1. 服务用户与目录
run "创建 ${SERVICE_USER}（无 shell 登录）" \
  "id $SERVICE_USER >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin $SERVICE_USER"
run "创建 ${DEPLOY_USER}（受限 shell）" \
  "id $DEPLOY_USER >/dev/null 2>&1 || useradd --system --shell /usr/local/bin/maasweekly-deploy-shell $DEPLOY_USER"
run "创建 release 目录树" \
  "mkdir -p $RELEASE_ROOT/{incoming,releases,shared/{state,slots,nginx},locks}"
run "目录属主（incoming 可写=deploy，releases root 只读）" \
  "chown $DEPLOY_USER:$DEPLOY_USER $RELEASE_ROOT/incoming && chown root:root $RELEASE_ROOT/releases $RELEASE_ROOT/locks && chmod 0755 $RELEASE_ROOT/releases"

# 2. 受控入口（受限 shell + sudoers 单行 NOPASSWD + host key 登记由管理员在本地做）
run "安装 maasweekly-deploy-shell → /usr/local/bin" \
  "install -m 0755 '$SHELL_SRC' /usr/local/bin/maasweekly-deploy-shell"
run "安装 maasweekly-activate → /usr/local/sbin（root only）" \
  "install -m 0750 -o root -g root '$ACTIVATE_SRC' /usr/local/sbin/maasweekly-activate"
run "安装 release_manifest_verify.py → /usr/local/sbin" \
  "install -m 0750 -o root -g root '$VERIFY_SRC' /usr/local/sbin/release_manifest_verify.py"
run "sudoers：deploy 只能 NOPASSWD 调 activate（单行，不开放其他）" \
  "echo '$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/maasweekly-activate' > /etc/sudoers.d/maasweekly-activate && chmod 0440 /etc/sudoers.d/maasweekly-activate && visudo -cf /etc/sudoers.d/maasweekly-activate"

# 3. systemd 模板 + 稳定 env
run "安装 maas-agent@.service" \
  "install -m 0644 '$UNIT_SRC' /etc/systemd/system/maas-agent@.service && systemctl daemon-reload"
run "生成 shared/agent.env（若不存在；含现场生成的 CURSOR_SECRET）" \
  "if [ ! -f $RELEASE_ROOT/shared/agent.env ]; then { sed 's/^CURSOR_SECRET=.*/CURSOR_SECRET='\"\$(openssl rand -hex 32)\"'/' \$(dirname $0)/../maas-agent.env.example; } > $RELEASE_ROOT/shared/agent.env && chown root:$SERVICE_USER $RELEASE_ROOT/shared/agent.env && chmod 0740 $RELEASE_ROOT/shared/agent.env; else echo '    agent.env 已存在（保留既有 CURSOR_SECRET）'; fi"

# 4. nginx include 位（不切流量；include 首次由激活事务写入并 nginx -t）
run "创建 nginx include 目录" "mkdir -p $(dirname $NGINX_AGENT_INC)"

# 5. 完成检查
echo "== 安装清单（完成后核对） =="
cat <<'EOF'
  /etc/systemd/system/maas-agent@.service          (0644)
  /usr/local/bin/maasweekly-deploy-shell           (0755, deploy 用户 shell)
  /usr/local/sbin/maasweekly-activate              (0750, root)
  /usr/local/sbin/release_manifest_verify.py       (0750, root)
  /etc/sudoers.d/maasweekly-activate               (0440, 单行 NOPASSWD)
  /srv/maasweekly/{incoming,releases,shared,locks} (0755 / deploy 可写 incoming)
  /srv/maasweekly/shared/agent.env                 (0740 root:maasagent)
  nginx include 位：/srv/maasweekly/shared/nginx/  (激活器维护)
EOF
echo "✓ 安装完成（流量未切换——首次 activate 事务完成 nginx 绑定）"
echo "  下一步：MAAS_DEPLOY_MODE=release ops/deploy-release.sh --commit <approved-sha>"
echo "  （通道经运行时环境变量注入；仓库 ops/deploy-mode 永久保持 legacy）"
