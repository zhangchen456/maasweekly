#!/usr/bin/env python3
"""把 data/diff/*.json 聚合成站点"每日动态"数据源。

输入: data/diff/YYYY-MM-DD.json (fetch_sources.py 产出)
输出: site/src/data/daily_changes.json

结构:
{
  "updated_at": "...",
  "days": [
    {
      "date": "2026-09-04",
      "stats": {...},
      "changed": [ {platform, source_type, url, status, added_count, removed_count, added_lines, removed_lines} ],
      "failed":  [...]
    }
  ]
}

只保留最近 N 天（默认 14），全量历史在 data/diff/。
"""
import json
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # repo root
DIFF_DIR = BASE / "data" / "diff"
DST_FILE = BASE / "site" / "src" / "data" / "daily_changes.json"
KEEP_DAYS = 14


def main():
    if not DIFF_DIR.exists():
        print(f"diff 目录不存在: {DIFF_DIR}")
        return

    files = sorted(DIFF_DIR.glob("*.json"), reverse=True)
    # 只取文件名是合法日期的
    valid = []
    for f in files:
        try:
            datetime.strptime(f.stem, "%Y-%m-%d")
            valid.append(f)
        except ValueError:
            continue

    days = []
    for f in valid[:KEEP_DAYS]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        changes = data.get("changes", [])
        changed = [c for c in changes if c.get("status") == "changed"]
        failed = [c for c in changes if c.get("status") == "fetch_failed"]
        first = [c for c in changes if c.get("status") == "first_fetch"]
        days.append({
            "date": data.get("date", f.stem),
            "stats": data.get("stats", {}),
            "changed": changed,
            "first_fetch": first,
            "failed": failed,
        })

    out = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
    }
    DST_FILE.parent.mkdir(parents=True, exist_ok=True)
    DST_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    total_changed = sum(len(d["changed"]) for d in days)
    print(f"Done: {len(days)} days, {total_changed} changed items -> {DST_FILE}")


if __name__ == "__main__":
    main()
