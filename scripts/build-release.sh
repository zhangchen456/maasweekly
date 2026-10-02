#!/usr/bin/env bash
# build-release.sh：生产 release 唯一构建入口（Task 06 M3，D1）。
#
# 从干净、明确的 Git commit 构建不可变 release：
#   preflight（工作区/commit 校验）→ 公开投影 → 全量门禁与测试 →
#   构建后 tracked diff 复查 → agent-api 生产包 → 组装 → manifest。
#
# 用法：
#   scripts/build-release.sh                     # 从 HEAD 构建
#   scripts/build-release.sh --preflight-only    # 只跑步骤 0（测试用）
#   scripts/build-release.sh --skip-tests        # 本地已全量回归时加速
#   scripts/build-release.sh --output <dir>      # 默认 dist-release/
set -euo pipefail
BASE="${MAAS_RELEASE_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$BASE"

COMMIT="HEAD"
OUTPUT_DIR="dist-release"
PREFLIGHT_ONLY=false
SKIP_TESTS=false
while [ $# -gt 0 ]; do
  case "$1" in
    --preflight-only) PREFLIGHT_ONLY=true; shift ;;
    --skip-tests) SKIP_TESTS=true; shift ;;
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --commit) COMMIT="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

die() { echo "✗ $1" >&2; exit 1; }

# Diagnostic failures never change build outcome. Seconds has 1s resolution.
DIAG_PHASE=preflight
DIAG_STARTED=$SECONDS
DIAG_TOTAL=$SECONDS
PKG_TMP=""
RID=""
GIT_SHA=""
DS_VER=""
release_event() {
  [ "${MAAS_RELEASE_DIAGNOSTICS:-1}" != 0 ] || return 0
  python3 - "$1" "$2" "$3" "$4" "$GIT_SHA" "$RID" "$DS_VER" "${OUT:-}" "$PREFLIGHT_ONLY" <<'PYDIAG' >&2 || true
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path
kind, stage, rc, elapsed, commit, rid, ds, root, preflight_only = sys.argv[1:]
e = dict(timestamp=datetime.now(timezone.utc).isoformat(), kind=kind, operation='preflight' if preflight_only=='true' else 'build',
         stage=stage, outcome='success' if int(rc)==0 else 'failed', exitCode=int(rc), elapsedMs=int(elapsed)*1000,
         timingResolutionMs=1000)
for k, v, pattern in [('gitCommit', commit, r'[0-9a-f]{40}'), ('releaseId', rid, r'rl_[0-9a-f]{10}_[0-9a-f]{12}'), ('datasetVersion', ds, r'ds_[0-9a-f]{64}')]:
    if re.fullmatch(pattern, v): e[k]=v
if kind=='release.result' and int(rc)==0 and root:
    try: e['totals']=json.loads((Path(root)/'metadata/release-manifest.json').read_text())['totals']
    except (OSError, ValueError, KeyError): pass
print(json.dumps(e, separators=(',', ':')))
PYDIAG
}
next_phase() {
  release_event release.stage "$DIAG_PHASE" 0 "$((SECONDS-DIAG_STARTED))"
  DIAG_PHASE="$1"; DIAG_STARTED=$SECONDS
}
finish_build() {
  local rc=$?
  trap - EXIT
  release_event release.stage "$DIAG_PHASE" "$rc" "$((SECONDS-DIAG_STARTED))"
  release_event release.result "$DIAG_PHASE" "$rc" "$((SECONDS-DIAG_TOTAL))"
  [ -z "$PKG_TMP" ] || rm -rf "$PKG_TMP"
  exit "$rc"
}
trap finish_build EXIT


# ---- 步骤 0：preflight（T03 全部拒绝点）----
echo "[0/6] preflight"
git rev-parse --verify "$COMMIT^{commit}" >/dev/null 2>&1 \
  || die "未知 commit: $COMMIT"
GIT_SHA="$(git rev-parse "$COMMIT")"
[ -z "$(git status --porcelain)" ] || die "工作区脏，拒绝生产 release（先提交或 stash）"
[ "$(git rev-parse HEAD)" = "$(git rev-parse "$COMMIT")" ] \
  || die "HEAD 与声明 commit 不符（生产 release 只能从 HEAD 构建）"
echo "  ✓ commit $(git rev-parse --short "$COMMIT")，工作区干净"

