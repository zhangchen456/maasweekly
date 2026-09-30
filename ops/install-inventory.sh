#!/usr/bin/env bash
# install-inventory.sh：安装 read-only inventory capability（T08-1A Gate B0 controlled mutation）
#
# ⚠️ 授权边界：本脚本是 Gate B0 controlled mutation。Gate A 验收通过前
# 【不得执行】——执行它会修改服务器 /usr/local/sbin、/usr/local/bin、/etc/sudoers.d。
#
# 职责（严格限定）：
#   1. 安装 ops/server/maasweekly-inventory → /usr/local/sbin/maasweekly-inventory（root:root 0750）
#   2. 更新 ops/server/maasweekly-deploy-shell → /usr/local/bin/maasweekly-deploy-shell（0755）
#   3. 安装最小 sudoers → /etc/sudoers.d/maasweekly-inventory（0440）
#   4. visudo -cf validation；失败 rollback
#
# 除此之外不得（严格禁止）：
#   * install package（apt/pip/npm）
#   * PostgreSQL mutation（CREATE/ALTER/DROP database/role）
#   * create DB/role
#   * create Linux user（useradd/usermod）
#   * clone/build Umami
#   * install maas-umami.service
#   * nginx mutation
#   * reload/restart service（systemctl enable/start/nginx -s）
#   * generate secret
#   * DNS/TLS mutation
#
# 安全合同：
#   * root execution only
#   * fixed source/destination（无 user supplied paths）
#   * no arbitrary command
#   * fail closed
#   * staged installation（backup → install → validate → rollback on failure）
#   * backup existing deploy-shell / inventory helper / sudoers before replacement
#   * visudo -cf 必须在 capability 可用前通过
#   * sudoers validation failure 必须 rollback
#   * deploy-shell replacement failure 必须 rollback
#   * inventory helper replacement failure 必须 rollback
#
# 安装完成后只允许新增：
#   maasdeploy restricted shell → inventory → fixed root-owned read-only helper
# 不能增加其他能力。
#
# 用法（root，在服务器上执行）：
#   ops/install-inventory.sh --dry-run    # 只打印将执行的动作
#   ops/install-inventory.sh             # 真实执行
set -euo pipefail

OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
case "$OPS_DIR" in
  */ops) : ;;
  *) echo "✗ 必须从 ops/ 下执行（当前: ${OPS_DIR}）" >&2; exit 2 ;;
esac

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

# ---- 固定路径（无 user supplied paths）----
INVENTORY_SRC="$OPS_DIR/server/maasweekly-inventory"
DEPLOY_SHELL_SRC="$OPS_DIR/server/maasweekly-deploy-shell"
INVENTORY_DST=/usr/local/sbin/maasweekly-inventory
DEPLOY_SHELL_DST=/usr/local/bin/maasweekly-deploy-shell
SUDOERS_DST=/etc/sudoers.d/maasweekly-inventory
# sudoers 授权对象：maasdeploy（restricted SSH 登录用户），不是 maasumami
SUDOERS_USER=maasdeploy

# 校验 root 执行
[ "$(id -u)" = "0" ] || { echo "✗ 必须以 root 执行" >&2; exit 2; }

# 校验源文件存在
[ -f "$INVENTORY_SRC" ] || { echo "✗ 源文件缺失: $INVENTORY_SRC" >&2; exit 2; }
[ -f "$DEPLOY_SHELL_SRC" ] || { echo "✗ 源文件缺失: $DEPLOY_SHELL_SRC" >&2; exit 2; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/backups/maasweekly-inventory-${TS}"

run() {  # run <desc> <cmd...>：统一输出与 dry-run
  echo "· $1"
  if [ "$DRY_RUN" = "1" ]; then echo "    [dry-run] $2"; return 0; fi
  eval "$2"
}

die() { echo "✗ $*" >&2; exit 1; }

echo "== T08-1A install-inventory（Gate B0 controlled mutation；dry-run: ${DRY_RUN}） =="

# ---- 0. preflight（只读检查，不 mutation）----
echo "· preflight：校验源文件与目标路径"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] 校验 $INVENTORY_SRC / $DEPLOY_SHELL_SRC 存在"
  echo "    [dry-run] 校验 /usr/local/sbin /usr/local/bin /etc/sudoers.d 存在"
else
  [ -d /usr/local/sbin ] || die "/usr/local/sbin 不存在"
  [ -d /usr/local/bin ] || die "/usr/local/bin 不存在"
  [ -d /etc/sudoers.d ] || die "/etc/sudoers.d 不存在"
  command -v visudo >/dev/null 2>&1 || die "visudo 不存在（需要 sudo 包）"
fi

# ---- 1. backup existing files（staged installation）----
echo "· backup existing files"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] mkdir -p $BACKUP_DIR"
  echo "    [dry-run] backup existing deploy-shell / inventory helper / sudoers"
else
  mkdir -p "$BACKUP_DIR"
  # backup existing deploy-shell
  if [ -f "$DEPLOY_SHELL_DST" ]; then
    cp -a "$DEPLOY_SHELL_DST" "$BACKUP_DIR/$(basename "$DEPLOY_SHELL_DST").backup"
    echo "  ✓ backup existing deploy-shell"
  else
    echo "  · 无 existing deploy-shell（首次安装）"
  fi
  # backup existing inventory helper
  if [ -f "$INVENTORY_DST" ]; then
    cp -a "$INVENTORY_DST" "$BACKUP_DIR/$(basename "$INVENTORY_DST").backup"
    echo "  ✓ backup existing inventory helper"
  else
    echo "  · 无 existing inventory helper（首次安装）"
  fi
  # backup existing sudoers
  if [ -f "$SUDOERS_DST" ]; then
    cp -a "$SUDOERS_DST" "$BACKUP_DIR/$(basename "$SUDOERS_DST").backup"
    echo "  ✓ backup existing sudoers"
  else
    echo "  · 无 existing sudoers（首次安装）"
  fi
