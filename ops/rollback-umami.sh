#!/usr/bin/env bash
# rollback-umami.sh：Umami Analytics 回滚（T08-1A Gate A 候选）
#
# ⚠️ 授权边界：本脚本属于 T08-1A Gate B「待执行配置」。Gate A 验收通过前
# 【不得执行】——执行它会停止 Umami 服务并回滚 nginx 配置。
#
# 回滚边界（对齐任务书 §18）：
#   - 停止并 disable Umami systemd service
#   - 移除 nginx Umami subdomain config（备份后移除）
#   - nginx -t + reload（恢复到无 Umami 状态）
#   - 保留 umami.env（不删除 secret）
#   - 保留 Umami 应用目录 /srv/maasweekly/umami（不删除应用）
#   - 【禁止】DROP DATABASE / rm -rf database / 删除 Analytics 历史
#   - PostgreSQL 数据默认不删除（除非显式 --purge-data，本任务不实现）
#
# 回滚后状态：
#   - daily.maas.click 主站正常（不受影响）
#   - agent-api 正常（不受影响）
#   - analytics.maas.click 返回 502（Umami 已停）或 444（server block 已移除）
#
# 用法（root，在服务器上执行）：
#   ops/rollback-umami.sh --dry-run    # 只打印将执行的动作
#   ops/rollback-umami.sh              # 真实执行（停服务 + 移除 nginx config）
set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

SERVICE_NAME=maas-umami.service
NGINX_CONF_D=/etc/nginx/conf.d
NGINX_DST=$NGINX_CONF_D/maasweekly-umami.conf
UMAMI_ENV=/srv/maasweekly/shared/umami.env
UMAMI_DIR=/srv/maasweekly/umami
PG_DB=maas_analytics
PG_USER=maas_umami

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

echo "== T08-1A Umami Analytics 回滚（dry-run: ${DRY_RUN}） =="

# ---- 1. 停止并 disable Umami service ----
run "停止 ${SERVICE_NAME}（若运行中）" \
  "systemctl stop $SERVICE_NAME 2>/dev/null || true"
run "disable ${SERVICE_NAME}" \
  "systemctl disable $SERVICE_NAME 2>/dev/null || true"

# ---- 2. 备份并移除 nginx config ----
if [ -f "$NGINX_DST" ]; then
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP="${NGINX_DST}.rollback-${TS}"
  run "备份 nginx config → $BACKUP" "cp -a '$NGINX_DST' '$BACKUP'"
  run "移除 nginx config $NGINX_DST" "rm -f '$NGINX_DST'"
else
  echo "· $NGINX_DST 不存在（跳过移除）"
fi

# ---- 3. nginx -t + reload ----
run "nginx -t（校验移除后配置）" "nginx -t"
run "nginx -s reload" "nginx -s reload"

# ---- 4. 保留项（明确不删除）----
echo "· 保留项（回滚不删除）："
echo "    - $UMAMI_ENV（保留 secret，便于重新启用）"
echo "    - $UMAMI_DIR（保留 Umami 应用 + build 产物）"
echo "    - PostgreSQL database $PG_DB（保留 Analytics 数据）"
echo "    - PostgreSQL user $PG_USER（保留）"

# ---- 5. 完成检查 ----
echo "== 回滚完成 =="
echo "  ⚠ PostgreSQL 数据已保留（不删除）"
echo "  ⚠ Umami 应用 + env 已保留（便于重新启用）"
echo "  ⚠ daily.maas.click 主站与 agent-api 不受影响"
echo "  ⚠ rollback contract：数据永远保留，不提供 destructive cleanup 命令"
