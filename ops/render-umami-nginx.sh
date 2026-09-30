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
#   这样 Production Authorization Package 才能准确标注：
#     Phase 3 = nginx mutation（只 nginx，不碰 DB/source/build/systemd）
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

# ---- 1. 渲染 nginx config（从模板 sed 取消注释 + 填入真实证书路径）----
echo "· 渲染 nginx config（含证书 $CERT_PATH）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] sed 渲染 ssl_certificate 行 → $NGINX_DST"
else
  # 临时文件 + atomic rename（避免中断留下半写文件）
  TMP_NGINX="$(mktemp "${NGINX_DST}.tmp.XXXXXX")"
  sed -e "s|^# ssl_certificate .*|ssl_certificate $CERT_PATH;|" \
      -e "s|^# ssl_certificate_key .*|ssl_certificate_key $KEY_PATH;|" \
      "$NGINX_SRC" > "$TMP_NGINX"
  # 验证渲染结果（ssl_certificate 行非注释）
  if ! grep -q "^ssl_certificate $CERT_PATH;" "$TMP_NGINX"; then
    rm -f "$TMP_NGINX"
    echo "✗ 渲染失败：ssl_certificate 行未正确填入" >&2
    exit 1
  fi
  chmod 0644 "$TMP_NGINX"
  mv -f "$TMP_NGINX" "$NGINX_DST"
  echo "  ✓ 渲染并安装 $NGINX_DST（atomic rename）"
fi

# ---- 2. nginx -t（完整配置，预期通过）----
run "nginx -t（完整配置，预期通过）" "nginx -t"

# ---- 3. nginx -s reload ----
run "nginx -s reload" "nginx -s reload"

# ---- 4. 完成检查 ----
echo "== render-umami-nginx 完成 =="
echo "  ✓ $NGINX_DST 已渲染并安装（含证书 $CERT_PATH）"
echo "  ✓ nginx -t 通过，已 reload"
echo "  ⚠ 本脚本只渲染 nginx config，不碰 PostgreSQL/source/build/systemd"
