#!/usr/bin/env bash
# install-production.sh：一次性服务器安装（Task 06 M7；M8-B3 P0 修订）
#
# ⚠️ 授权边界：本脚本属于 M7 授权包的「待执行配置」。授权点 A（生产切换授权）
# 通过前【不得执行】——执行它会修改服务器 systemd/nginx/用户/目录。
#
# 设计约束（任务书 §3/§4/§7/§8）：
#   - 幂等：重复执行不破坏已就位状态（先检查再变更）；nginx 改造失败自动回滚
#   - 可审查：每个动作对应 task-06-result.md M7 授权包的配置 diff 条目
#   - 最小面：只创建专用用户/目录/受限 shell/systemd 单元/nginx 接线；
#     不切换流量（首次 activate 事务才写入动态 root/routes 并接 API 路由）
#   - 不落 secret 进仓库/日志：CURSOR_SECRET 由管理员现场生成
#
# 路径解析：从仓库根的 ops/ 或 ops/server/ 下执行均可（OPS_DIR 自适配）。
# 用法（root，在服务器上执行）：
#   ops/install-production.sh --dry-run   # 只打印将执行的动作
#   ops/install-production.sh             # 真实执行
set -euo pipefail

# OPS_DIR 自适配：$0 在 ops/ 下（install-production.sh）或 ops/server/ 下
# （staging 包布局）都解析到 ops/ 目录
OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
case "$OPS_DIR" in
  */ops/server) OPS_DIR="${OPS_DIR%/server}" ;;
  */ops) : ;;
  *) echo "✗ 必须从 ops/ 或 ops/server/ 下执行（当前: ${OPS_DIR}）" >&2; exit 2 ;;
esac

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# ---- 布局常量（与 activate/deploy-shell/release 文档一致） ----
RELEASE_ROOT=/srv/maasweekly
SERVICE_USER=maasagent
DEPLOY_USER=maasdeploy
NGINX_CONF_D=/etc/nginx/conf.d
NGINX_SNIPPETS=/etc/nginx/snippets
NGINX_HTTP_CONF=$NGINX_CONF_D/maasweekly-agent.conf
NGINX_SERVER_SNIPPET=$NGINX_SNIPPETS/maasweekly-agent.conf
HTTPS_CONF=$NGINX_SNIPPETS/maasweekly-https.conf
NGINX_DYN_DIR=$RELEASE_ROOT/shared/nginx
DYN_UPSTREAM=$NGINX_DYN_DIR/agent-upstream.inc
DYN_SITE_ROOT=$NGINX_DYN_DIR/site-root.inc
DYN_ROUTES=$NGINX_DYN_DIR/agent-routes.inc

UNIT_SRC="$OPS_DIR/maas-agent@.service"
ENV_EXAMPLE_SRC="$OPS_DIR/maas-agent.env.example"
SHELL_SRC="$OPS_DIR/server/maasweekly-deploy-shell"
ACTIVATE_SRC="$OPS_DIR/server/maasweekly-activate"
VERIFY_SRC="$OPS_DIR/server/release_manifest_verify.py"
RUN_SRC="$OPS_DIR/server/maas-agent-run"
NGINX_HTTP_SRC="$OPS_DIR/nginx/maasweekly-agent-http.conf"
NGINX_SERVER_SRC="$OPS_DIR/nginx/maasweekly-agent-server.conf"
NODE_BIN=/usr/bin/node

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

echo "== Task 06 生产安装（授权后执行；dry-run: ${DRY_RUN}） =="

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
run "安装 maas-agent-run wrapper → /usr/local/bin（候选槽位运行候选 release，M8-B3 P0）" \
  "install -m 0755 '$RUN_SRC' /usr/local/bin/maas-agent-run"
run "sudoers：deploy 只能 NOPASSWD 调 activate（单行，不开放其他）" \
  "echo '$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/maasweekly-activate' > /etc/sudoers.d/maasweekly-activate && chmod 0440 /etc/sudoers.d/maasweekly-activate && visudo -cf /etc/sudoers.d/maasweekly-activate"

# 3. systemd 模板 + 稳定 env
run "安装 maas-agent@.service" \
  "install -m 0644 '$UNIT_SRC' /etc/systemd/system/maas-agent@.service && systemctl daemon-reload"
run "生成 shared/agent.env（若不存在；含现场生成的 CURSOR_SECRET）" \
  "if [ ! -f $RELEASE_ROOT/shared/agent.env ]; then { sed 's/^CURSOR_SECRET=.*/CURSOR_SECRET='\"\$(openssl rand -hex 32)\"'/' '$ENV_EXAMPLE_SRC'; } > $RELEASE_ROOT/shared/agent.env && chown root:$SERVICE_USER $RELEASE_ROOT/shared/agent.env && chmod 0740 $RELEASE_ROOT/shared/agent.env; else echo '    agent.env 已存在（保留既有 CURSOR_SECRET）'; fi"

