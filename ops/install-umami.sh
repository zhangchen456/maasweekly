#!/usr/bin/env bash
# install-umami.sh：Umami Analytics + PostgreSQL 独立幂等安装（T08-1A Gate A 候选）
#
# ⚠️ 授权边界：本脚本属于 T08-1A Gate B「待执行配置」。Gate A 验收通过前
# 【不得执行】——执行它会修改服务器 systemd/nginx/用户/目录/PostgreSQL。
#
# ⚠️ 关键设计（Gate A Round 3 修复——显式四态状态机）：
#   credential 状态必须在任何 mutation 之前显式检测，不靠过期快照变量推断。
#   四态：
#     A. role absent + env absent  → fresh install（generate credential once）
#     B. role exists + env exists  → existing healthy（preserve）
#     C. role exists + env absent  → fail closed（STOP，不自动 rotate）
#     D. role absent + env exists  → fail closed（STOP，inconsistent）
#   C/D 检测发生在任何 CREATE USER / CREATE DATABASE / chown / clone 之前。
#
# ⚠️ Fresh install credential lifecycle（Round 3 修复）：
#   DB_PASS 只生成一次；CREATE ROLE 直接使用该 DB_PASS；同一个 DB_PASS 写入
#   umami.env。不再 CREATE 后 ALTER USER（消除中断窗口）。
#   env 使用 temp file + chmod/chown + atomic rename，避免中断留下半写文件。
#
# ⚠️ build 幂等（Round 3 修复）：
#   不以 .next exists 判断 build 成功（.next 可能是中途失败的半成品）。
#   采用可证明与 pinned SHA 对应的 build strategy：每次明确 pnpm install +
#   pnpm run build（重复执行多花时间，比错误认为"已 build 完"安全）。
#
# ⚠️ render-nginx 已拆为独立脚本 render-umami-nginx.sh（Round 3 修复）：
#   render nginx 不得触发 PostgreSQL/source/build/systemd mutation。
#   本脚本只做 install（不含 render-nginx）。
#
# Umami v3.4.0（MIT License，github.com/umami-software/umami）从源码部署。
# 版本双重 pin（tag + 40-char commit SHA，防 upstream tag 移动）。
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

# 版本双重 pin（tag + 40-char commit SHA，防 upstream tag 移动）
UMAMI_VERSION="v3.4.0"
UMAMI_COMMIT="ec0ff50388c264ed8ce46f00967e92f7e71476ae"
UMAMI_REPO="https://github.com/umami-software/umami.git"

SERVICE_USER=maasumami
SHARED_DIR=$RELEASE_ROOT/shared
UMAMI_ENV=$SHARED_DIR/umami.env
SERVICE_SRC="$OPS_DIR/maas-umami.service"
ENV_EXAMPLE_SRC="$OPS_DIR/maas-umami.env.example"

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

# ---- 0. preflight（工具检查，不 mutation）----
run "检查 node 22" "command -v node && \$(node --version | grep -q '^v22' || { echo '需要 Node 22'; exit 1; })"
run "检查 pnpm" "command -v pnpm || { echo '需要 pnpm（npm i -g pnpm@12.3.4）'; exit 1; }"
run "检查 postgresql" "command -v postgres || { echo '需要 PostgreSQL v12.14+'; exit 1; }"
run "检查 psql" "command -v $PG_BIN"
run "检查 nginx" "command -v nginx"
run "检查磁盘剩余 >1GB（GNU df，服务器 Linux）" \
  'avail=$(df -BG --output=avail / | tail -1 | tr -dc "0-9"); [ "$avail" -ge 1 ] || { echo "磁盘不足 1GB"; exit 1; }'

# ---- 1. PostgreSQL active（在状态检测之前）----
run "确认 PostgreSQL 运行" "systemctl is-active --quiet postgresql || systemctl start postgresql"

# ============================================================
# 2. CREDENTIAL 状态机预检（Round 3 P0 修复）
#    必须在任何 PostgreSQL/user/database/source mutation 之前。
#    显式四态：A fresh / B existing / C fail closed / D fail closed
# ============================================================
echo "· credential 状态预检（四态状态机）"

