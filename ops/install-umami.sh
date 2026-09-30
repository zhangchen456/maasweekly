#!/usr/bin/env bash
# install-umami.sh：Umami Analytics + PostgreSQL 独立幂等安装（T08-1A Gate A 候选）
#
# ⚠️ 授权边界：本脚本属于 T08-1A Gate B「待执行配置」。Gate A 验收通过前
# 【不得执行】——执行它会修改服务器 systemd/nginx/用户/目录/PostgreSQL。
#
# 设计约束（对齐 ops/install-production.sh）：
#   - 幂等：重复执行不破坏已就位状态（先检查再变更）；nginx 改造失败自动回滚
#   - 可审查：每个动作对应 install-umami.sh 的 run() 步骤（--dry-run 可预览）
#   - 最小面：只创建 Umami 专用用户/目录/systemd/nginx/PostgreSQL；
#     不切换流量、不修改 daily.maas.click 主站配置、不影响 agent-api
#   - 不落 secret 进仓库/日志：APP_SECRET/DB password 由本脚本在服务器现场生成
#
# Umami v3.4.0（MIT License，github.com/umami-software/umami）从源码部署：
#   git clone --branch v3.4.0 --depth 1 → pnpm install → pnpm run build → next start
# build 步骤自动建表（prisma migrate）并创建默认 admin/umami 用户。
#
# 用法（root，在服务器上执行）：
#   ops/install-umami.sh --dry-run    # 只打印将执行的动作
#   ops/install-umami.sh             # 真实执行
set -euo pipefail

OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
case "$OPS_DIR" in
  */ops) : ;;
  *) echo "✗ 必须从 ops/ 下执行（当前: ${OPS_DIR}）" >&2; exit 2 ;;
esac

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# ---- 布局常量（对齐 install-production.sh 的 RELEASE_ROOT 约定）----
RELEASE_ROOT=/srv/maasweekly
UMAMI_DIR=$RELEASE_ROOT/umami
UMAMI_VERSION="v3.4.0"
UMAMI_REPO="https://github.com/umami-software/umami.git"
SERVICE_USER=maasumami
SHARED_DIR=$RELEASE_ROOT/shared
UMAMI_ENV=$SHARED_DIR/umami.env
SERVICE_SRC="$OPS_DIR/maas-umami.service"
ENV_EXAMPLE_SRC="$OPS_DIR/maas-umami.env.example"
NGINX_SRC="$OPS_DIR/nginx/maasweekly-umami.conf"
NGINX_CONF_D=/etc/nginx/conf.d
NGINX_DST=$NGINX_CONF_D/maasweekly-umami.conf
NGINX_HTTPS_CONF=/etc/nginx/snippets/maasweekly-https.conf

# PostgreSQL
PG_DB=maas_analytics
PG_USER=maas_umami
PG_BIN=/usr/bin/psql

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

echo "== T08-1A Umami Analytics 安装（Gate B 授权后执行；dry-run: ${DRY_RUN}） =="

# ---- 0. preflight ----
run "检查 node 22" "command -v node && \$(node --version | grep -q '^v22' || { echo '需要 Node 22'; exit 1; })"
run "检查 pnpm" "command -v pnpm || { echo '需要 pnpm（npm i -g pnpm@12.3.4）'; exit 1; }"
run "检查 postgresql" "command -v postgres || { echo '需要 PostgreSQL v12.14+'; exit 1; }"
run "检查 psql" "command -v $PG_BIN"
run "检查 nginx" "command -v nginx"
run "检查磁盘剩余 >1GB（GNU df，服务器 Linux）" \
  'avail=$(df -BG --output=avail / | tail -1 | tr -dc "0-9"); [ "$avail" -ge 1 ] || { echo "磁盘不足 1GB"; exit 1; }'

# ---- 1. 创建服务用户 ----
run "创建 ${SERVICE_USER}（无 login shell）" \
  "id $SERVICE_USER >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin $SERVICE_USER"

# ---- 2. 创建 Umami 应用目录 ----
run "创建 Umami 应用目录 ${UMAMI_DIR}" \
  "mkdir -p $UMAMI_DIR && chown $SERVICE_USER:$SERVICE_USER $UMAMI_DIR"

# ---- 3. git clone Umami v3.4.0 + pnpm install + pnpm run build ----
# 幂等：目录已存在且 .git 存在则跳过 clone（不覆盖已有 build 产物）
if [ -d "$UMAMI_DIR/.git" ]; then
  echo "· Umami 已存在（跳过 clone）；当前版本：$(cd $UMAMI_DIR && git describe --tags 2>/dev/null || echo unknown)"
else
  run "git clone Umami ${UMAMI_VERSION}" \
    "git clone --branch $UMAMI_VERSION --depth 1 $UMAMI_REPO $UMAMI_DIR"
  run "pnpm install（Umami 依赖）" \
    "cd $UMAMI_DIR && pnpm install --frozen-lockfile"
  run "pnpm run build（含 prisma 自动建表；首次需 DATABASE_URL）" \
    "cd $UMAMI_DIR && pnpm run build"
fi

# ---- 4. PostgreSQL database + user provisioning ----
# 幂等：database/user 已存在则跳过（不重置密码、不删除数据）
run "确认 PostgreSQL 运行" "systemctl is-active --quiet postgresql || systemctl start postgresql"

# 检查 database 是否已存在
DB_EXISTS="$(sudo -u postgres $PG_BIN -tAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" 2>/dev/null || echo '')"
if [ "$DB_EXISTS" = "1" ]; then
  echo "· database $PG_DB 已存在（跳过创建，保留数据）"
