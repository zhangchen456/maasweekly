#!/usr/bin/env python3
"""把 data/diff/*.json 聚合成站点"每日动态"数据源。

输入: data/diff/YYYY-MM-DD.json (fetch_sources.py 产出)
输出:
  1. site/src/data/daily_changes.json —— 每日明细（最近 KEEP_DAYS 天）
  2. site/src/data/weekly-digest.json —— 按 ISO 周聚合的归档索引

daily_changes.json 结构:
{
  "updated_at": "...",
  "days": [
    {
      "date": "2026-09-04",
      "stats": {...},
      "changed": [ {platform, source_type, url, status, kind, pairs,
                    added_count, removed_count, added_lines, removed_lines,
                    signal_preview, ...} ],   # 经 diff_clean 降噪/配对
      "highlights": [...],                   # llm-digest.py 产出
      "first_fetch": [...],
      "failed": [...]
    }
  ]
}

weekly-digest.json 结构（按周倒序）:
[
  {
    "week": "2026-W36", "start": "2026-08-31", "end": "2026-09-06",
    "days": {"2026-09-02": {substantive, jitter, failed, releases, pricings, sunsets}},
    "totals": {substantive, releases, pricings, sunsets},
    "highlights": [...]    # 当周全部每日要点（按日拼接）
  }
]
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))
from diff_clean import filter_and_pair, humanize_line  # noqa: E402
from record_archive import (  # noqa: E402
    ArchiveError,
    build_index as archive_build_index,
    build_record as archive_build_record,
    load_registry as archive_load_registry,
    make_record_id,
    make_permalink,
    merge_record,
    load_and_validate_diff, plan_records, apply_plan, set_prefilter,
    resolve_source_id,
)

DIFF_DIR = BASE / "data" / "diff"
DST_FILE = BASE / "site" / "src" / "data" / "daily_changes.json"
WEEKLY_FILE = BASE / "site" / "src" / "data" / "weekly-digest.json"
KEEP_DAYS = 60


def iso_week(d: str) -> tuple:
    """日期字符串 -> (ISO 周标识 "2026-W36", 周一日期, 周日日期)。"""
    dt = datetime.strptime(d, "%Y-%m-%d").date()
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return (f"{monday.isocalendar()[0]}-W{monday.isocalendar()[1]:02d}",
            monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d"))


def build_weekly(days: list) -> list:
    """把每日数据按 ISO 周聚合。"""
    weeks = {}
    for d in days:
        # ISO 周跨年时 isocalendar 年份可能与日期年份不同，标识统一用周一所在 ISO 年
        wk, start, end = iso_week(d["date"])
        w = weeks.setdefault(wk, {
            "week": wk, "start": start, "end": end, "days": {}, "totals": {},
            "highlights": [],
        })
        substantive = [c for c in d.get("changed", []) if c.get("kind") == "substantive"]
        jitter = [c for c in d.get("changed", []) if c.get("kind") == "jitter"]
        hl = d.get("highlights") or []
        # v3 highlights 是平台分组结构 [{platform, logo_summary, items:[{text,type}]}]，
        # 展平为 item 级再统计/拼接
        flat = []
        for h in hl:
            for item in h.get("items", []):
                flat.append({"platform": h.get("platform"), "date": d["date"],
                             "text": item.get("text"), "type": item.get("type")})
        w["days"][d["date"]] = {
            "substantive": len(substantive),
            "jitter": len(jitter),
            "failed": len(d.get("failed", [])),
            "releases": sum(1 for h in flat if h.get("type") == "release"),
            "pricings": sum(1 for h in flat if h.get("type") == "pricing"),
            "sunsets": sum(1 for h in flat if h.get("type") == "sunset"),
        }
        w["highlights"].extend(flat)
    # 汇总
    for w in weeks.values():
        w["totals"] = {
            "substantive": sum(v["substantive"] for v in w["days"].values()),
            "releases": sum(v["releases"] for v in w["days"].values()),
            "pricings": sum(v["pricings"] for v in w["days"].values()),
            "sunsets": sum(v["sunsets"] for v in w["days"].values()),
        }
    return sorted(weeks.values(), key=lambda w: w["start"], reverse=True)


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

    # ---- Task 01：归档合并（扫描全部历史 diff，不限窗口） ----
    RECORDS_ROOT = BASE / "data" / "records"
    REVISIONS_ROOT = BASE / "data" / "record-revisions"
    try:
        registry = archive_load_registry(BASE / "pipeline" / "config" / "source_registry.json")
    except Exception as e:  # noqa: BLE001 —— registry 问题是硬错误
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    # 全部日期先读取、映射并生成计划；此阶段不写任何归档或站点文件。
    loaded, ops = [], []
    set_prefilter(filter_and_pair)
    try:
        for f in valid:
            data, date = load_and_validate_diff(f, registry)
            loaded.append((f, data))
            ops.extend(plan_records(data, date, f, registry))
    except ArchiveError as e:
        print(f"✗ {e}；输入预检失败，未写入任何内容", file=sys.stderr)
        sys.exit(1)

    days = []
    for f, data in loaded:
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

        # 注入稳定 ID 与 permalink 到近期 changed 条目
        for c in changed:
            try:
                sid = resolve_source_id(registry, c.get("platform", ""),
                                        c.get("source_type", ""), c.get("url"))
            except Exception:  # noqa: BLE001 —— 防御性兜底（预检已保证不发生）
                continue
            rid = make_record_id(sid, data.get("date", f.stem))
            c["id"] = rid
            c["permalink"] = make_permalink(rid)

        days.append({
            "date": data.get("date", f.stem),
            "stats": data.get("stats", {}),
            "changed": changed,
            "first_fetch": first,
            "failed": failed,
        })

    # Task 01：归档后近期列表截回 KEEP_DAYS 窗口（归档本身保留全部日期）
    days = days[:KEEP_DAYS]

    # 保留已有 highlights 和 llm_summary（llm-digest.py 产出，按日期幂等）
    try:
        prev = json.loads(DST_FILE.read_text(encoding="utf-8"))
        prev_days = {d["date"]: d for d in prev.get("days", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        prev_days = {}
    for d in days:
        pd = prev_days.get(d["date"])
        if not pd:
            continue
        if pd.get("highlights"):
            d["highlights"] = pd["highlights"]
        # 价格变化事件（fetch-prices.py 产出，按日期幂等保留）
        if pd.get("price_changes"):
            d["price_changes"] = pd["price_changes"]
        # 信源级 LLM 解读挂回重建的 changed 条目
        prev_sum = {f"{c.get('platform')}|{c.get('source_type')}": c.get("llm_summary")
                    for c in pd.get("changed", []) if c.get("llm_summary")}
        if prev_sum:
            for c in d["changed"]:
                key = f"{c.get('platform')}|{c.get('source_type')}"
                if key in prev_sum:
                    c["llm_summary"] = prev_sum[key]
                    # 将 LLM 摘要纳入同一批次，避免预检后另行修改归档。
                    for op in ops:
                        if op["op"] == "merge" and op["record"]["id"] == c.get("id"):
                            op["record"]["summary"] = c["llm_summary"]
                            op["record"]["summaryOrigin"] = "llm"

    try:
        apply_plan(ops, RECORDS_ROOT, REVISIONS_ROOT)
    except ArchiveError as e:
        print(f"✗ 同步中止: {e}", file=sys.stderr)
        sys.exit(1)

    out = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
    }
    DST_FILE.parent.mkdir(parents=True, exist_ok=True)
    DST_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 周聚合归档
    weekly = build_weekly(days)
    # 保留已有周度串讲（llm-weekly-digest.py 产出，按周幂等）
    try:
        prev_w = json.loads(WEEKLY_FILE.read_text(encoding="utf-8"))
        prev_story = {w["week"]: w.get("story") for w in prev_w if w.get("story")}
    except (FileNotFoundError, json.JSONDecodeError):
        prev_story = {}
    for w in weekly:
        if w["week"] in prev_story:
            w["story"] = prev_story[w["week"]]
    WEEKLY_FILE.write_text(json.dumps(weekly, ensure_ascii=False, indent=2), encoding="utf-8")

    # Task 01：record-index.json（可重建索引；持久源为 data/records 与 revisions）
    from pathlib import Path as _P
    RECORDS_ROOT.mkdir(parents=True, exist_ok=True)
    index = archive_build_index(RECORDS_ROOT)
    INDEX_FILE = BASE / "site" / "src" / "data" / "record-index.json"
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    # 构建前校验：索引引用必须与归档一致
    from record_archive import validate_archive
    errors = validate_archive(RECORDS_ROOT, REVISIONS_ROOT)
    if errors:
        print(f"✗ 归档校验失败（{len(errors)} 项，不构建）：", file=sys.stderr)
        for e in errors[:10]:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    total_changed = sum(len(d["changed"]) for d in days)
    total_sub = sum(1 for d in days for c in d["changed"] if c["kind"] == "substantive")
    print(f"Done: {len(days)} days, {total_changed} changed items ({total_sub} substantive), "
          f"{len(weekly)} weeks -> {DST_FILE.name} + {WEEKLY_FILE.name}")


if __name__ == "__main__":
    main()