fi

# ---- 2. install inventory helper → /usr/local/sbin（root:root 0750）----
echo "· 安装 inventory helper → $INVENTORY_DST（root:root 0750）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] install -m 0750 -o root -g root $INVENTORY_SRC $INVENTORY_DST"
else
  install -m 0750 -o root -g root "$INVENTORY_SRC" "$INVENTORY_DST"
  echo "  ✓ inventory helper 已安装"
fi

# ---- 3. install sudoers → /etc/sudoers.d/maasweekly-inventory（0440）----
# sudoers 授权对象：maasdeploy（restricted SSH 登录用户），不是 maasumami
# 只允许 NOPASSWD 调用固定 inventory helper，不扩大权限
echo "· 安装 sudoers（principal=$SUDOERS_USER，只允许 $INVENTORY_DST）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] echo '$SUDOERS_USER ALL=(root) NOPASSWD: $INVENTORY_DST' > $SUDOERS_DST"
  echo "    [dry-run] chmod 0440 $SUDOERS_DST && visudo -cf $SUDOERS_DST"
else
  echo "$SUDOERS_USER ALL=(root) NOPASSWD: $INVENTORY_DST" > "$SUDOERS_DST"
  chmod 0440 "$SUDOERS_DST"
  echo "  ✓ sudoers 已安装（principal=$SUDOERS_USER）"
fi

# ---- 4. visudo -cf validation（必须在 deploy-shell 更新前通过）----
echo "· visudo -cf validation（sudoers 必须有效）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] visudo -cf $SUDOERS_DST"
else
  if ! visudo -cf "$SUDOERS_DST" 2>&1; then
    echo "✗ visudo -cf 失败——rollback sudoers" >&2
    # rollback：恢复 backup 或删除（首次安装）
    if [ -f "$BACKUP_DIR/$(basename "$SUDOERS_DST").backup" ]; then
      cp -a "$BACKUP_DIR/$(basename "$SUDOERS_DST").backup" "$SUDOERS_DST"
      echo "  ✓ sudoers 已恢复 backup" >&2
    else
      rm -f "$SUDOERS_DST"
      echo "  ✓ sudoers 已删除（首次安装，无 backup）" >&2
    fi
    # rollback inventory helper
    if [ -f "$BACKUP_DIR/$(basename "$INVENTORY_DST").backup" ]; then
      cp -a "$BACKUP_DIR/$(basename "$INVENTORY_DST").backup" "$INVENTORY_DST"
      echo "  ✓ inventory helper 已恢复 backup" >&2
    else
      rm -f "$INVENTORY_DST"
      echo "  ✓ inventory helper 已删除（首次安装）" >&2
    fi
    die "sudoers validation 失败，已 rollback（capability 不可用）"
  fi
  echo "  ✓ visudo -cf 通过"
fi

# ---- 5. update deploy-shell → /usr/local/bin/maasweekly-deploy-shell（0755）----
echo "· 更新 deploy-shell（新增 inventory 分支）→ $DEPLOY_SHELL_DST（0755）"
if [ "$DRY_RUN" = "1" ]; then
  echo "    [dry-run] install -m 0755 $DEPLOY_SHELL_SRC $DEPLOY_SHELL_DST"
else
  install -m 0755 "$DEPLOY_SHELL_SRC" "$DEPLOY_SHELL_DST"
  echo "  ✓ deploy-shell 已更新"
fi

# ---- 6. 完成检查 ----
echo "== install-inventory 完成 =="
cat <<EOF
  $INVENTORY_DST       (0750 root:root，只读 inventory helper)
  $DEPLOY_SHELL_DST    (0755，restricted shell，新增 inventory 分支)
  $SUDOERS_DST  (0440，principal=$SUDOERS_USER，只允许 $INVENTORY_DST)

  ⚠ capability 范围（严格限定）：
    maasdeploy SSH → maasweekly-deploy-shell → inventory
      → sudo -n /usr/local/sbin/maasweekly-inventory（只读）

  ⚠ 本脚本不安装 package / 不修改 PostgreSQL / 不创建 DB/role / 不创建 Linux user /
    不 clone/build Umami / 不 install maas-umami.service / 不修改 nginx /
    不 reload/restart service / 不 generate secret / 不 DNS/TLS mutation。

  ⚠ backup 已保存到 $BACKUP_DIR（如需 rollback 见下文）

  rollback（手动，如需）：
    恢复 deploy-shell：cp -a $BACKUP_DIR/$(basename "$DEPLOY_SHELL_DST").backup $DEPLOY_SHELL_DST
    恢复 inventory helper：cp -a $BACKUP_DIR/$(basename "$INVENTORY_DST").backup $INVENTORY_DST
    恢复 sudoers：cp -a $BACKUP_DIR/$(basename "$SUDOERS_DST").backup $SUDOERS_DST && visudo -cf $SUDOERS_DST
    首次安装无 backup：rm -f $INVENTORY_DST $DEPLOY_SHELL_DST $SUDOERS_DST
EOF
echo "✓ inventory capability 已安装（maasdeploy → inventory → 只读 helper）"
