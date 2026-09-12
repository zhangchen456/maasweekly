#!/usr/bin/env python3
"""archive-source-changes.py：离线回填与校验入口（Task 01）。

用法：
  python3 pipeline/scripts/archive-source-changes.py            # 回填全部合法日期
  python3 pipeline/scripts/archive-source-changes.py --check    # 只校验不写入
  python3 pipeline/scripts/archive-source-changes.py --diff-dir X --archive-root Y --registry Z

行为：
- 扫描 --diff-dir 下全部合法日期命名的 diff JSON（不限于 KEEP_DAYS 窗口）
- 每个文件：status=changed 的来源经 registry 映射后归档；
  unchanged 且已有条目 → withdrawn（明确语义，不是抓取缺失）
- 身份冲突/未映射来源/JSON 损坏 → 非零退出，旧档案不动
- 同一输入幂等：第二次运行无任何文件变化
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))

from diff_clean import filter_and_pair  # noqa: E402
from record_archive import (  # noqa: E402
    ArchiveError,
    build_index,
    build_record,
    load_registry,
    make_permalink,
    make_record_id,
    merge_record,
    resolve_source_id,
    validate_archive,
    withdraw_record,
)

DEFAULT_DIFF_DIR = BASE / "data" / "diff"
DEFAULT_ARCHIVE_ROOT = BASE / "data"
DEFAULT_REGISTRY = BASE / "pipeline" / "config" / "source_registry.json"


def is_valid_date_name(stem: str) -> bool:
    try:
        datetime.strptime(stem, "%Y-%m-%d")
        return True
    except ValueError:
        return False







def process_diff_file(path: Path, registry: dict, records_root: Path,
                      revisions_root: Path) -> dict:
    """单文件处理（保留兼容；走 record_archive 公共管线）。"""
    from record_archive import load_and_validate_diff, plan_records, apply_plan
    data, date = load_and_validate_diff(path, registry)
    ops = plan_records(data, date, path, registry)
    return apply_plan(ops, records_root, revisions_root)


def main() -> int:
    ap = argparse.ArgumentParser(description="来源变化条目离线归档")
    ap.add_argument("--diff-dir", type=Path, default=DEFAULT_DIFF_DIR)
    ap.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--check", action="store_true",
                    help="只检查输入、身份、归档与版本引用，不写入")
    args = ap.parse_args()

    records_root = args.archive_root / "records"
    revisions_root = args.archive_root / "record-revisions"

    try:
        registry = load_registry(args.registry)
    except ArchiveError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    # --check：校验现有归档一致性 + 输入可映射性（不写入）
    if args.check:
        errors = validate_archive(records_root, revisions_root) \
            if records_root.exists() else []
        # 输入侧：全部 diff 的来源组合必须可映射（dry-run，不写）
        files = sorted(args.diff_dir.glob("*.json"))
        checked, skipped = 0, 0
        for f in files:
            if not is_valid_date_name(f.stem):
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                errors.append(f"diff 文件损坏: {f}: {e}")
                continue
            checked += 1
            seen = set()
            for c in data.get("changes", []):
                if c.get("status") not in ("changed", "unchanged"):
                    continue
                sid = resolve_source_id(registry, c.get("platform", ""),
                                        c.get("source_type", ""), c.get("url"))
                key = sid
                if key in seen:
                    errors.append(f"同日同 source_id 多条输入: {f.name} {sid}")
                seen.add(key)
        if errors:
            print(f"✗ 校验失败（{len(errors)} 项）：", file=sys.stderr)
            for e in errors[:20]:
                print(f"  - {e}", file=sys.stderr)
            return 1
        n_records = len(list(records_root.glob('obs_*.json'))) if records_root.exists() else 0
        print(f"✓ 校验通过：{checked} 个日期输入可映射，{n_records} 条归档一致")
        return 0

    # 常规回填（R2：先校验全部输入，全部通过后一次性应用）
    from record_archive import plan_and_apply, set_prefilter
    set_prefilter(filter_and_pair)
    try:
        result = plan_and_apply(args.diff_dir, registry,
                                records_root, revisions_root)
    except ArchiveError as e:
        print(f"✗ {e}", file=sys.stderr)
        print("  归档中止；修复错误后可重跑。输入与归档预检在写入前完成。", file=sys.stderr)
        return 1
    processed = result.pop("processed")
    skipped_nondate = result.pop("skipped_nondate")
    totals = result

    # 生成索引（默认仓库路径写 site；外部 archive-root 写在 archive 内，测试隔离）
    index = build_index(records_root) if records_root.exists() else []
    if args.archive_root == DEFAULT_ARCHIVE_ROOT:
        index_file = BASE / "site" / "src" / "data" / "record-index.json"
    else:
        index_file = args.archive_root / "record-index.json"
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"归档完成：{processed} 个日期（跳过非日期文件 {skipped_nondate} 个），"
          f"新建 {totals['created']} / 修订 {totals['updated']} / "
          f"幂等 {totals['unchanged']} / 撤回 {totals['withdrawn']}"
          f"；索引 {len(index)} 条 -> {index_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
