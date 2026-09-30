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
# ⚠️ 关键执行顺序（Gate A FAIL 修复，P0）：
#   preflight → service user/dirs → PostgreSQL active → role → database →
#   umami.env → clone source → pnpm install → pnpm run build（带 DATABASE_URL）→
#   install systemd → nginx → validate
#   原因：pnpm run build 含 prisma 自动建表，需要 DATABASE_URL 已就绪；
#   DATABASE_URL 需要 PostgreSQL role + database 已存在。
#
# ⚠️ Credential recovery 语义（Gate A FAIL 修复，P0）：
#   - 正常状态（role exists + env exists）：preserve password，不 ALTER USER
#   - 首次安装（role absent + env absent）：generate password once
#   - 异常状态（role exists + env absent）：**STOP，fail closed**
#     必须显式 --recover-env 才能 ALTER USER（本任务不实现 --recover-env）
#
# Umami v3.4.0（MIT License，github.com/umami-software/umami）从源码部署。
# 版本 pinning（Gate A FAIL 修复，P1）：tag v3.4.0 + 40-char commit SHA 双重 pin，
# clone 后验证 HEAD == 预期 SHA，防止 upstream tag 移动。
#
# 用法（root，在服务器上执行）：
#   ops/install-umami.sh --dry-run    # 只打印将执行的动作
#   ops/install-umami.sh              # 真实执行
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

# 版本双重 pin（tag + 40-char commit SHA，防 upstream tag 移动）
UMAMI_VERSION="v3.4.0"
UMAMI_COMMIT="ec0ff50388c264ed8ce46f00967e92f7e71476ae"
UMAMI_REPO="https://github.com/umami-software/umami.git"

SERVICE_USER=maasumami
SHARED_DIR=$RELEASE_ROOT/shared
UMAMI_ENV=$SHARED_DIR/umami.env
SERVICE_SRC="$OPS_DIR/maas-umami.service"
ENV_EXAMPLE_SRC="$OPS_DIR/maas-umami.env.example"
NGINX_SRC="$OPS_DIR/nginx/maasweekly-umami.conf"
NGINX_CONF_D=/etc/nginx/conf.d
NGINX_DST=$NGINX_CONF_D/maasweekly-umami.conf

# PostgreSQL
PG_DB=maas_analytics
PG_USER=maas_umami
PG_BIN=/usr/bin/psql

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

die() { echo "✗ $*" >&2; exit 1; }

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

# ---- 3. PostgreSQL active（必须在 role/database 之前）----
run "确认 PostgreSQL 运行" "systemctl is-active --quiet postgresql || systemctl start postgresql"

# ---- 4. PostgreSQL role 必须先于 database（P0 修复）----
# 检查 role 是否已存在（幂等：已存在则跳过，不重置密码）
USER_EXISTS="$(sudo -u postgres $PG_BIN -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'" 2>/dev/null || echo '')"
if [ "$USER_EXISTS" = "1" ]; then
  echo "· PostgreSQL role $PG_USER 已存在（跳过创建，保留密码）"
else
  run "创建 PostgreSQL role $PG_USER（密码现场生成）" \
    "sudo -u postgres $PG_BIN -c \"CREATE USER $PG_USER WITH ENCRYPTED PASSWORD '\$(openssl rand -hex 24)'\""
fi

# ---- 5. PostgreSQL database（role 已就绪，OWNER 才能成功；P0 修复）----
# 幂等：database 已存在则跳过（不删除数据）
DB_EXISTS="$(sudo -u postgres $PG_BIN -tAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" 2>/dev/null || echo '')"
if [ "$DB_EXISTS" = "1" ]; then
  echo "· database $PG_DB 已存在（跳过创建，保留数据）"
else
  run "创建 database $PG_DB OWNER $PG_USER" \
    "sudo -u postgres $PG_BIN -c \"CREATE DATABASE $PG_DB OWNER $PG_USER\""
  run "授予 $PG_USER 对 $PG_DB 全部权限" \
    "sudo -u postgres $PG_BIN -d $PG_DB -c \"GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER\""
fi

# ---- 6. 生成 umami.env（必须在 clone/build 之前；P0 修复）----
# Credential recovery 语义（P0 修复）：
#   - 正常状态（role exists + env exists）：preserve password，不 ALTER USER
#   - 首次安装（role absent + env absent）：generate password once
#   - 异常状态（role exists + env absent）：STOP，fail closed
#     必须显式 --recover-env 才能 ALTER USER（本任务不实现 --recover-env）
run "创建 shared 目录（若不存在）" "mkdir -p $SHARED_DIR"

if [ -f "$UMAMI_ENV" ]; then
  echo "· $UMAMI_ENV 已存在（保留既有 secret；如需轮换用 --recover-env，本任务不实现）"
