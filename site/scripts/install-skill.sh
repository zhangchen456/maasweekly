#!/usr/bin/env bash
# maas-daily Skill 安装器（Task 04 M7）
# 用法: install.sh --dir <目标目录> [--base-url <url>] [--version <v>]
#       [--timeout <sec>] [--retries <n>]
#
# 退出码: 0 成功 | 2 用法错误 | 3 下载失败 | 4 清单/校验失败
#         5 目标非法 | 6 替换/恢复失败 | 7 缺依赖
# 安全: 只写 --dir 指定目录与其同级临时目录；不用 sudo；不跟随逃逸符号链接。

set -u

SCRIPT_NAME="maas-daily Skill 安装器"
SKILL_NAME="maas-daily"
DEFAULT_BASE="https://daily.maas.click/maas-skill"
TMP_PREFIX=".maas-skill-install"

die() { echo "$1" >&2; exit "${2:-1}"; }
usage() {
  cat <<EOF
$SCRIPT_NAME

必选:
  --dir <target>     Skill 安装目标目录（如 ~/.claude/skills/maas-daily 的父级）
可配置:
  --base-url <url>   包下载源（默认 ${DEFAULT_BASE}）
  --version <v>      包版本（默认 manifest 最新）
  --timeout <sec>    单请求超时（默认 15）
  --retries <n>      重试次数（默认 2）
  --help             本说明
EOF
  exit 0
}

# 依赖检查
command -v curl >/dev/null 2>&1 || die "缺少 curl（退出 7）" 7
sha256() { shasum -a 256 2>/dev/null || sha256sum; }
command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 \
  || die "缺少 shasum/sha256sum（退出 7）" 7

# 参数解析
TARGET="" BASE_URL="$DEFAULT_BASE" VERSION="" TIMEOUT=15 RETRIES=2
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) [ $# -ge 2 ] || die "--dir 需要参数（退出 2）" 2; TARGET="$2"; shift 2 ;;
    --base-url) [ $# -ge 2 ] || die "--base-url 需要参数（退出 2）" 2; BASE_URL="${2%/}"; shift 2 ;;
    --version) [ $# -ge 2 ] || die "--version 需要参数（退出 2）" 2; VERSION="$2"; shift 2 ;;
    --timeout) [ $# -ge 2 ] || die "--timeout 需要参数（退出 2）" 2; TIMEOUT="$2"; shift 2 ;;
    --retries) [ $# -ge 2 ] || die "--retries 需要参数（退出 2）" 2; RETRIES="$2"; shift 2 ;;
    --help) usage ;;
    *) die "未知参数: $1（退出 2）" 2 ;;
  esac
done
[ -n "$TARGET" ] || { echo "必须显式指定 --dir（不猜测客户端目录）" >&2; exit 2; }

# 路径归一化（不依赖 readlink -f；拒绝显式 ..）
case "$TARGET" in
  *..*) die "目标路径含 ..（退出 2）" 2 ;;
esac
TARGET_DIR=$(cd "$(dirname "$TARGET")" 2>/dev/null && pwd) || die "目标父目录不存在: $TARGET" 5
TARGET_NAME=$(basename "$TARGET")
TARGET="$TARGET_DIR/$TARGET_NAME"
# 目标父目录不得是符号链接（防逃逸；不向上遍历——/tmp 等系统级
# symlink 是合法路径，逐级遍历会误拒）
[ -L "$TARGET_DIR" ] && die "目标父目录是符号链接（拒绝，退出 5）" 5

# 中断恢复：检测同级残留（上次安装中断）
for stale in "$TARGET_DIR/$TMP_PREFIX".*; do
  [ -e "$stale" ] || continue
  if [ ! -e "$TARGET" ] && [ -d "$stale/backup" ]; then
    mv "$stale/backup" "$TARGET" 2>/dev/null \
      && echo "检测到上次安装中断：已恢复原版本（${TARGET}）" >&2
  fi
  rm -rf "$stale" 2>/dev/null
  echo "已清理中断残留: $(basename "$stale")" >&2
done