if $PREFLIGHT_ONLY; then echo "preflight-only：到此为止"; exit 0; fi

next_phase projection

# ---- 步骤 1：公开投影 ----
echo "[1/6] 公开数据投影"
python3 pipeline/scripts/export-public-data.py
python3 pipeline/scripts/export-public-data.py --check

next_phase regression

# ---- 步骤 2：统一全量回归（scripts/run-all-tests.sh，复验 P1c）----
TESTS_FLAG=""
if ! $SKIP_TESTS; then
  echo "[2/6] 统一全量回归（Task 01–06）"
  scripts/run-all-tests.sh || die "全量回归失败（见上方失败项）——生产 release 拒绝"
else
  echo "[2/6] ⚠ 跳过测试（--skip-tests）——release 将标记为不可激活"
  TESTS_FLAG="--skip-tests-marked"
  node scripts/ensure-node-deps.mjs services/agent-api
  npm --prefix services/agent-api run build --silent
  (node scripts/ensure-node-deps.mjs site && cd site && npm run build >/dev/null 2>&1) || die "site 构建失败"
fi

next_phase clean-tree

# ---- 步骤 3：构建后 tracked diff 复查（数据未提交的信号）----
echo "[3/6] tracked diff 复查"
[ -z "$(git status --porcelain)" ] \
  || { git status --short >&2; die "构建产生未解释的 tracked 改动（数据未提交？）"; }

next_phase runtime-package

# ---- 步骤 4：agent-api 生产运行包 ----
# The complete suite already compiled/tested the exact checkout. Reuse dist,
# then install only production dependencies into an isolated runtime package.
echo "[4/6] agent-api 生产包（已验编译产物 + omit=dev 安装）"
[ -f services/agent-api/dist/server.js ] || die "agent-api 编译产物缺失"
PKG_TMP="$(mktemp -d "${TMPDIR:-/tmp}/maas-release-pkg.XXXXXX")"
PKG="$PKG_TMP/agent-api"
mkdir -p "$PKG"
cp -R services/agent-api/dist services/agent-api/package.json services/agent-api/package-lock.json "$PKG/"
(cd "$PKG" && npm ci --omit=dev --prefer-offline --silent)
[ -f "$PKG/node_modules/@modelcontextprotocol/sdk/package.json" ] \
  || die "agent-api 生产依赖缺失：@modelcontextprotocol/sdk"
[ -f "$PKG/node_modules/zod/package.json" ] || die "agent-api 生产依赖缺失：zod"

next_phase assembly

# ---- 步骤 5：组装 release 目录 ----
echo "[5/6] 组装 release"
GIT_SHA="$(git rev-parse "$COMMIT")"
GIT_TS="$(git show -s --format=%ct "$COMMIT")"
DS_VER="$(python3 -c "import json; print(json.load(open('data/public/v1/manifest.json'))['datasetVersion'])")"
DATA_THROUGH="$(python3 -c "import json; print(json.load(open('data/public/v1/manifest.json'))['dataThrough'])")"
RID="rl_$(git rev-parse --short=10 "$COMMIT")_${DS_VER:3:12}"
OUT="$OUTPUT_DIR/$RID"
rm -rf "$OUT"
mkdir -p "$OUT/metadata"
rsync -a --delete site/dist/ "$OUT/site/"
mkdir -p "$OUT/data/public/v1"
rsync -a --delete data/public/v1/ "$OUT/data/public/v1/"
mkdir -p "$OUT/agent-api"
cp -R "$PKG/dist" "$PKG/package.json" "$PKG/package-lock.json" "$PKG/node_modules" "$OUT/agent-api/"

next_phase manifest

# ---- 步骤 6：manifest ----
echo "[6/6] manifest"
BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 pipeline/scripts/release_manifest.py build --root "$OUT" --rid "$RID" \
  --git-commit "$GIT_SHA" --git-ts "$GIT_TS" \
  --dataset-version "$DS_VER" --data-through "$DATA_THROUGH" \
  --built-at "$BUILT_AT" $TESTS_FLAG
python3 pipeline/scripts/release_manifest.py verify --root "$OUT"

echo "✓ release $RID → $OUT"
echo "  datasetVersion=$DS_VER dataThrough=$DATA_THROUGH commit=$(git rev-parse --short "$COMMIT")"