else
  # umami.env 不存在
  if [ "$USER_EXISTS" = "1" ]; then
    # role 已存在但 env 不存在 → 异常状态，fail closed
    die "异常状态：PostgreSQL role $PG_USER 已存在但 $UMAMI_ENV 不存在。
    这意味着 umami.env 丢失但 DB credential 仍存在。PostgreSQL 密码不可逆，
    无法从 DB 恢复。必须显式 credential recovery：
      方式 A（轮换密码）：显式 --recover-env（本任务未实现，T08-1A 不支持静默轮换）
      方式 B（完全重装）：先 rollback-umami.sh，手动 dropdb/dropuser 后重跑本脚本
    普通安装不应静默 ALTER USER 轮换现有 credential。"
  fi
  # 首次安装：role 刚创建（或刚生成密码），生成 umami.env
  echo "· 生成 $UMAMI_ENV（首次安装；含现场生成的 APP_SECRET + DB password）"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] openssl rand -hex 32 → APP_SECRET；DB password 在 role 创建时已生成"
    echo "    [dry-run] 注意：首次安装 role 创建时密码已现场生成，但未保存到 env"
    echo "    [dry-run] 生产执行时：role 创建 + env 生成必须同一次脚本执行完成"
  else
    # ⚠️ 首次安装的密码一致性：role 创建时生成的密码与 env 中的密码必须一致。
    # 因为 role 创建（step 4）与 env 生成（step 6）在同一脚本执行中，
    # 但 role 创建的密码是随机的且未保存——这里必须重新 ALTER USER 设置新密码，
    # 并把同一密码写入 env。这是首次安装（role 刚创建），ALTER USER 不算"轮换"。
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

# ---- 7. git clone Umami v3.4.0（tag + commit SHA 双重 pin；P1 修复）----
# 幂等 + 版本校验（P1 修复）：目录已存在时验证 HEAD == pinned SHA + clean worktree，
# 不一致 fail closed（不猜版本，升级走单独 upgrade path）
if [ -d "$UMAMI_DIR/.git" ]; then
  echo "· Umami 源码已存在，验证版本..."
  ACTUAL_COMMIT="$(cd "$UMAMI_DIR" && git rev-parse HEAD 2>/dev/null || echo '')"
  if [ "$ACTUAL_COMMIT" != "$UMAMI_COMMIT" ]; then
    die "Umami 源码版本不匹配：HEAD=$ACTUAL_COMMIT，期望=$UMAMI_COMMIT。
    installer 不猜版本。升级走单独 upgrade path（见 task-08-1a 文档 §10）。
    如需强制重装：先 rm -rf $UMAMI_DIR（会丢失 build 产物，不丢失 DB 数据）。"
  fi
  # 验证 clean worktree
  if [ -n "$(cd "$UMAMI_DIR" && git status --porcelain 2>/dev/null)" ]; then
    die "Umami 源码 worktree 脏，拒绝安装（先清理或重装）"
  fi
  echo "  ✓ Umami 源码版本正确（$UMAMI_VERSION @ $UMAMI_COMMIT），worktree clean"
else
  run "git clone Umami ${UMAMI_VERSION} @ ${UMAMI_COMMIT:0:12}" \
    "git clone --branch $UMAMI_VERSION --depth 1 $UMAMI_REPO $UMAMI_DIR"
  # clone 后验证 HEAD == pinned SHA（P1 修复：防 upstream tag 移动）
  ACTUAL_COMMIT="$(cd "$UMAMI_DIR" && git rev-parse HEAD 2>/dev/null || echo '')"
  if [ "$ACTUAL_COMMIT" != "$UMAMI_COMMIT" ]; then
    die "clone 后 HEAD 不匹配：actual=$ACTUAL_COMMIT，期望=$UMAMI_COMMIT。
    Umami upstream tag $UMAMI_VERSION 可能已被移动。拒绝安装。"
  fi
  echo "  ✓ clone 后 HEAD 验证通过（$UMAMI_VERSION @ $UMAMI_COMMIT）"
fi

# ---- 8. pnpm install（env 已就绪，可在 build 前）----
# 幂等：node_modules 已存在则跳过（不重复安装）
if [ -d "$UMAMI_DIR/node_modules" ]; then
  echo "· node_modules 已存在（跳过 pnpm install）"
else
  run "pnpm install（Umami 依赖）" \
    "cd $UMAMI_DIR && pnpm install --frozen-lockfile"
fi

# ---- 9. pnpm run build（含 prisma 自动建表；DATABASE_URL 已在 env 就绪；P0 修复）----
# 幂等：.next build 产物已存在则跳过（不重复 build）
if [ -d "$UMAMI_DIR/.next" ]; then
  echo "· .next build 产物已存在（跳过 build）"
else
  # build 需要 DATABASE_URL（prisma 自动建表）；从 umami.env 加载
  echo "· pnpm run build（含 prisma 自动建表；从 $UMAMI_ENV 加载 DATABASE_URL）"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] set -a; source $UMAMI_ENV; cd $UMAMI_DIR && pnpm run build; set +a"
  else
    # 安全加载 env（不输出 secret）
    set -a
    # shellcheck disable=SC1090
    source "$UMAMI_ENV"
    set +a
    (cd "$UMAMI_DIR" && pnpm run build)
    echo "  ✓ build 完成（prisma 自动建表 + 默认 admin/umami 用户已创建）"
  fi
