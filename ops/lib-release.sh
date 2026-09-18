#!/usr/bin/env bash
# lib-release.sh：发布客户端脚本族公共库（Task 06 M5）
#
# 被 ops/{deploy,verify,rollback}-release.sh source。提供：
#   - 受控 host key / SSH 封装（禁止运行时 ssh-keyscan 无验证结果）
#   - deploy-mode 读取（legacy | release）
#   - release ID / 环境变量解析与校验
#
# 不直接执行任何发布动作（动作在各脚本内，便于单测断言）。

set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$OPS_DIR/.." && pwd)"

# ---- 可覆盖环境变量 ----
: "${MAAS_DEPLOY_HOST:=47.237.135.97}"
: "${MAAS_DEPLOY_USER:=maasdeploy}"
: "${MAAS_SSH_KEY:=$HOME/.ssh/id_ed25519}"
: "${MAAS_KNOWN_HOSTS:=$OPS_DIR/known_hosts.production}"
: "${MAAS_PUBLIC_ORIGIN:=https://daily.maas.click}"
: "${MAAS_CONNECT_TIMEOUT:=15}"

RID_RE='^rl_[0-9a-f]{10}_[0-9a-f]{12}$'

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "· $*"; }

# ---- deploy-mode 读取（M7 P0 修复：运行时覆盖，不污染 clean worktree）----
# 优先级：MAAS_DEPLOY_MODE 环境变量 > 仓库 ops/deploy-mode 文件 > 默认 legacy。
# 仓库文件**永久保持 legacy**（tracked，不得翻转——翻转会造成工作区脏，
# build-release.sh preflight 的 clean-worktree 检查直接拒绝生产构建，
# 且留下"忘记改回"的风险）。release 通道首发时显式注入：
#   MAAS_DEPLOY_MODE=release ops/deploy-release.sh --commit <approved-sha>
deploy_mode() {
  local line
  if [ -n "${MAAS_DEPLOY_MODE:-}" ]; then
    line="$MAAS_DEPLOY_MODE"
  elif [ -f "$OPS_DIR/deploy-mode" ]; then
    line="$(grep -E '^DEPLOY_MODE=' "$OPS_DIR/deploy-mode" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
  fi
  case "${line:-legacy}" in
    legacy|release) echo "${line:-legacy}" ;;
    *) die "deploy-mode 值非法: ${line}（合法: legacy|release）" ;;
  esac
}

validate_rid() {
  [[ "${1:-}" =~ $RID_RE ]] || die "release ID 格式非法: ${1:-<空>}"
}

# ---- SSH 封装：受控 known_hosts，严格 host key 校验 ----
ssh_base() {
  [ -f "$MAAS_KNOWN_HOSTS" ] \
    || die "受控 host key 缺失: $MAAS_KNOWN_HOSTS（不得用 ssh-keyscan 运行时抓取）"
  echo "ssh -i $MAAS_SSH_KEY" \
       "-o UserKnownHostsFile=$MAAS_KNOWN_HOSTS" \
       "-o StrictHostKeyChecking=yes" \
       "-o ConnectTimeout=$MAAS_CONNECT_TIMEOUT" \
       "-o BatchMode=yes" \
       "-p 22"
}

rsync_ssh_rsh() {
  # rsync -e 需要一个字符串：同样强制受控 known_hosts
  [ -f "$MAAS_KNOWN_HOSTS" ] \
    || die "受控 host key 缺失: $MAAS_KNOWN_HOSTS"
  echo "ssh -i $MAAS_SSH_KEY -o UserKnownHostsFile=$MAAS_KNOWN_HOSTS -o StrictHostKeyChecking=yes -o BatchMode=yes"
}

deploy_target() { echo "$MAAS_DEPLOY_USER@$MAAS_DEPLOY_HOST"; }

# 服务器侧 incoming 根（与服务端 deploy-shell/activate 一致）
SERVER_INCOMING_ROOT="${MAAS_SERVER_INCOMING_ROOT:-/srv/maasweekly/incoming}"

# 远端固定动作（经受限 shell）：激活/回滚/状态
remote_status() { $(ssh_base) "$(deploy_target)" status; }
remote_activate() { validate_rid "$1"; $(ssh_base) "$(deploy_target)" "activate $1"; }
remote_rollback() {
  validate_rid "$1"; [ -n "${2:-}" ] || die "rollback 必须提供 --reason"
  $(ssh_base) "$(deploy_target)" "rollback $1 --reason \"$2\""
}

# 从服务器读取当前 release 的只读 metadata（M7：经受限 shell 的固定 status
# 动作返回，不再通过 ssh 开放任意 python3 -c 命令面）。
server_meta() {  # <field>：datasetVersion|dataThrough|gitCommit|current
  local out
  out="$(remote_status 2>/dev/null)" || die "无法读取服务器 status"
  echo "$out" | grep -E "^${1}:" | head -1 | sed 's/^[^:]*:[[:space:]]*//'
}
current_ds_from_server() { server_meta datasetVersion; }
