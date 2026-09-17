#!/usr/bin/env bash
# rollback-release.sh：回滚到指定 release（Task 06 M5）
#
# 用法：ops/rollback-release.sh <rid> --reason "<原因>"
#
# 服务器激活脚本的 rollback 动作已经覆盖：
#   - 数据集兼容性校验（目标 release 必须覆盖当前 datasetVersion）
#   - 切换事务（失败时 current/include/slots 全部恢复，目标保留原位）
#   - 回滚原因记录 activations.log
# 本脚本只是命令入口，不在客户端二次实现逻辑。
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
. "$(dirname "$0")/lib-release.sh"

RID=""
REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --reason) REASON="$2"; shift 2 ;;
    *) [ -z "$RID" ] && RID="$1" || die "多余参数: $1"; shift ;;
  esac
done
validate_rid "$RID"
[ -n "$REASON" ] || die "用法: rollback-release.sh <rid> --reason \"<原因>\""

# 服务器 current 应为要回滚的目标的前一个版本（不强制，便于运维观察）
info "回滚 $RID（原因: $REASON）"
remote_rollback "$RID" "$REASON"
echo "✓ 回滚已下发：$RID"

# 提示后续验证步骤（不做自动验证——由 ops/verify-release.sh 完成）
echo "· 下一步：ops/verify-release.sh --online --expect-release $RID"