ROLE_EXISTS=0
ENV_EXISTS=0
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] 检测 role $PG_USER 与 $UMAMI_ENV 状态"
  # dry-run 假设 fresh install（状态 A）
  echo "    [dry-run] 假设状态 A（fresh install）"
else
  if sudo -u postgres $PG_BIN -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER'" 2>/dev/null | grep -q 1; then
    ROLE_EXISTS=1
  fi
  if [ -f "$UMAMI_ENV" ]; then
    ENV_EXISTS=1
  fi
fi

echo "  · role $PG_USER exists=$ROLE_EXISTS；$UMAMI_ENV exists=$ENV_EXISTS"

# 四态判定（在任何 mutation 之前）
if [ "$ROLE_EXISTS" = "1" ] && [ "$ENV_EXISTS" = "0" ]; then
  # 状态 C：role exists + env absent → fail closed
  die "状态 C（incomplete/recovery）：PostgreSQL role $PG_USER 已存在但 $UMAMI_ENV 不存在。
    这意味着此前安装中断（role 已创建但 env 未生成）或 env 丢失。
    PostgreSQL 密码不可逆，无法从 DB 恢复。
    installer 不自动 rotate credential（避免静默轮换）。
    数据默认保留。需人工诊断：
      - 若需恢复：确认 DB 数据是否需要保留，与 owner 决策 credential recovery 方案
      - installer 不提供 destructive recovery 路径（不 dropdb/dropuser）"
fi

if [ "$ROLE_EXISTS" = "0" ] && [ "$ENV_EXISTS" = "1" ]; then
  # 状态 D：role absent + env exists → fail closed（inconsistent）
  die "状态 D（inconsistent）：$UMAMI_ENV 存在但 PostgreSQL role $PG_USER 不存在。
    这是 inconsistent 状态（env 指向不存在的 role）。
    installer 不自动修复。需人工诊断：
      - 确认 env 是否是残留文件（可备份后删除 env，回到状态 A fresh install）
      - 数据默认保留。installer 不提供 destructive 路径"
fi

# 状态 A（role absent + env absent）→ fresh install
# 状态 B（role exists + env exists）→ existing healthy，preserve
STATE=""
if [ "$ROLE_EXISTS" = "0" ] && [ "$ENV_EXISTS" = "0" ]; then
  STATE="A_fresh"
  echo "  · 状态 A：fresh install（将生成 credential 一次）"
elif [ "$ROLE_EXISTS" = "1" ] && [ "$ENV_EXISTS" = "1" ]; then
  STATE="B_existing"
  echo "  · 状态 B：existing healthy（preserve credential，不 ALTER USER）"
fi

# ============================================================
# 3. 创建服务用户（mutation 开始；状态已预检）
# ============================================================
run "创建 ${SERVICE_USER}（无 login shell）" \
  "id $SERVICE_USER >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin $SERVICE_USER"

# ---- 4. 创建 Umami 应用目录 ----
run "创建 Umami 应用目录 ${UMAMI_DIR}" \
  "mkdir -p $UMAMI_DIR && chown $SERVICE_USER:$SERVICE_USER $UMAMI_DIR"

run "创建 shared 目录（若不存在）" "mkdir -p $SHARED_DIR"

