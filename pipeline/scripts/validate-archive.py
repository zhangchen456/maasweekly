#!/usr/bin/env python3
"""validate-archive.py：构建前归档门禁（Task 01 / R1）。

npm run build 的 prebuild 钩子调用本脚本。任何归档/索引/修订不一致
→ 非零退出，Astro 构建不执行——不生成"成功但没有详情页"的站点。

检查项（全部为硬门禁）：
1. data/records 与 data/record-revisions 目录存在且非空（首次无归档时允许空跑，
   但 record-index.json 存在时必须双向一致）
2. record-index.json 存在且与归档双向完整（id/字段级比对，不只数量）
3. validate_archive 全量通过（JSON 解析/身份/修订链/最新修订↔当前一致）
4. 详情路由所需的修订引用完整
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))

from record_archive import validate_archive  # noqa: E402

RECORDS = BASE / "data" / "records"
REVISIONS = BASE / "data" / "record-revisions"
INDEX = BASE / "site" / "src" / "data" / "record-index.json"


def main() -> int:
    errors: list[str] = []

    # 1) 索引必须存在（sync 产物；缺失说明链路断裂）
    if not INDEX.exists():
        print("✗ 构建门禁失败: site/src/data/record-index.json 不存在——"
              "请先运行 sync-diff-to-site.py（缺失索引时拒绝构建，"
              "防止生成无详情页的悬空链接站点）", file=sys.stderr)
        return 1
    try:
        index = json.loads(INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ 构建门禁失败: record-index.json 损坏: {e}", file=sys.stderr)
        return 1

    # 2) 归档目录状态
    if not RECORDS.exists() or not list(RECORDS.glob("obs_*.json")):
        if index:
            print("✗ 构建门禁失败: 索引有 {len(index)} 条但 data/records 为空——"
                  "详情页将全部缺失", file=sys.stderr)
            return 1
        # 索引与归档都空：允许（尚未开始归档的仓库）
        print("✓ 构建门禁通过：无归档（索引也为空）")
        return 0

    if not REVISIONS.exists():
        print("✗ 构建门禁失败: data/record-revisions 不存在", file=sys.stderr)
        return 1

    # 3) 全量一致性（含索引双向字段比对）
    errors = validate_archive(RECORDS, REVISIONS, index_items=index)
    if errors:
        print(f"✗ 构建门禁失败（{len(errors)} 项，构建中止）:", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        return 1

    n = len(list(RECORDS.glob('obs_*.json')))
    print(f"✓ 构建门禁通过：{n} 条记录 / 索引 {len(index)} 条一致，修订链完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
