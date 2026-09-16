#!/usr/bin/env python3
"""validate-price-archive.py：价格归档构建门禁（Task 02）。

npm run build 的 prebuild 钩子调用（与 validate-archive.py 链式）。
检查项（全部为硬门禁，缺归档时允许空跑——首跑前仓库无 data/price-*）：
1. data/price-* 各目录 JSON 可解析、文件名=id、id 与内容匹配
2. 事件修订链完整、版本/证据引用不悬空、excerpt_hash 复核
3. price-record-index.json / price-evidence-index.json 双向一致
4. evidence 页路由所需的证据文件完整
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "pipeline"))

from pricing import archive as pa  # noqa: E402

DATA_ROOT = BASE / "data"
PRICE_INDEX = BASE / "site" / "src" / "data" / "price-record-index.json"
EVIDENCE_INDEX = BASE / "site" / "src" / "data" / "price-evidence-index.json"


def main() -> int:
    has_versions = (DATA_ROOT / pa.DIR_FACT_VERSIONS).exists()
    has_records = (DATA_ROOT / pa.DIR_PRICE_RECORDS).exists()
    if not has_versions and not has_records:
        print("✓ 价格归档门禁通过：无归档（尚未首跑，允许空跑）")
        return 0

    price_index = None
    if PRICE_INDEX.exists():
        try:
            price_index = json.loads(PRICE_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"✗ 构建门禁失败: price-record-index.json 损坏: {e}",
                  file=sys.stderr)
            return 1
    evidence_index = None
    if EVIDENCE_INDEX.exists():
        try:
            evidence_index = json.loads(EVIDENCE_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"✗ 构建门禁失败: price-evidence-index.json 损坏: {e}",
                  file=sys.stderr)
            return 1

    errors = pa.validate_price_archive(
        DATA_ROOT,
        versions_root=DATA_ROOT / pa.DIR_FACT_VERSIONS,
        evidence_root=DATA_ROOT / pa.DIR_EVIDENCE,
        snapshots_root=DATA_ROOT / pa.DIR_SNAPSHOTS,
        records_root=DATA_ROOT / pa.DIR_PRICE_RECORDS,
        revisions_root=DATA_ROOT / pa.DIR_PRICE_REVISIONS,
        current_file=DATA_ROOT / pa.DIR_CURRENT,
        runs_root=DATA_ROOT / pa.DIR_RUNS,
        price_index=price_index,
        evidence_index=evidence_index,
    )
    if errors:
        print(f"✗ 价格归档门禁失败（{len(errors)} 项，构建中止）:", file=sys.stderr)
        for e in errors[:20]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    n_records = len(list((DATA_ROOT / pa.DIR_PRICE_RECORDS).glob("price_*.json")))
    n_evidence = len(list((DATA_ROOT / pa.DIR_EVIDENCE).glob("ev_*.json")))
    print(f"✓ 价格归档门禁通过：{n_records} 事件 / {n_evidence} 证据，"
          f"修订链与引用完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