# ============================================================
# 5. Fresh install: 生成 credential 一次 + CREATE ROLE + CREATE DATABASE + env
#    （Round 3 P0 修复：DB_PASS 一次生成，不 CREATE 后 ALTER）
# ============================================================
if [ "$STATE" = "A_fresh" ]; then
  echo "· fresh install：生成 credential 一次"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] DB_PASS=openssl rand -hex 24（一次生成，用于 CREATE ROLE + env）"
    echo "    [dry-run] APP_SECRET=openssl rand -hex 32"
    echo "    [dry-run] CREATE USER $PG_USER WITH ENCRYPTED PASSWORD \$DB_PASS"
    echo "    [dry-run] CREATE DATABASE $PG_DB OWNER $PG_USER"
    echo "    [dry-run] 写临时 env → chmod/chown → atomic rename → $UMAMI_ENV"
  else
    # 生成 credential 一次（DB_PASS 从这里一直活到 role + env 完成）
    DB_PASS="$(openssl rand -hex 24)"
    APP_SECRET="$(openssl rand -hex 32)"

    # CREATE ROLE 直接使用该 DB_PASS（不 CREATE 后 ALTER）
    echo "· CREATE ROLE $PG_USER（使用生成的 DB_PASS）"
    sudo -u postgres $PG_BIN -c "CREATE USER $PG_USER WITH ENCRYPTED PASSWORD '$DB_PASS'"

    # CREATE DATABASE OWNER role（role 已就绪）
    echo "· CREATE DATABASE $PG_DB OWNER $PG_USER"
    sudo -u postgres $PG_BIN -c "CREATE DATABASE $PG_DB OWNER $PG_USER"
    sudo -u postgres $PG_BIN -d "$PG_DB" -c "GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER"

    # 写临时 env → chmod/chown → atomic rename（避免中断留下半写文件）
    echo "· 写 $UMAMI_ENV（temp file → atomic rename）"
    TMP_ENV="$(mktemp "${UMAMI_ENV}.tmp.XXXXXX")"
    cat > "$TMP_ENV" <<EOF
HOSTNAME=127.0.0.1
PORT=3000
DATABASE_URL=postgresql://${PG_USER}:${DB_PASS}@localhost:5432/${PG_DB}
APP_SECRET=${APP_SECRET}
EOF
    chown root:"$SERVICE_USER" "$TMP_ENV"
    chmod 0740 "$TMP_ENV"
    mv -f "$TMP_ENV" "$UMAMI_ENV"
    echo "  ✓ $UMAMI_ENV 生成（0740 root:$SERVICE_USER，atomic rename）"
  fi
elif [ "$STATE" = "B_existing" ]; then
  echo "· existing healthy：preserve credential（不 ALTER USER，不重置密码）"
  echo "  · PostgreSQL role $PG_USER 已存在（跳过 CREATE）"
  # 状态 B：role + env 都存在，只检查 database 是否存在（幂等）
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] 检查 database $PG_DB 是否存在（幂等）"
  else
    DB_EXISTS="$(sudo -u postgres $PG_BIN -tAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" 2>/dev/null || echo '')"
    if [ "$DB_EXISTS" != "1" ]; then
      die "状态 B 异常：role + env 存在但 database $PG_DB 不存在（inconsistent）。
        需人工诊断。installer 不自动 CREATE DATABASE（避免与现有 env 状态不一致）"
    fi
    echo "  · database $PG_DB 已存在（跳过 CREATE，保留数据）"
  fi
fi

# ---- 6. git clone Umami v3.4.0（tag + commit SHA 双重 pin）----
# 幂等 + 版本校验：目录已存在时验证 HEAD == pinned SHA + clean worktree，
# 不一致 fail closed（不猜版本，升级走单独 upgrade path）
if [ -d "$UMAMI_DIR/.git" ]; then
  echo "· Umami 源码已存在，验证版本..."
  ACTUAL_COMMIT="$(cd "$UMAMI_DIR" && git rev-parse HEAD 2>/dev/null || echo '')"
  if [ "$ACTUAL_COMMIT" != "$UMAMI_COMMIT" ]; then
    die "Umami 源码版本不匹配：HEAD=$ACTUAL_COMMIT，期望=$UMAMI_COMMIT。
    installer 不猜版本。升级走单独 upgrade path（见 task-08-1a 文档 §10）。
    如需强制重装：先 rm -rf $UMAMI_DIR（会丢失 build 产物，不丢失 DB 数据）"
  fi
  if [ -n "$(cd "$UMAMI_DIR" && git status --porcelain 2>/dev/null)" ]; then
    die "Umami 源码 worktree 脏，拒绝安装（先清理或重装）"
  fi
  echo "  ✓ Umami 源码版本正确（$UMAMI_VERSION @ $UMAMI_COMMIT），worktree clean"