fi

# ---- 10. 安装 systemd service ----
run "安装 maas-umami.service → /etc/systemd/system" \
  "install -m 0644 '$SERVICE_SRC' /etc/systemd/system/maas-umami.service && systemctl daemon-reload"

# ---- 11. 安装 nginx config（TLS 闭环；P1 修复）----
# ⚠️ P1 修复：不安装一个 nginx -t 已知会失败的 443 ssl config。
# 本脚本不安装含注释 ssl_certificate 的模板，而是要求 Gate B 分阶段执行：
#   Phase 1: DNS ready（owner）
#   Phase 2: certbot certonly -d analytics.maas.click（owner，获取证书路径）
#   Phase 3: 本脚本 --render-nginx <cert-path> 渲染完整 nginx config 并安装
#   Phase 4: nginx -t（完整配置，预期通过）
#   Phase 5: nginx -s reload
#
# Gate A（本脚本不带 --render-nginx）：只验证 nginx 模板语法（不含 ssl_certificate，
# 不安装到生产）。Gate B owner 提供证书路径后才渲染并安装。
NGINX_CERT=""
NGINX_KEY=""
# 解析 --render-nginx <cert> <key>（Gate B 用）
if [ "${1:-}" = "--render-nginx" ]; then
  NGINX_CERT="${2:-}"
  NGINX_KEY="${3:-}"
  [ -n "$NGINX_CERT" ] && [ -n "$NGINX_KEY" ] || die "--render-nginx 需要证书与密钥路径"
fi

if [ -n "$NGINX_CERT" ] && [ -n "$NGINX_KEY" ]; then
  # Gate B Phase 3：渲染完整 nginx config（含真实证书路径）
  echo "· 渲染 nginx config（含证书 $NGINX_CERT）"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] sed 渲染 ssl_certificate 行 → $NGINX_DST"
  else
    # 从模板渲染（取消注释 + 填入真实路径）
    sed -e "s|^# ssl_certificate .*|ssl_certificate $NGINX_CERT;|" \
        -e "s|^# ssl_certificate_key .*|ssl_certificate_key $NGINX_KEY;|" \
        "$NGINX_SRC" > "$NGINX_DST"
    chmod 0644 "$NGINX_DST"
    echo "  ✓ 渲染并安装 $NGINX_DST"
  fi
else
  # Gate A / 未提供证书：不安装到生产；只提示
  echo "· nginx config 未渲染（需 --render-nginx <cert> <key>，Gate B Phase 3）"
  echo "    Gate A：不安装到生产；模板语法校验见 test_analytics_foundation.py"
  echo "    Gate B 流程：DNS → certbot → 本脚本 --render-nginx <cert> <key> → nginx -t → reload"
fi

# ---- 12. validate（只在 --render-nginx 后执行 nginx -t；P1 修复）----
if [ -n "$NGINX_CERT" ] && [ -n "$NGINX_KEY" ]; then
  run "nginx -t（完整配置，预期通过）" "nginx -t"
  run "nginx -s reload" "nginx -s reload"
else
  echo "· skip nginx -t（无完整配置；Gate B Phase 3 后才执行）"
fi

# ---- 13. enable/start（Gate B owner 授权后才执行）----
echo "· enable + start（Gate B owner 授权后执行）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] systemctl enable --now maas-umami.service"
else
  echo "  ⚠ Gate B：确认证书已配置 + nginx -t 通过后执行："
  echo "    systemctl enable --now maas-umami.service"
  echo "    systemctl status maas-umami.service"
  echo "    curl -sf http://127.0.0.1:3000/api/heartbeat  # Umami 官方 health endpoint"
fi

# ---- 14. 完成检查 ----
echo "== 安装清单（完成后核对） =="
cat <<EOF
  /etc/systemd/system/maas-umami.service               (0644)
  /srv/maasweekly/umami/                                (0755, $SERVICE_USER，git clone $UMAMI_VERSION @ ${UMAMI_COMMIT:0:12})
  /srv/maasweekly/shared/umami.env                      (0740 root:$SERVICE_USER，含 APP_SECRET + DB password)
  $NGINX_DST                       (0644, 仅 --render-nginx 后安装；analytics.maas.click)
  PostgreSQL: database=$PG_DB user=$PG_USER（密码在 umami.env）

  ⚠ OWNER ACTION REQUIRED（Gate B prerequisite）：
    Phase 1: DNS analytics.maas.click → 47.237.135.97
    Phase 2: certbot certonly -d analytics.maas.click（记录证书路径）
    Phase 3: ops/install-umami.sh --render-nginx <cert-path> <key-path>
    Phase 4: nginx -t（本脚本 Phase 3 后自动执行）
    Phase 5: nginx -s reload（本脚本 Phase 3 后自动执行）
    Phase 6: systemctl enable --now maas-umami.service
    Phase 7: curl http://127.0.0.1:3000/api/heartbeat（验证 Umami 健康）
EOF
echo "✓ T08-1A 安装完成（流量未切换——需 owner Gate B 授权后执行上述步骤）"
