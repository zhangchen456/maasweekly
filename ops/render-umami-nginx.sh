#!/usr/bin/env bash
# render-umami-nginx.sh：渲染并安装 Umami Analytics nginx config（T08-1A Gate A 候选）
#
# ⚠️ 授权边界：本脚本属于 T08-1A Gate B「待执行配置」。Gate A 验收通过前
# 【不得执行】——执行它会修改服务器 nginx 配置。
#
# 设计目的（Round 3 P1 修复）：
#   render-nginx 必须是真正独立的 nginx 操作，不得触发 PostgreSQL/source/build/
#   systemd mutation。install-umami.sh 只做 install（不含 render-nginx）；
#   本脚本只渲染 nginx config 并 nginx -t + reload。
#
# Candidate rollback safety（Round 4 P1 修复）：
#   render 失败不能让 /etc/nginx 留在 invalid state。
#   流程：render temp → backup existing → install candidate → nginx -t
#   → 失败则 restore previous → nginx -t 验证恢复 → success 才 reload。
#   若此前无 existing config：candidate validation failure → remove candidate
#   → nginx -t → exit non-zero。
#   reload 只允许发生在 nginx -t success 后。
#
# 用法（root，在服务器上执行）：
#   ops/render-umami-nginx.sh <cert-path> <key-path>    # 渲染并安装 + nginx -t + reload
#   ops/render-umami-nginx.sh --dry-run <cert> <key>     # 只打印
set -euo pipefail

OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
case "$OPS_DIR" in
  */ops) : ;;
  *) echo "✗ 必须从 ops/ 下执行（当前: ${OPS_DIR}）" >&2; exit 2 ;;
esac

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi

CERT_PATH="${1:-}"
KEY_PATH="${2:-}"

[ -n "$CERT_PATH" ] || { echo "用法: $0 [--dry-run] <cert-path> <key-path>" >&2; exit 2; }
[ -n "$KEY_PATH" ] || { echo "用法: $0 [--dry-run] <cert-path> <key-path>" >&2; exit 2; }

NGINX_SRC="$OPS_DIR/nginx/maasweekly-umami.conf"
NGINX_CONF_D=/etc/nginx/conf.d
NGINX_DST=$NGINX_CONF_D/maasweekly-umami.conf

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

echo "== T08-1A render-umami-nginx（dry-run: ${DRY_RUN}） =="

# ---- 0. preflight（只 nginx 相关，不碰 DB/source/build）----
run "检查 nginx" "command -v nginx"
run "检查 nginx 模板存在" "[ -f '$NGINX_SRC' ]"
run "检查证书文件存在" "[ -f '$CERT_PATH' ]"
run "检查密钥文件存在" "[ -f '$KEY_PATH' ]"
run "检查 conf.d 目录" "[ -d '$NGINX_CONF_D' ]"

# ---- 1. 渲染 candidate 到 temp file（不直接覆盖生产）----
echo "· 渲染 candidate nginx config（temp file）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] sed 渲染 → temp file"
  echo "    [dry-run] 验证 candidate 含 ssl_certificate $CERT_PATH;"
else
  CANDIDATE="$(mktemp)"
  sed -e "s|^# ssl_certificate .*|ssl_certificate $CERT_PATH;|" \
      -e "s|^# ssl_certificate_key .*|ssl_certificate_key $KEY_PATH;|" \
      "$NGINX_SRC" > "$CANDIDATE"
  # 验证渲染结果（ssl_certificate 行非注释）
  if ! grep -q "^ssl_certificate $CERT_PATH;" "$CANDIDATE"; then
    rm -f "$CANDIDATE"
    echo "✗ 渲染失败：ssl_certificate 行未正确填入" >&2
    exit 1
  fi
  chmod 0644 "$CANDIDATE"
  echo "  ✓ candidate 渲染完成（temp file）"
fi

# ---- 2. backup existing config（若存在）----
HAD_EXISTING=0
if [ -f "$NGINX_DST" ]; then
  HAD_EXISTING=1
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP="${NGINX_DST}.backup-${TS}"
  echo "· backup existing config → $BACKUP"
  if [ "$DRY_RUN" = "1" ]; then
    echo "    [dry-run] cp -a $NGINX_DST $BACKUP"
  else
    cp -a "$NGINX_DST" "$BACKUP"
    echo "  ✓ existing config 已备份"
  fi
else
  echo "· 无 existing config（首次安装）"
fi

# ---- 3. install candidate → /etc/nginx/conf.d/----
echo "· install candidate → $NGINX_DST"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] mv candidate → $NGINX_DST"
else
  mv -f "$CANDIDATE" "$NGINX_DST"
fi

# ---- 4. nginx -t（验证 candidate）----
echo "· nginx -t（验证 candidate 配置）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] nginx -t"
else
  if ! nginx -t 2>&1; then
    echo "✗ nginx -t 失败（candidate 配置无效）" >&2
    # ---- 5. rollback：restore previous config 或 remove candidate ----
    if [ "$HAD_EXISTING" = "1" ]; then
      echo "· rollback：restore previous config from $BACKUP"
      mv -f "$BACKUP" "$NGINX_DST"
      echo "  ✓ previous config 已恢复"
      # nginx -t 验证恢复
      echo "· nginx -t（验证恢复后的配置）"
      if ! nginx -t 2>&1; then
        echo "✗✗ 严重：恢复后的配置也无效！/etc/nginx 可能处于 invalid state" >&2
        echo "  人工诊断：$NGINX_DST（已恢复 backup，但 backup 可能也无效）" >&2
        exit 1
      fi
      echo "  ✓ 恢复后 nginx -t 通过（生产配置已恢复到变更前状态）"
    else
      echo "· rollback：remove candidate（首次安装，无 previous config）"
      rm -f "$NGINX_DST"
      echo "  ✓ candidate 已移除"
      # nginx -t 验证（不应因移除 candidate 而失败）
      echo "· nginx -t（验证移除 candidate 后的配置）"
      if ! nginx -t 2>&1; then
        echo "✗✗ 严重：移除 candidate 后配置仍无效！/etc/nginx 可能已有其他问题" >&2
        echo "  人工诊断：$NGINX_DST 已移除，但 nginx 其他配置可能有问题" >&2
        exit 1
      fi
      echo "  ✓ 移除 candidate 后 nginx -t 通过"
    fi
    echo "✗ render-umami-nginx 失败：candidate 配置无效，已 rollback" >&2
    exit 1
  fi
  echo "  ✓ nginx -t 通过（candidate 配置有效）"
fi

# ---- 6. reload（只在 nginx -t success 后）----
echo "· nginx -s reload（只在 nginx -t success 后）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] nginx -s reload"
else
  nginx -s reload
  echo "  ✓ nginx 已 reload"
fi

# ---- 7. 清理 backup（成功后）----
if [ "$HAD_EXISTING" = "1" ] && [ -f "$BACKUP" ] && [ "$DRY_RUN" != "1" ]; then
  rm -f "$BACKUP"
  echo "  ✓ backup 已清理（成功安装后）"
fi

# ---- 8. 完成检查 ----
echo "== render-umami-nginx 完成 =="
echo "  ✓ $NGINX_DST 已渲染并安装（含证书 $CERT_PATH）"
echo "  ✓ nginx -t 通过，已 reload"
echo "  ⚠ 本脚本只渲染 nginx config，不碰 PostgreSQL/source/build/systemd"
echo "  ⚠ candidate rollback safety：nginx -t 失败时自动 restore/remove，不留 invalid state"
