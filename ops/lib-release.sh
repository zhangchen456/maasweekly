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

# ---- deploy-mode 读取（默认 legacy：行为不变）----
deploy_mode() {
  local f="$OPS_DIR/deploy-mode" line
  if [ -f "$f" ]; then
    line="$(grep -E '^DEPLOY_MODE=' "$f" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
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

# 从服务器读取某 release 的 datasetVersion（经受限 shell 不开放任意命令面，
# 因此走 ssh 到同一台机器用 sudo -n 直接读文件——前提是 sudoers 单行 NOPASSWD
# 已允许 activate 脚本所属用户的只读 manifest 读取；M7 安装时配套配置）。
current_ds_from_server() {
  local rid="$1" path="/srv/maasweekly/releases/$rid/metadata/release-manifest.json"
  $(ssh_base) "$(deploy_target)" \
    "python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"datasetVersion\"])' '$path'"
}
