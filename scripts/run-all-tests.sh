#!/usr/bin/env bash
# run-all-tests.sh：Task 01–06 统一回归入口（复验 P1c）。
#
# 供开发、release builder（步骤 2）与 CI 共用——真实退出码逐项判断，
# 失败输出测试名与关键日志（不吞完整日志、不 grep 文本判断成功）。
#
# 用法：
#   scripts/run-all-tests.sh            # 全量
#   scripts/run-all-tests.sh --quick   # 跳过 site build 重型段（开发迭代用；
#                                       # release/CI 禁用——见 build-release.sh）
set -uo pipefail
BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"

QUICK=false
[ "${1:-}" = "--quick" ] && QUICK=true

FAILED=()
PASS=0

SUITE_LOG_PARENT="${MAAS_REGRESSION_LOG_ROOT:-${TMPDIR:-/tmp}}"
mkdir -p "$SUITE_LOG_PARENT" || exit 2
SUITE_LOG_DIR="$(mktemp -d "$SUITE_LOG_PARENT/maas-regression.XXXXXX")" || exit 2
SUITE_FINISHED=false
TEST_INDEX=0
cleanup() {
  if $SUITE_FINISHED && [ "${#FAILED[@]}" -eq 0 ]; then
    rm -rf "$SUITE_LOG_DIR"
  else
    echo "回归未通过或中断，日志保留: $SUITE_LOG_DIR"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run() {  # run <名称> <命令...>
  local name="$1"; shift
  echo "── $name"
  TEST_INDEX=$((TEST_INDEX + 1))
  local log="$SUITE_LOG_DIR/$TEST_INDEX.txt" code=0
  "$@" > "$log" 2>&1 || code=$?
  if [ "$code" -eq 0 ]; then
    PASS=$((PASS + 1))
    echo "   ✓ $name"
    rm -f "$log"
  else
    FAILED+=("$name")
    echo "   ✗ ${name}（退出码 ${code}）——完整失败日志："
    printf 'suite=%s\nexitCode=%s\n' "$name" "$code" > "$log.meta"
    sed 's/^/     /' "$log"
    echo "   （完整日志: ${log}）"
  fi
}

echo "══ Task 01–06 统一回归 ══"

# ---- Lockfile/toolchain/platform dependency validation ----
if ! $QUICK; then
  run "site dependency cache" node scripts/ensure-node-deps.mjs site
  run "agent-api dependency cache" node scripts/ensure-node-deps.mjs services/agent-api
fi

# ---- 归档与导出门禁 ----
run "export-public-data --check" python3 pipeline/scripts/export-public-data.py --check
run "validate-archive（Task 01）" python3 pipeline/scripts/validate-archive.py
run "validate-price-archive（Task 02）" python3 pipeline/scripts/validate-price-archive.py --check
run "build-skill-package --check" python3 site/scripts/build-skill-package.py --check

# ---- Python 测试 ----
run "test_release_retention（live references）" python3 -m unittest discover -s tests -p 'test_release_retention.py'
run "test_operations_budget（production resource thresholds）" python3 -m unittest discover -s tests -p 'test_operations_budget.py'
run "test_public_retention（公开历史引用完整性）" python3 -m unittest discover -s tests -p 'test_public_retention.py'
run "test_cross_platform（关系与官方价格）" python3 -m unittest discover -s tests -p 'test_cross_platform.py'
run "test_regression_diagnostics（CI failure evidence）" python3 -m unittest discover -s tests -p 'test_regression_diagnostics.py'
run "test_current_pricing（official table drift）" python3 -m unittest discover -s tests -p 'test_current_pricing.py'
run "test_record_archive（Task 01）" python3 -m unittest discover -s tests -p 'test_record_archive.py'
run "test_price_archive（Task 02）" python3 -m unittest discover -s tests -p 'test_price_archive.py'
run "test_public_export（Task 03）" python3 -m unittest discover -s tests -p 'test_public_export.py'
run "test_skill_package（Task 04）" python3 -m unittest discover -s tests -p 'test_skill_package.py'
run "test_release_build（Task 06）" python3 -m unittest discover -s tests -p 'test_release_build.py'
run "test_release_activation（Task 06）" python3 -m unittest discover -s tests -p 'test_release_activation.py'
run "test_deploy_mode（Task 06 M7）" python3 -m unittest discover -s tests -p 'test_deploy_mode.py'
run "test_model_identity_audit（Task 07）" python3 -m unittest discover -s tests -p 'test_model_identity_audit.py'
run "test_model_public_projection（Task 07）" python3 -m unittest discover -s tests -p 'test_model_public_projection.py'
run "test_model_registry（Task 07）" python3 -m unittest discover -s tests -p 'test_model_registry.py'
run "validate-model-registry（Task 07）" python3 pipeline/scripts/validate-model-registry.py --check
run "audit-model-registry-coverage（Task 07）" python3 pipeline/scripts/audit-model-registry-coverage.py --output "$SUITE_LOG_DIR/coverage-audit.json"
run "test_architecture_workflows（AR-05）" python3 -m unittest discover -s tests -p 'test_architecture_workflows.py'
run "test_architecture_observability（AR-08）" python3 -m unittest discover -s tests -p 'test_architecture_observability.py'
run "test_blob_storage（AR-06）" python3 -m unittest discover -s tests -p 'test_blob_storage.py'
run "test_pipeline_runtime（AR-04）" python3 -m unittest discover -s tests -p 'test_pipeline_runtime.py'
run "test_standard_inputs（AR-03）" python3 -m unittest discover -s tests -p 'test_standard_inputs.py'
run "test_workflow_release_contract（incident 2026-09）" python3 -m unittest discover -s tests -p 'test_workflow_release_contract.py'
run "validate-developer-registry（T07-5.2）" python3 pipeline/scripts/validate-developer-registry.py
run "test_developer_platform_registry（T07-5.2）" python3 -m unittest discover -s tests -p 'test_developer_platform_registry.py'
run "account maintenance" python3 -m unittest discover -s tests -p 'test_account_maintenance.py'
run "test_analytics_foundation（T08-1A）" python3 -m unittest discover -s tests -p 'test_analytics_foundation.py'
run "test_umami_postgres_preflight（T08-1A）" python3 -m unittest discover -s tests -p 'test_umami_postgres_preflight.py'
run "test_umami_prerequisites（T08-1A）" python3 -m unittest discover -s tests -p 'test_umami_prerequisites.py'
run "test_inventory_capability（T08-1A Gate B Preflight）" python3 -m unittest discover -s tests -p 'test_inventory_capability.py'

# ---- site（构建 + 六测试）----
if ! $QUICK; then
  run "site build（含 prebuild 门禁）" bash -c 'cd site && npm run build'
fi
run "site: access-pages（Task 05）" bash -c 'cd site && node --experimental-strip-types tests/access-pages.test.mjs'
run "site: rss（Task 05）" bash -c 'cd site && node --experimental-strip-types tests/rss.test.mjs'
run "site: page ViewModel types" node services/agent-api/node_modules/typescript/bin/tsc --project site/tsconfig.page-models.json
run "site: page ViewModel parity" bash -c 'cd site && node tests/page-models.test.mjs'
run "site: cross-platform" bash -c 'cd site && node tests/cross-platform.test.mjs'
run "site: pricing" bash -c 'cd site && node tests/pricing.test.mjs'
run "site: model-identity-ui（T07-4A）" bash -c 'cd site && node tests/model-identity-ui.test.mjs'
run "site: model-identity-ui-contract（T07-4A）" bash -c 'cd site && node tests/model-identity-ui-contract.test.mjs'
run "site: changes-browser-contract（T07-4A.2）" bash -c 'cd site && node tests/changes-browser-contract.test.mjs'
run "site: changes-browser-ui（T07-4A.2）" bash -c 'cd site && node tests/changes-browser-ui.test.mjs'
run "site: model-detail（T07-4B.2）" bash -c 'cd site && node tests/model-detail.test.mjs'
run "site: browser time zones" bash -c 'cd site && node --test tests/time-display.test.mjs'
run "site: analytics（T08 lightweight）" bash -c 'cd site && node --test tests/analytics.test.mjs'
run "site: agent-interactions（copy regression）" bash -c 'cd site && node --test tests/agent-interactions.test.mjs'
run "site: platform-logos" bash -c 'cd site && node tests/platform-logos.test.mjs'
run "site: leaderboards" bash -c 'cd site && node tests/leaderboards.test.mjs'
run "site: records（含残留检测）" bash -c 'cd site && node tests/records.test.mjs'
# records fixtures now build in a disposable input/output root; formal dist
# never needs a cleanup rebuild, including after interrupted fixture tests.
run "site: SEO（canonical / sitemap / model content）" bash -c 'cd site && node --experimental-strip-types tests/seo.test.mjs'

run "site: multilingual" bash -c 'cd site && node --experimental-strip-types tests/multilingual.test.mjs'

# ---- agent-api（REST + MCP 全套）----
run "agent-api: build" bash -c 'cd services/agent-api && npm run build'
run "agent-api: country" bash -c 'cd services/agent-api && node --test dist/tests/country.test.js'
run "agent-api: REST 测试" bash -c 'cd services/agent-api && npm run test:compiled'
run "agent-api: MCP 测试" bash -c 'cd services/agent-api && npm run test:mcp:compiled'
run "agent-api: MCP 真实数据" bash -c 'cd services/agent-api && npm run test:mcp:real:compiled'

run "site: feedback interaction" bash -c 'cd site && node --test tests/feedback.test.mjs'

# ---- 汇总 ----
echo "══════════════════════════"
echo "通过: $PASS | 失败: ${#FAILED[@]}"
SUITE_FINISHED=true
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "失败项："
  for f in "${FAILED[@]}"; do echo "  ✗ $f"; done
  exit 1
fi
echo "全部通过 ✓"
exit 0
