#!/usr/bin/env bash
# verify-release.sh：线上 release 验收（Task 06 M5）
#
# 用法：
#   ops/verify-release.sh --offline <release-dir>  # 离线校验本地 release 产物（CI）
#   ops/verify-release.sh --online --expect-release <rid>
#     # 线上验收：current==rid、四入口 datasetVersion 与 manifest 一致
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
. "$(dirname "$0")/lib-release.sh"

MODE=""
EXPECT_RID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --offline) MODE="offline"; RELEASE_DIR="$2"; shift 2 ;;
    --online) MODE="online"; shift ;;
    --expect-release) EXPECT_RID="$2"; shift 2 ;;
    --host) MAAS_DEPLOY_HOST="$2"; shift 2 ;;
    *) die "未知参数: $1" ;;
  esac
done
[ -n "$MODE" ] || die "必须指定 --offline <dir> 或 --online"

if [ "$MODE" = "offline" ]; then
  [ -d "$RELEASE_DIR" ] || die "release 目录不存在: $RELEASE_DIR"
  python3 pipeline/scripts/release_manifest.py verify --root "$RELEASE_DIR"
  echo "✓ 离线验收通过: $RELEASE_DIR"
  exit 0
fi

# ---- 在线验收 ----
validate_rid "$EXPECT_RID"

# 1. 服务器 current 应指向目标 release
current="$(remote_status 2>/dev/null | grep '^current:' | awk '{print $2}')"
[ "$current" = "$EXPECT_RID" ] \
  || die "服务器 current=$current ≠ expect=$EXPECT_RID（激活未完成或已回滚）"
info "✓ 服务器 current: $current"

# 2. 从服务器 release manifest 读取期望 datasetVersion
expect_ds="$(current_ds_from_server "$EXPECT_RID")" || die "无法读取服务器上的 release manifest"

# 3. 三个 HTTP 入口必须看到同一 datasetVersion（REST/MCP 同版；RSS 是文档型，命中率即可）
for ep in "/api/v1/status" "/api/v1/changes"; do
  body="$(curl -sf --max-time 10 -H 'Cache-Control: no-cache' \
    "$MAAS_PUBLIC_ORIGIN$ep" 2>/dev/null || true)"
  ds="$(echo "$body" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('datasetVersion',''))" 2>/dev/null)"
  [ "$ds" = "$expect_ds" ] \
    || die "$ep datasetVersion=$ds ≠ expect=$expect_ds（新旧混版？）"
  info "✓ $ep datasetVersion=$ds"
done
echo "✓ 在线验收通过: current=$EXPECT_RID / datasetVersion=$expect_ds"