else
  run "创建 database $PG_DB" \
    "sudo -u postgres $PG_BIN -c \"CREATE DATABASE $PG_DB OWNER $PG_USER\" || sudo -u postgres createdb -O $PG_USER $PG_DB"
fi

# 检查 user 是否已存在（不重置密码）
USER_EXISTS="$(sudo -u postgres $PG_BIN -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'" 2>/dev/null || echo '')"
if [ "$USER_EXISTS" = "1" ]; then
  echo "· user $PG_USER 已存在（跳过创建，保留密码）"
else
  run "创建 user $PG_USER（密码现场生成）" \
    "sudo -u postgres $PG_BIN -c \"CREATE USER $PG_USER WITH ENCRYPTED PASSWORD '\$(openssl rand -hex 24)'\""
  run "授予 $PG_USER 对 $PG_DB 全部权限" \
    "sudo -u postgres $PG_BIN -d $PG_DB -c \"GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER\""
fi

# ---- 5. 生成 umami.env（若不存在；含现场生成的 APP_SECRET + DB password）----
# 幂等：umami.env 已存在则保留（不覆盖已有 secret），除非显式 --rotate
run "创建 shared 目录（若不存在）" "mkdir -p $SHARED_DIR"

if [ -f "$UMAMI_ENV" ]; then
  echo "· $UMAMI_ENV 已存在（保留既有 secret；如需轮换用 --rotate，本任务不实现）"
else
  echo "· 生成 $UMAMI_ENV（含现场生成的 APP_SECRET + DB password）"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] openssl rand -hex 32 → APP_SECRET；从 PostgreSQL 读取或重置 DB password"
  else
    # 从 PostgreSQL 读取已有 user 的密码是不可逆的（密码哈希不可解密）；
    # 首次创建时密码已设；若 umami.env 不存在但 user 已存在，需重置密码
    DB_PASS="$(openssl rand -hex 24)"
    sudo -u postgres $PG_BIN -c "ALTER USER $PG_USER WITH ENCRYPTED PASSWORD '$DB_PASS'"
    APP_SECRET="$(openssl rand -hex 32)"
    cat > "$UMAMI_ENV" <<EOF
HOSTNAME=127.0.0.1
PORT=3000
DATABASE_URL=postgresql://${PG_USER}:${DB_PASS}@localhost:5432/${PG_DB}
APP_SECRET=${APP_SECRET}
EOF
    chown root:$SERVICE_USER "$UMAMI_ENV"
    chmod 0740 "$UMAMI_ENV"
    echo "  ✓ $UMAMI_ENV 生成（0740 root:$SERVICE_USER）"
  fi
fi

# ---- 6. 安装 systemd service ----
run "安装 maas-umami.service → /etc/systemd/system" \
  "install -m 0644 '$SERVICE_SRC' /etc/systemd/system/maas-umami.service && systemctl daemon-reload"

# ---- 7. 安装 nginx config（独立 subdomain server block）----
# 幂等：已存在则跳过（不覆盖；由本脚本版本管理）
run "安装 Umami nginx config → $NGINX_DST" \
  "install -m 0644 '$NGINX_SRC' '$NGINX_DST'"

# ---- 8. validate（nginx -t；不 reload——Gate B owner 授权后才 reload）----
# 注意：TLS 证书可能尚未配置（owner Gate B prerequisite），nginx -t 可能因
# ssl_certificate 缺失而失败。Gate B 执行时 owner 先配 certbot 证书，再 nginx -t。
if [ "$DRY_RUN" = "1" ]; then
  echo "· [dry-run] nginx -t（Gate B owner 配置证书后执行）"
else
  echo "· nginx -t（若证书未配置会失败——owner Gate B 先配 certbot）"
  if ! nginx -t 2>&1; then
    echo "✗ nginx -t 失败（可能是 TLS 证书未配置——owner Gate B prerequisite）" >&2
    echo "  Gate B 流程：1) certbot certonly -d analytics.maas.click；2) 取消注释 maasweekly-umami.conf 的 ssl_certificate 行；3) nginx -t；4) nginx -s reload" >&2
    exit 1
  fi
fi

# ---- 9. enable/start（Gate B owner 授权后才执行）----
echo "· enable + start（Gate B owner 授权后执行）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] systemctl enable --now maas-umami.service"
else
  echo "  ⚠ Gate B：确认证书已配置 + nginx -t 通过后执行："
  echo "    systemctl enable --now maas-umami.service"
  echo "    systemctl status maas-umami.service"
  echo "    curl -sf http://127.0.0.1:3000/api/heartbeat  # Umami 官方 health endpoint"
fi

# ---- 10. 完成检查 ----
echo "== 安装清单（完成后核对） =="
cat <<EOF
  /etc/systemd/system/maas-umami.service               (0644)
  /srv/maasweekly/umami/                                (0755, $SERVICE_USER，git clone $UMAMI_VERSION)
  /srv/maasweekly/shared/umami.env                      (0740 root:$SERVICE_USER，含 APP_SECRET + DB password)
  $NGINX_DST                       (0644, analytics.maas.click subdomain server block)
  PostgreSQL: database=$PG_DB user=$PG_USER（密码在 umami.env）

  ⚠ OWNER ACTION REQUIRED（Gate B prerequisite）：
    1. DNS：analytics.maas.click → 47.237.135.97
    2. TLS：certbot certonly -d analytics.maas.click
    3. 取消注释 $NGINX_DST 的 ssl_certificate/ssl_certificate_key 行
    4. nginx -t && nginx -s reload
    5. systemctl enable --now maas-umami.service
    6. curl http://127.0.0.1:3000/api/heartbeat（验证 Umami 健康）
EOF
echo "✓ T08-1A 安装完成（流量未切换——需 owner Gate B 授权后执行上述步骤）"