# ---- 4. nginx 接线（M8-B3 P0：三 include 结构；幂等 + 失败回滚） ----
# 4a. http context 稳定配置（conf.d）
run "安装 http 级配置 → $NGINX_HTTP_CONF" \
  "install -m 0644 '$NGINX_HTTP_SRC' '$NGINX_HTTP_CONF'"
# 4b. server context 稳定 snippet
run "安装 server 级 snippet → $NGINX_SERVER_SNIPPET" \
  "install -m 0644 '$NGINX_SERVER_SRC' '$NGINX_SERVER_SNIPPET'"
# 4c. 三个动态 include 的首发兼容态（幂等：已存在则不覆盖——激活器事务维护）
#     site-root → 旧静态根（行为完全不变）；upstream → 占位（无路由指向）；
#     routes → 空（/api、feed、Skill 仍走既有 location / 的 404/静态行为）
run "生成动态 include 首发兼容态（site-root=旧根 / upstream 占位 / routes 空）" \
  "mkdir -p '$NGINX_DYN_DIR' && \
   [ -f '$DYN_SITE_ROOT' ] || printf '%s\n' 'root /var/www/maasweekly;' > '$DYN_SITE_ROOT'; \
   [ -f '$DYN_UPSTREAM' ] || printf '%s\n' 'upstream agent_api {' '    server 127.0.0.1:8788;' '}' > '$DYN_UPSTREAM'; \
   [ -f '$DYN_ROUTES' ] || printf '%s\n' '# intentionally empty before first activation' > '$DYN_ROUTES'; \
   ls -l '$DYN_SITE_ROOT' '$DYN_UPSTREAM' '$DYN_ROUTES'"
# 4d. 改造 maasweekly-https.conf（幂等：备份 → 精确替换 root → 追加 include →
#     nginx -t 失败恢复备份并 exit；成功才 reload）
if [ "$DRY_RUN" = "1" ]; then
  echo "· 改造 ${HTTPS_CONF}（root → site-root.inc include；追加 agent snippet include）"
  echo "    [dry-run] 幂等检查 + timestamp backup + sed 精确替换 + nginx -t + reload"
else
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP="$HTTPS_CONF.pre-m8-${TS}"
  if ! grep -q 'include /srv/maasweekly/shared/nginx/site-root.inc;' "$HTTPS_CONF"; then
    cp -a "$HTTPS_CONF" "$BACKUP"
    # 精确替换 root 行（只匹配既有静态根）
    sed -i 's|^root /var/www/maasweekly;$|include /srv/maasweekly/shared/nginx/site-root.inc;|' "$HTTPS_CONF"
    # 追加 agent snippet include（幂等：不重复插入）
    if ! grep -q 'include /etc/nginx/snippets/maasweekly-agent.conf;' "$HTTPS_CONF"; then
      printf '\n# Agent 路由（REST/MCP/RSS/Skill；动态内容由激活器维护）\ninclude /etc/nginx/snippets/maasweekly-agent.conf;\n' >> "$HTTPS_CONF"
    fi
    echo "· 已改造 ${HTTPS_CONF}（备份: ${BACKUP}）"
    if ! nginx -t; then
      echo "✗ nginx -t 失败——恢复备份 $BACKUP" >&2
      cp -a "$BACKUP" "$HTTPS_CONF"
      nginx -t || true
      exit 1
    fi
    nginx -s reload
    echo "  ✓ nginx -t 通过并已 reload（旧站行为应无变化）"
  else
    echo "· $HTTPS_CONF 已含 site-root.inc include（幂等跳过）"
  fi
fi

# 5. 完成检查
echo "== 安装清单（完成后核对） =="
cat <<EOF
  /etc/systemd/system/maas-agent@.service          (0644)
  /usr/local/bin/maasweekly-deploy-shell           (0755, deploy 用户 shell)
  /usr/local/sbin/maasweekly-activate              (0750, root)
  /usr/local/sbin/release_manifest_verify.py       (0750, root)
  /usr/local/bin/maas-agent-run                    (0755, 槽位启动 wrapper：候选槽位运行候选 release)
  /etc/sudoers.d/maasweekly-activate               (0440, 单行 NOPASSWD)
  /srv/maasweekly/{incoming,releases,shared,locks} (0755 / deploy 可写 incoming)
  /srv/maasweekly/shared/agent.env                 (0740 root:maasagent)
  $NGINX_HTTP_CONF       (0644, http ctx：限流 zone + upstream include)
  $NGINX_SERVER_SNIPPET  (0644, server ctx：routes include)
  $HTTPS_CONF            (root → site-root.inc；+ agent snippet include)
  动态 include（激活器事务维护）：$NGINX_DYN_DIR/
    site-root.inc（初始 /var/www/maasweekly）/ agent-upstream.inc（占位 8788）
    / agent-routes.inc（空——首发激活时写入）
EOF
echo "✓ 安装完成（流量未切换——API 路由由首次 activate 事务接入）"
echo "  下一步：MAAS_DEPLOY_MODE=release ops/deploy-release.sh --commit <approved-sha>"
echo "  （通道经运行时环境变量注入；仓库 ops/deploy-mode 永久保持 legacy）"
