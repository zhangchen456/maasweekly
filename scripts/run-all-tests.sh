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

run() {  # run <名称> <命令...>
  local name="$1"; shift
  echo "── $name"
  local log
  log="$(mktemp)"
  if "$@" > "$log" 2>&1; then
    PASS=$((PASS + 1))
    echo "   ✓ $name"
  else
    FAILED+=("$name")
    echo "   ✗ ${name}（退出码 $?）——日志关键内容："
    tail -25 "$log" | sed 's/^/     /'
    echo "   （完整日志: ${log}）"
  fi
  rm -f "$log"
}

echo "══ Task 01–06 统一回归 ══"

# ---- 依赖就位（幂等：本地已装则秒过；CI 干净环境必需）----
# run-all-tests 的 site/agent-api 测试假设 node_modules 已存在——本地靠历史
# 安装残留恰好成立，CI 全新环境会 TS2688（@types/node 缺失）。统一在此装齐。
if ! $QUICK; then
  [ -d site/node_modules ] || (cd site && npm ci --silent)
  [ -d services/agent-api/node_modules ] || (cd services/agent-api && npm ci --silent)
fi

# ---- 归档与导出门禁 ----
run "export-public-data --check" python3 pipeline/scripts/export-public-data.py --check
run "validate-archive（Task 01）" python3 pipeline/scripts/validate-archive.py
run "validate-price-archive（Task 02）" python3 pipeline/scripts/validate-price-archive.py --check
run "build-skill-package --check" python3 site/scripts/build-skill-package.py --check

# ---- Python 测试 ----
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
run "audit-model-registry-coverage（Task 07）" python3 pipeline/scripts/audit-model-registry-coverage.py --output /tmp/t07-coverage-audit.json
run "test_workflow_release_contract（incident 2026-09）" python3 -m unittest discover -s tests -p 'test_workflow_release_contract.py'
run "validate-developer-registry（T07-5.2）" python3 pipeline/scripts/validate-developer-registry.py
run "test_developer_platform_registry（T07-5.2）" python3 -m unittest discover -s tests -p 'test_developer_platform_registry.py'

# ---- site（构建 + 六测试）----
if ! $QUICK; then
  run "site build（含 prebuild 门禁）" bash -c 'cd site && npm run build'
fi
run "site: access-pages（Task 05）" bash -c 'cd site && node --experimental-strip-types tests/access-pages.test.mjs'
run "site: rss（Task 05）" bash -c 'cd site && node --experimental-strip-types tests/rss.test.mjs'
run "site: pricing" bash -c 'cd site && node tests/pricing.test.mjs'
run "site: model-identity-ui（T07-4A）" bash -c 'cd site && node tests/model-identity-ui.test.mjs'
run "site: model-identity-ui-contract（T07-4A）" bash -c 'cd site && node tests/model-identity-ui-contract.test.mjs'
run "site: changes-browser-contract（T07-4A.2）" bash -c 'cd site && node tests/changes-browser-contract.test.mjs'
run "site: changes-browser-ui（T07-4A.2）" bash -c 'cd site && node tests/changes-browser-ui.test.mjs'
run "site: model-detail（T07-4B.2）" bash -c 'cd site && node tests/model-detail.test.mjs'
run "site: platform-logos" bash -c 'cd site && node tests/platform-logos.test.mjs'
run "site: leaderboards" bash -c 'cd site && node tests/leaderboards.test.mjs'
run "site: records（含残留检测）" bash -c 'cd site && node tests/records.test.mjs'

# ---- agent-api（REST + MCP 全套）----
run "agent-api: build" bash -c 'cd services/agent-api && npm run build'
run "agent-api: REST 测试" bash -c 'cd services/agent-api && npm test'
run "agent-api: MCP 测试" bash -c 'cd services/agent-api && npm run test:mcp'
run "agent-api: MCP 真实数据" bash -c 'cd services/agent-api && npm run test:mcp:real'

# ---- 汇总 ----
echo "══════════════════════════"
echo "通过: $PASS | 失败: ${#FAILED[@]}"
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "失败项："
  for f in "${FAILED[@]}"; do echo "  ✗ $f"; done
  exit 1
fi
echo "全部通过 ✓"
exit 0