else
  run "git clone Umami ${UMAMI_VERSION} @ ${UMAMI_COMMIT:0:12}" \
    "git clone --branch $UMAMI_VERSION --depth 1 $UMAMI_REPO $UMAMI_DIR"
  # clone 后验证 HEAD == pinned SHA（防 upstream tag 移动）
  ACTUAL_COMMIT="$(cd "$UMAMI_DIR" && git rev-parse HEAD 2>/dev/null || echo '')"
  if [ "$ACTUAL_COMMIT" != "$UMAMI_COMMIT" ]; then
    die "clone 后 HEAD 不匹配：actual=$ACTUAL_COMMIT，期望=$UMAMI_COMMIT。
    Umami upstream tag $UMAMI_VERSION 可能已被移动。拒绝安装。"
  fi
  echo "  ✓ clone 后 HEAD 验证通过（$UMAMI_VERSION @ $UMAMI_COMMIT）"
fi

# ---- 7. pnpm install（每次明确执行，不靠 node_modules exists 判断）----
# Round 3 P1 修复：不以 node_modules exists 判断（可能是中途失败半成品）
echo "· pnpm install（Umami 依赖；每次明确执行）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] cd $UMAMI_DIR && pnpm install --frozen-lockfile"
else
  (cd "$UMAMI_DIR" && pnpm install --frozen-lockfile)
fi

# ---- 8. pnpm run build（含 prisma 自动建表；DATABASE_URL 已在 env 就绪）----
# Round 3 P1 修复：不以 .next exists 判断 build 成功（.next 可能是中途失败半成品）
# 每次明确 pnpm run build，重复执行多花时间，比错误认为"已 build 完"安全
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

# ---- 9. 安装 systemd service ----
run "安装 maas-umami.service → /etc/systemd/system" \
  "install -m 0644 '$SERVICE_SRC' /etc/systemd/system/maas-umami.service && systemctl daemon-reload"

# ---- 10. nginx config（由独立脚本 render-umami-nginx.sh 渲染；Round 3 P1 修复）----
echo "· nginx config：由独立脚本 ops/render-umami-nginx.sh <cert> <key> 渲染"
echo "    本脚本不渲染 nginx config（职责拆分，避免 render-nginx 触发 DB/build/systemd mutation）"
echo "    Gate B 流程：DNS → certbot → ops/render-umami-nginx.sh <cert> <key> → nginx -t → reload"

# ---- 11. enable/start（Gate B owner 授权后才执行）----
echo "· enable + start（Gate B owner 授权后执行）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] systemctl enable --now maas-umami.service"
else
  echo "  ⚠ Gate B：确认 nginx config 已渲染 + nginx -t 通过后执行："
  echo "    systemctl enable --now maas-umami.service"
  echo "    systemctl status maas-umami.service"
  echo "    curl -sf http://127.0.0.1:3000/api/heartbeat  # Umami 官方 health endpoint"
fi

# ---- 12. 完成检查 ----
echo "== 安装清单（完成后核对） =="
cat <<EOF
  /etc/systemd/system/maas-umami.service               (0644)
  /srv/maasweekly/umami/                                (0755, $SERVICE_USER，git clone $UMAMI_VERSION @ ${UMAMI_COMMIT:0:12})
  /srv/maasweekly/shared/umami.env                      (0740 root:$SERVICE_USER，含 APP_SECRET + DB password)
  PostgreSQL: database=$PG_DB user=$PG_USER（密码在 umami.env）

  ⚠ OWNER ACTION REQUIRED（Gate B prerequisite，分阶段执行）：
    Phase 1: DNS analytics.maas.click → 47.237.135.97
    Phase 2: certbot certonly -d analytics.maas.click（记录证书路径）
    Phase 3: ops/render-umami-nginx.sh <cert-path> <key-path>（独立脚本，只渲染 nginx）
    Phase 4: nginx -t（render-umami-nginx.sh 自动执行）
    Phase 5: nginx -s reload（同上）
    Phase 6: systemctl enable --now maas-umami.service
    Phase 7: curl http://127.0.0.1:3000/api/heartbeat（验证 Umami 健康）

  ⚠ 状态机说明：
    状态 A（role absent + env absent）：fresh install，credential 生成一次
    状态 B（role exists + env exists）：preserve credential，不 ALTER USER
    状态 C（role exists + env absent）：fail closed（STOP，人工诊断）
    状态 D（role absent + env exists）：fail closed（STOP，人工诊断）
EOF
echo "✓ T08-1A 安装完成（流量未切换——需 owner Gate B 授权后执行上述步骤）"
