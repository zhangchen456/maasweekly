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

# ---- 步骤 0：preflight（T03 全部拒绝点）----
echo "[0/6] preflight"
git rev-parse --verify "$COMMIT^{commit}" >/dev/null 2>&1 \
  || die "未知 commit: $COMMIT"
[ -z "$(git status --porcelain)" ] || die "工作区脏，拒绝生产 release（先提交或 stash）"
[ "$(git rev-parse HEAD)" = "$(git rev-parse "$COMMIT")" ] \
  || die "HEAD 与声明 commit 不符（生产 release 只能从 HEAD 构建）"
echo "  ✓ commit $(git rev-parse --short "$COMMIT")，工作区干净"

if $PREFLIGHT_ONLY; then echo "preflight-only：到此为止"; exit 0; fi

# ---- 步骤 1：公开投影 ----
echo "[1/6] 公开数据投影"
python3 pipeline/scripts/export-public-data.py
python3 pipeline/scripts/export-public-data.py --check

# ---- 步骤 2：门禁与测试 ----
if ! $SKIP_TESTS; then
  echo "[2/6] 全量门禁与测试"
  python3 pipeline/scripts/validate-archive.py
  python3 pipeline/scripts/validate-price-archive.py --check
  python3 -m unittest discover -s tests -p 'test_*.py' 2>&1 | tail -1
  (cd site && npm ci --silent && npm run build >/dev/null 2>&1) \
    || die "site 构建失败"
  (cd site && node --experimental-strip-types tests/access-pages.test.mjs >/dev/null) \
    || die "access-pages 测试失败"
  (cd site && node --experimental-strip-types tests/rss.test.mjs >/dev/null) \
    || die "rss 测试失败"
  (cd services/agent-api && npm ci --silent && npm run build >/dev/null 2>&1 && npm test 2>&1 | grep -q '^# fail 0') \
    || die "agent-api 构建或测试失败"
else
  echo "[2/6] 跳过测试（--skip-tests）；site 构建仍执行"
  (cd site && npm ci --silent && npm run build >/dev/null 2>&1) || die "site 构建失败"
fi

# ---- 步骤 3：构建后 tracked diff 复查（数据未提交的信号）----
echo "[3/6] tracked diff 复查"
[ -z "$(git status --porcelain)" ] \
  || { git status --short >&2; die "构建产生未解释的 tracked 改动（数据未提交？）"; }

# ---- 步骤 4：agent-api 生产运行包 ----
echo "[4/6] agent-api 生产包（npm ci --omit=dev）"
PKG="$(mktemp -d)/agent-api"
cp -R services/agent-api "$PKG"
rm -rf "$PKG/node_modules" "$PKG/dist"
(cd "$PKG" && npm ci --omit=dev --silent)

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
rsync -a --delete data/public/v1/ "$OUT/data/"
mkdir -p "$OUT/agent-api"
cp -R "$PKG/dist" "$PKG/package.json" "$PKG/package-lock.json" "$PKG/node_modules" "$OUT/agent-api/"

# ---- 步骤 6：manifest ----
echo "[6/6] manifest"
BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 pipeline/scripts/release_manifest.py build --root "$OUT" --rid "$RID" \
  --git-commit "$GIT_SHA" --git-ts "$GIT_TS" \
  --dataset-version "$DS_VER" --data-through "$DATA_THROUGH" \
  --built-at "$BUILT_AT"
python3 pipeline/scripts/release_manifest.py verify --root "$OUT"

echo "✓ release $RID → $OUT"
echo "  datasetVersion=$DS_VER dataThrough=$DATA_THROUGH commit=$(git rev-parse --short "$COMMIT")"
