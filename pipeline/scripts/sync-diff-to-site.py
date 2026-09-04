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
      "changed": [ {platform, source_type, url, status, kind, pairs,
                    added_count, removed_count, added_lines, removed_lines,
                    signal_preview, ...} ],   # 经 diff_clean 降噪/配对
      "first_fetch": [...],
      "failed": [...]
    }
  ]
}

只保留最近 N 天（默认 14），全量历史在 data/diff/。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))
from diff_clean import filter_and_pair, humanize_line  # noqa: E402

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
        # 降噪 + 配对 + 分类（substantive/jitter）；高亮预览行做语义化转写
        changed = []
        for c in changes:
            if c.get("status") != "changed":
                continue
            e = filter_and_pair(c)
            if e["signal_preview"]:
                e["signal_preview"] = humanize_line(e["signal_preview"])
            changed.append(e)
        # 实质变化在前，常规抖动在后（同 kind 内保持原顺序）
        changed.sort(key=lambda e: 0 if e["kind"] == "substantive" else 1)
        failed = [c for c in changes if c.get("status") == "fetch_failed"]
        first = [c for c in changes if c.get("status") == "first_fetch"]
        days.append({
            "date": data.get("date", f.stem),
            "stats": data.get("stats", {}),
            "changed": changed,
            "first_fetch": first,
            "failed": failed,
        })

    # 保留已有 highlights（llm-digest.py 产出，按日期幂等）
    try:
        prev = json.loads(DST_FILE.read_text(encoding="utf-8"))
        prev_hl = {d["date"]: d.get("highlights") for d in prev.get("days", []) if d.get("highlights")}
    except (FileNotFoundError, json.JSONDecodeError):
        prev_hl = {}
    for d in days:
        if d["date"] in prev_hl:
            d["highlights"] = prev_hl[d["date"]]

    out = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
    }
    DST_FILE.parent.mkdir(parents=True, exist_ok=True)
    DST_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    total_changed = sum(len(d["changed"]) for d in days)
    total_sub = sum(1 for d in days for c in d["changed"] if c["kind"] == "substantive")
    print(f"Done: {len(days)} days, {total_changed} changed items ({total_sub} substantive) -> {DST_FILE}")


if __name__ == "__main__":
    main()