# 临时目录（与目标同级，保证 mv 原子；失败时的恢复路径同文件系统）
TMP=$(mktemp -d "$TARGET_DIR/${TMP_PREFIX}.XXXXXX") || die "无法创建临时目录（退出 6）" 6
cleanup() { rm -rf "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

# ---- 下载 manifest ----
fetch() { # fetch <url> <输出路径>
  curl --fail --silent --show-error --max-time "$TIMEOUT" --retry "$RETRIES" \
       -o "$2" "$1" 2>/dev/null
}
MANIFEST_URL="$BASE_URL/manifest.json"
fetch "$MANIFEST_URL" "$TMP/manifest.json" \
  || die "下载 manifest 失败（退出 3）: $MANIFEST_URL" 3

# ---- manifest 结构校验（无 jq 依赖的极简检查）----
M_CHECK=$(python3 - "$TMP/manifest.json" <<'PYEOF' 2>/dev/null || echo BAD
import json, sys
try:
    m = json.load(open(sys.argv[1]))
    assert m.get("skillName") == "maas-daily"
    assert m.get("schemaVersion") == "1.0"
    files = m.get("files") or []
    assert len(files) > 0
    for f in files:
        p = f["path"]
        assert isinstance(p, str) and p and ".." not in p and not p.startswith("/")
        assert isinstance(f["bytes"], int) and f["bytes"] > 0
        assert len(f["sha256"]) == 64
    paths = [f["path"] for f in files]
    assert len(paths) == len(set(paths)), "重复路径"
    print("OK")
except Exception as e:
    print(f"BAD: {e}", file=sys.stderr)
PYEOF
)
[ "$M_CHECK" = "OK" ] || die "manifest 非法（退出 4）" 4

# 版本选择与校验（复验 P2-1：--version 必须与 manifest 一致，否则报错
# 而不是静默装别的版本还打印用户要的版本号）
MANIFEST_VERSION=$(python3 -c "import json; print(json.load(open('$TMP/manifest.json'))['packageVersion'])")
if [ -z "$VERSION" ]; then
  VERSION="$MANIFEST_VERSION"
elif [ "$VERSION" != "$MANIFEST_VERSION" ]; then
  die "请求版本 ${VERSION} 不存在（manifest 仅提供 ${MANIFEST_VERSION}；退出 4）" 4
fi
# （v1 单版本发布：manifest 即最新；未来多版本扩展 releases/<v>/ 路径规则）

# ---- 下载全部文件 ----
STAGE="$TMP/stage"
mkdir -p "$STAGE"
FILE_LIST=$(python3 -c "
import json
for f in json.load(open('$TMP/manifest.json'))['files']:
    print(f\"{f['path']} {f['bytes']} {f['sha256']}\")")
echo "$FILE_LIST" | while IFS=' ' read -r rel bytes want_sha; do
  [ -n "$rel" ] || continue
  mkdir -p "$STAGE/$(dirname "$rel")"
  fetch "$BASE_URL/$rel" "$STAGE/$rel" || { echo "下载失败: $rel" >&2; exit 3; }
done || rc=$?
[ "${rc:-0}" = "0" ] || die "部分文件下载失败（退出 3）" 3

# ---- 逐文件校验（bytes + sha256）----
VERIFY_FAIL=0
echo "$FILE_LIST" | while IFS=' ' read -r rel bytes want_sha; do
  [ -n "$rel" ] || continue
  f="$STAGE/$rel"
  if [ ! -f "$f" ]; then echo "缺文件: $rel" >&2; exit 4; fi
  actual_bytes=$(wc -c < "$f" | tr -d ' ')
  if [ "$actual_bytes" != "$bytes" ]; then echo "bytes 不符: ${rel}（$actual_bytes != ${bytes}）" >&2; exit 4; fi
  actual_sha=$(sha256 < "$f" | awk '{print $1}')
  if [ "$actual_sha" != "$want_sha" ]; then echo "sha256 不符: $rel" >&2; exit 4; fi
done || VERIFY_FAIL=$?
[ "$VERIFY_FAIL" = "0" ] || die "文件校验失败（退出 4）" 4

# 文件数精确比对（缺一不可、多一不可）
EXPECT_N=$(echo "$FILE_LIST" | grep -c .)
ACTUAL_N=$(find "$STAGE" -type f | wc -l | tr -d ' ')
[ "$ACTUAL_N" = "$EXPECT_N" ] || die "文件数不符（期望 ${EXPECT_N}，实得 ${ACTUAL_N}；退出 4）" 4

# manifest 也放进目标（升级时已知文件集的依据）
cp "$TMP/manifest.json" "$STAGE/manifest.json"

# ---- 目标判定 ----
if [ -e "$TARGET" ]; then
  if [ -L "$TARGET" ]; then die "目标是符号链接（拒绝，退出 5）" 5; fi
  if [ ! -d "$TARGET" ]; then die "目标已存在且不是目录（退出 5）" 5; fi
  # 必须是合法 maas-daily（或空目录）：SKILL.md frontmatter name 校验
  if [ -f "$TARGET/SKILL.md" ]; then
    TARGET_NAME_IN=$(sed -n 's/^name:[[:space:]]*//p' "$TARGET/SKILL.md" | head -1 | tr -d '"' | tr -d "'" | tr -d '\r')
    if [ "$TARGET_NAME_IN" != "$SKILL_NAME" ]; then
      die "目标已含其他 Skill（name: ${TARGET_NAME_IN:-未知}；拒绝覆盖，退出 5）" 5
    fi
    # 合法同名也不能静默删未知文件（验收 P1-1 / US-10）：目标内文件
    # 必须全部属于「新 manifest 已列 ∪ 旧 manifest 已列 ∪ 本包已知集合」，
    # 出现用户自建文件（如 user-config.md）→ 拒绝覆盖退出 5
    OLD_MANIFEST="$TARGET/manifest.json"
    KNOWN=$(python3 - "$TMP/manifest.json" "$OLD_MANIFEST" <<'PYEOF' 2>/dev/null || echo ""
import json, sys
known = set()
new_m = sys.argv[1]
try:
    known |= {f["path"] for f in json.load(open(new_m))["files"]}
except Exception:
    pass
known |= {"manifest.json"}
if len(sys.argv) > 2:
    try:
        old = json.load(open(sys.argv[2]))
        for f in old.get("files") or []:
            known.add(f["path"])
    except Exception:
        pass
for rel in sorted(known):
    print(rel)
PYEOF
)
    if [ -n "$KNOWN" ]; then
      while IFS= read -r kf; do
        [ -n "$kf" ] || continue
        if [ -e "$TARGET/$kf" ]; then
          # 已知文件存在——OK（继续比对未知文件）
          :
        fi
      done <<EOF2
$KNOWN
EOF2
      # 未知文件检测（不在 KNOWN 集内的任何文件）
      UNKNOWN=$(cd "$TARGET" && find . -type f | sed 's|^\./||' | while IFS= read -r f; do
        echo "$KNOWN" | grep -qxF "$f" || echo "$f"
      done)
      if [ -n "$UNKNOWN" ]; then
        die "目标目录含未知文件（拒绝覆盖以保护用户数据，退出 5）：${UNKNOWN}" 5
      fi
    fi
  else
    # 无 SKILL.md：只允许空目录
    EXISTING=$(find "$TARGET" -type f | wc -l | tr -d ' ')
    [ "$EXISTING" = "0" ] || die "目标目录非空且无 maas-daily 标识（拒绝覆盖，退出 5）" 5
  fi
  # 目录内不得有逃逸符号链接
  if find "$TARGET" -type l | grep -q .; then
    die "目标目录含符号链接（拒绝，退出 5）" 5
  fi
fi

# ---- 备份 + 原子替换 ----
if [ -e "$TARGET" ]; then
  mv "$TARGET" "$TMP/backup" || die "备份失败（退出 6）" 6
fi
if ! mv "$STAGE" "$TARGET"; then
  if [ -d "$TMP/backup" ]; then
    mv "$TMP/backup" "$TARGET" && die "替换失败，已恢复原版本（退出 6）" 6
  fi
  die "替换失败（退出 6）" 6
fi

# 安装器自身不放入目标（manifest 未列它）
echo "✓ $SKILL_NAME $VERSION 已安装到 $TARGET"
echo "验证（新会话中问）: 「用 maas-daily 查一下最近几天 OpenAI 有什么变化」"
exit 0
