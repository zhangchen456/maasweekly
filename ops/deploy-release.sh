#!/usr/bin/env bash
# deploy-release.sh：从本地构建并把 release 发布到服务器（Task 06 M5）
#
# 用法：
#   ops/deploy-release.sh                 # 构建 HEAD → 上传 incoming → 激活 → 冒烟
#   ops/deploy-release.sh --local-only    # 只构建不发布（CI 倒挂/测试）
#   ops/deploy-release.sh --commit <sha>  # 构建指定 commit（必须先 push）
#
# 通道（ops/deploy-mode 决定）：
#   legacy  现有 rsync 到 /var/www/maasweekly（保持现状，无新机制介入）
#   release incoming → 校验 → 蓝绿激活（服务器激活脚本负责锁/旧作业拒绝/回滚）
#
# 边界：不恢复直接 rsync 在线根目录的旁路；所有发布都经此入口。
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

. "$(dirname "$0")/lib-release.sh"

LOCAL_ONLY=false
COMMIT="HEAD"
OUTPUT_DIR="dist-release"
BUILD_EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --local-only) LOCAL_ONLY=true; shift ;;
    --commit) COMMIT="$2"; shift 2 ;;
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --skip-tests) BUILD_EXTRA="--skip-tests"; shift ;;
    *) die "未知参数: $1" ;;
  esac
done

MODE="$(deploy_mode)"
info "deploy-mode: $MODE"

# ---- 步骤 1：构建（唯一入口 build-release.sh）----
info "构建 release（commit=$COMMIT${BUILD_EXTRA:+，$BUILD_EXTRA}）"
scripts/build-release.sh --commit "$COMMIT" --output "$OUTPUT_DIR" $BUILD_EXTRA

# 从构建产物里取出真正的 RID：按 mtime 取最新（dist-release 可能残留旧 release；
# 不能用 find|head -1——目录序不稳定会拿到旧产物）
RID_DIR="$(ls -td "$OUTPUT_DIR"/*/ 2>/dev/null | head -1)"
RID_DIR="${RID_DIR%/}"
[ -n "$RID_DIR" ] || die "构建未产出 release 目录: $OUTPUT_DIR"
RID="$(basename "$RID_DIR")"
validate_rid "$RID"
info "release: $RID"

RELEASE_DIR="$RID_DIR"
MANIFEST="$RELEASE_DIR/metadata/release-manifest.json"
[ -f "$MANIFEST" ] || die "构建产物缺 manifest: $MANIFEST"

# --skip-tests 的产物禁止激活——在客户端就拦下
if grep -q '"testsSkipped": true' "$MANIFEST"; then
  die "release $RID 标记 testsSkipped=true（--skip-tests 产物），禁止部署/激活"
fi

if $LOCAL_ONLY; then
  echo "✓ $RID 已构建（local-only）"
  exit 0
fi

if [ "$MODE" = "legacy" ]; then
  # ---- legacy：构建与部署分开，行为完全保持现状 ----
  info "legacy 通道：rsync 到 $MAAS_DEPLOY_USER@$MAAS_DEPLOY_HOST:/var/www/maasweekly/"
  rsync -az --delete -e "$(rsync_ssh_rsh)" \
    "$RELEASE_DIR/site/" \
    "$MAAS_DEPLOY_USER@$MAAS_DEPLOY_HOST:/var/www/maasweekly/"
  echo "✓ legacy 部署完成（$RID 的 site 已发布）"
  exit 0
fi

# ---- release 通道：incoming → 激活 → 公网冒烟 ----
info "release 通道：上传 incoming → 激活 → 公网冒烟"

# 上传（rsync 服务端受限 shell 只放行 incoming/<rid>/）
RSYNC_SSH="$(rsync_ssh_rsh)"
DEST_DIR="$SERVER_INCOMING_ROOT/$RID/"
# 用 rsync --delete 确保 incoming 目录与本地一致（幂等：同 RID 重传可重试）
rsync -az --delete -e "$RSYNC_SSH" "$RELEASE_DIR/" "$(deploy_target):$DEST_DIR"
info "✓ 上传完成: $RID → incoming"

exit_code=0
remote_activate "$RID" || exit_code=$?
if [ "$exit_code" -ne 0 ]; then
  echo "✗ 激活失败 exit=$exit_code（当前站点无变化；incoming 保留可诊断）" >&2
  exit "$exit_code"
fi
info "✓ 激活完成: $RID"

# ---- 公网冒烟（必须看到激活的数据版本，防新旧混版）----
DS_VER="$(python3 -c "import json; print(json.load(open('$MANIFEST'))['datasetVersion'])")"
info "公网冒烟: $MAAS_PUBLIC_ORIGIN/api/v1/status（expect datasetVersion=$DS_VER）"

# 缓存穿透+重试（CDN/浏览器缓存容忍窗口）
ok=false
for i in 1 2 3 4 5; do
  body="$(curl -sf --max-time 10 --get \
    -H "Cache-Control: no-cache" -H "Pragma: no-cache" \
    "$MAAS_PUBLIC_ORIGIN/api/v1/status" 2>/dev/null || true)"
  if [ -n "$body" ] && [ "$(echo "$body" | python3 -c \
      "import sys,json; print(json.load(sys.stdin).get('datasetVersion',''))" 2>/dev/null)" = "$DS_VER" ]; then
    ok=true; break
  fi
  sleep 2
done
[ "$ok" = true ] \
  || die "公网冒烟失败：status 的 datasetVersion 未见新值（候选已切但外部不可视）"

echo "✓ release 通道发布完成: $RID（datasetVersion=$DS_VER）"
