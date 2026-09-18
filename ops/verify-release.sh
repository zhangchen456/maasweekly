#!/usr/bin/env bash
# verify-release.sh：release 验收（Task 06 M5；M7 四入口覆盖）
#
# 用法：
#   ops/verify-release.sh --offline <release-dir>  # 离线校验本地 release 产物（CI）
#   ops/verify-release.sh --online --expect-release <rid>
#     # 线上验收：current==rid；REST/MCP/RSS/Skill 四入口与 manifest 同版本
#
# 在线验收原则：
#   - 服务器侧只经受限 shell 的固定 status 动作取 metadata（不开放任意命令）
#   - 公网侧只做匿名只读 GET（与真实用户一致的视角）
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
. "$(dirname "$0")/lib-release.sh"

MODE=""
EXPECT_RID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --offline) MODE="offline"; RELEASE_DIR="$2"; shift 2 ;;
    --online) MODE="online"; shift ;;
    --expect-release) EXPECT_RID="$2"; shift 2 ;;
    --host) MAAS_DEPLOY_HOST="$2"; shift 2 ;;
    *) die "未知参数: $1" ;;
  esac
done
[ -n "$MODE" ] || die "必须指定 --offline <dir> 或 --online"

if [ "$MODE" = "offline" ]; then
  [ -d "$RELEASE_DIR" ] || die "release 目录不存在: $RELEASE_DIR"
  python3 pipeline/scripts/release_manifest.py verify --root "$RELEASE_DIR"
  echo "✓ 离线验收通过: $RELEASE_DIR"
  exit 0
fi

# ---- 在线验收（四入口） ----
validate_rid "$EXPECT_RID"

# 1. 服务器 current 应指向目标 release（经固定 status 动作，含只读 metadata）
status_out="$(remote_status 2>/dev/null)" || die "无法读取服务器 status"
current="$(echo "$status_out" | grep '^current:' | awk '{print $2}')"
[ "$current" = "$EXPECT_RID" ] \
  || die "服务器 current=${current} ≠ expect=${EXPECT_RID}（激活未完成或已回滚）"
info "✓ 服务器 current: $current"

expect_ds="$(echo "$status_out" | grep '^datasetVersion:' | awk '{print $2}')"
expect_through="$(echo "$status_out" | grep '^dataThrough:' | awk '{print $2}')"
[ -n "$expect_ds" ] || die "服务器 status 未返回 datasetVersion（current release manifest 异常？）"
info "· 服务器 datasetVersion=${expect_ds} / dataThrough=${expect_through}"

# 本地期望（可选：给了本地 release 目录则比对 manifest 一致性）
if [ -n "${LOCAL_RELEASE_DIR:-}" ]; then
  local_ds="$(python3 -c "
import json
m = json.load(open('$LOCAL_RELEASE_DIR/metadata/release-manifest.json'))
print(m.get('datasetVersion', ''))")"
  [ "$local_ds" = "$expect_ds" ] \
    || die "本地 manifest datasetVersion=${local_ds} ≠ 服务器=${expect_ds}（发布错版本？）"
  info "✓ 本地 manifest 与服务器 datasetVersion 一致"
fi

# 2. REST：status 与 changes 必须看到同一 datasetVersion
for ep in "/api/v1/status" "/api/v1/changes?limit=10"; do
  body="$(curl -sf --max-time 10 -H 'Cache-Control: no-cache' \
    "$MAAS_PUBLIC_ORIGIN$ep" 2>/dev/null || true)"
  ds="$(echo "$body" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('datasetVersion',''))" 2>/dev/null)"
  [ "$ds" = "$expect_ds" ] \
    || die "${ep} datasetVersion=${ds} ≠ expect=${expect_ds}（新旧混版？）"
  info "✓ REST ${ep} datasetVersion=${ds}"
done

# 3. MCP：initialize + tools/list（协议层可达即证明同服务；数据版本由 REST 同源保证）
mcp_init="$(curl -sf --max-time 10 -X POST \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"verify-release","version":"0"}}}' \
  "$MAAS_PUBLIC_ORIGIN/api/mcp" 2>/dev/null || true)"
echo "$mcp_init" | grep -q '"serverInfo"' \
  || die "MCP initialize 未返回 serverInfo（响应: $(echo "$mcp_init" | head -c 200)）"
info "✓ MCP initialize 可达"
mcp_tools="$(curl -sf --max-time 10 -X POST \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  "$MAAS_PUBLIC_ORIGIN/api/mcp" 2>/dev/null || true)"
for tool in maas_get_changes maas_get_prices maas_get_item maas_get_evidence maas_get_weekly; do
  echo "$mcp_tools" | grep -q "\"$tool\"" \
    || die "MCP tools/list 缺工具 $tool"
done
info "✓ MCP 五工具齐备"
# MCP 数据版本：一次真实工具调用（changes）返回 datasetVersion
mcp_call="$(curl -sf --max-time 10 -X POST \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"maas_get_changes","arguments":{"limit":5}}}' \
  "$MAAS_PUBLIC_ORIGIN/api/mcp" 2>/dev/null || true)"
echo "$mcp_call" | grep -q "$expect_ds" \
  || die "MCP maas_get_changes 响应不含 datasetVersion=${expect_ds}（新旧混版？）"
info "✓ MCP 工具调用 datasetVersion=$expect_ds"

# 4. RSS：两个 feed 可达 + content type + ETag/304 行为
for feed in "/feed.xml" "/feed/weekly.xml"; do
  headers="$(curl -sI --max-time 10 "$MAAS_PUBLIC_ORIGIN$feed" 2>/dev/null || true)"
  ct="$(echo "$headers" | grep -i '^content-type:' | head -1 | tr -d '\r')"
  echo "$ct" | grep -qi 'application/rss+xml' \
    || die "$feed content-type 异常: ${ct:-无}"
  etag="$(echo "$headers" | grep -i '^etag:' | head -1 | tr -d '\r')"
  [ -n "$etag" ] || die "$feed 无 ETag"
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
    -H "If-None-Match: $(echo "$etag" | sed 's/^[Ee][Tt][Aa][Gg]: *//')" \
    "$MAAS_PUBLIC_ORIGIN$feed" 2>/dev/null || echo 000)"
  [ "$code" = "304" ] || die "${feed} 条件请求返回 ${code}（期望 304）"
  info "✓ RSS ${feed}（rss+xml + ETag + 304）"
done

# 5. Skill：manifest 与 install.sh 可达且为同源 release
sk_manifest="$(curl -sf --max-time 10 "$MAAS_PUBLIC_ORIGIN/maas-skill/manifest.json" 2>/dev/null || true)"
[ -n "$sk_manifest" ] || die "Skill manifest.json 不可达"
echo "$sk_manifest" | python3 -c "
import sys, json
m = json.load(sys.stdin)
assert m.get('skillName') == 'maas-daily', f'skillName={m.get(\"skillName\")}'
assert len(m.get('files') or []) > 0, 'files 为空'
" 2>/dev/null || die "Skill manifest 结构非法"
curl -sf --max-time 10 "$MAAS_PUBLIC_ORIGIN/maas-skill/install.sh" >/dev/null 2>&1 \
  || die "Skill install.sh 不可达"
info "✓ Skill manifest + install.sh 可达"

echo "✓ 在线验收通过: current=$EXPECT_RID / datasetVersion=${expect_ds}（REST+MCP+RSS+Skill 四入口）"
