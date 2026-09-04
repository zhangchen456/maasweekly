#!/usr/bin/env python3
"""从每日 diff JSON 提炼热点事件，更新 site/src/data/live_feeds.json。

提炼逻辑（规则式，按优先级）：

1. 发布事件（release）：
   - changelog 新增行匹配 "Released X" / "X is rolling out" / "X 发布"
   - 或 model_list 出现新模型 ID 行（全小写连字符格式，如 gpt-6-astra）
2. 下线事件（sunset）：
   - 新增/删除行匹配 "下线" / "停服" / "deprecat" / "will be removed" / "sunset"
3. 调价事件（pricing）：
   - pricing 信源有变化 + 行内容含货币符号（$¥€£）且含价格模式（/M 或 per million 或 元/百万）

去重：同一事件（platform + 归一化 title）只保留最新日期。
排序：按日期倒序；live_feeds.json 保留最近 MAX_ITEMS 条（默认 20）。

用法: python3 pipeline/scripts/extract-live-events.py [diff.json 路径 ...]
不传参数时自动处理 data/diff/ 下最近 7 天的 JSON。
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
DIFF_DIR = BASE / "data" / "diff"
FEEDS_FILE = BASE / "site" / "src" / "data" / "live_feeds.json"
LOOKBACK_DAYS = 7
MAX_ITEMS = 20

# 每平台的信源 URL 映射（事件条目里给"来源"链接）
def source_urls(platform, source_type):
    cfg = BASE / "pipeline" / "config" / "maas_official_sources.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return ""
    for p in data.get("platforms", []):
        if p.get("name") == platform or p.get("name_en") == platform:
            return (p.get("sources") or {}).get(source_type) or ""
    return ""


RELEASE_PATTERNS = [
    re.compile(r"Released\s+([A-Za-z0-9][\w.\-]*(?:\s+[A-Za-z0-9][\w.\-]*){0,3})", re.I),
    re.compile(r"([A-Za-z0-9][\w.\-]*(?:\s+[A-Za-z0-9][\w.\-]*){0,3})\s+is rolling out", re.I),
    re.compile(r"announc\w*\s+([A-Z][\w.\-]*(?:\s+[A-Z][\w.\-]*){0,3})\b"),  # 要求词首大写，过滤 "announcements investigating..."
    # 中文：X 发布 / 发布 X / X 上线 / X 开源。要求紧邻上下文（避免长聚合行里跨段误配），
    # 且排除"调整/升级/停服"类动词混入（如"价格调整】DeepSeek-V4 ... 上线"跨【】段落误报）
    re.compile(r"(?:^|】|\s)([A-Za-z0-9][\w.\-]*(?:\s+[A-Za-z0-9][\w.\-]*){0,2})\s*(?:正式)?\s*(发布|上线|开源|推出)"),
    re.compile(r"(?:正式)?(发布|上线|开源|推出)\s*([A-Za-z0-9][\w.\-]*(?:\s+[A-Za-z0-9][\w.\-]*){0,2})"),
]
# 发布语句匹配的常见非模型名噪音
STOP_NAMES = {"we", "our", "the", "new", "an", "a", "api", "claude", "gpt", "now", "today", "update", "updates",
              "released", "general", "availability", "version"}
SUNSET_PATTERNS = [
    re.compile(r"(下线|停服|退役|deprecated|deprecat\w+|will be removed|sunset|discontinu\w+)", re.I),
]
PRICE_LINE = re.compile(r"[¥$€£]\s?\d|元/百万|/MTok|per million", re.I)
MODEL_ID_LINE = re.compile(r"^[a-z][a-z0-9\-]*[a-z0-9]$")


def norm_title(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def extract_from_diff(diff_data):
    """从单个 diff JSON 提炼事件列表。先按平台收集全部候选，再统一聚合。"""
    events = []
    date = diff_data.get("date")
    # platform -> 该平台当日全部候选事件（跨 source_type 聚合）
    by_platform = {}
    for c in diff_data.get("changes", []):
        platform = c.get("platform", "")
        stype = c.get("source_type", "")
        if c.get("status") != "changed":
            continue
        added = c.get("added_lines") or []
        removed = c.get("removed_lines") or []
        all_lines = added + removed
        platform_events = by_platform.setdefault(platform, [])

        # --- 发布事件：changelog / blog 的明确发布语句 ---
        if stype in ("changelog", "blog"):
            for line in added:
                # 超长聚合行是公告列表页快照（整页公告拼成一行），历史公告混在
                # 其中会造成误报（如旧公告"新模型上线 DeepSeek-V3"），跳过
                if len(line) > 200:
                    continue
                for pat in RELEASE_PATTERNS:
                    m = pat.search(line)
                    if not m:
                        continue
                    # 动词前置模式有两个捕获组：group(1)=动词, group(2)=名字
                    if m.group(1) in ("发布", "上线", "开源", "推出") and m.lastindex and m.lastindex >= 2:
                        name = m.group(2)
                    else:
                        name = m.group(1)
                    name = (name or "").strip()
                    if not name or name.lower() in STOP_NAMES or len(name) < 2:
                        continue
                    platform_events.append({
                        "platform": platform,
                        "date": date,
                        "title": f"{name} 发布",
                        "summary": line[:120],
                        "url": c.get("url", ""),
                        "type": "release",
                        "_weight": 3,  # 明确发布语句权重最高
                    })
                    break

        # --- 发布事件兜底：model_list 出现新模型 ID 行 ---
        if stype == "model_list" and not any(e["type"] == "release" for e in platform_events):
            for line in added:
                s = line.strip()
                if MODEL_ID_LINE.match(s) and 4 < len(s) < 40 and "-" in s:
                    platform_events.append({
                        "platform": platform,
                        "date": date,
                        "title": f"{s} 上线模型列表",
                        "summary": f"模型列表新增 {s}，同源共 {len(added)} 行新增",
                        "url": c.get("url", ""),
                        "type": "release",
                        "_weight": 2,
                    })
                    break

        # --- 下线事件 ---
        if not any(e["type"] == "sunset" for e in platform_events):
            for line in all_lines:
                if any(pat.search(line) for pat in SUNSET_PATTERNS):
                    platform_events.append({
                        "platform": platform,
                        "date": date,
                        "title": line[:60],
                        "summary": f"{stype} 页面出现下线/弃用相关变更",
                        "url": c.get("url", ""),
                        "type": "sunset",
                        "_weight": 2,
                    })
                    break

        # --- 调价事件：pricing 页变化且含价格行（同日有发布事件时并入发布条目）---
        if stype == "pricing" and any(PRICE_LINE.search(l) for l in all_lines):
            platform_events.append({
                "platform": platform,
                "date": date,
                "title": f"{platform} 定价页变更",
                "summary": f"定价页 {len(added)} 行新增 / {len(removed)} 行删除，含价格内容",
                "url": c.get("url", ""),
                "type": "pricing",
                "_weight": 1,
            })

    # 每平台聚合：发布事件为该平台主事件，调价并入其 summary；无发布时各事件并列
    for platform, platform_events in by_platform.items():
        releases = [e for e in platform_events if e["type"] == "release"]
        others = [e for e in platform_events if e["type"] != "release"]
        if releases:
            main_e = max(releases, key=lambda e: e["_weight"])
            pricing_e = [e for e in others if e["type"] == "pricing"]
            if pricing_e:
                main_e["summary"] += f"；同日定价页也有变更（{pricing_e[0]['summary']}）"
            events.append(main_e)
            events.extend(e for e in others if e["type"] != "pricing")
        else:
            events.extend(others)

    return events


def main():
    # 输入文件：命令行参数 or 最近 N 天
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    else:
        today = datetime.now().date()
        files = []
        for i in range(LOOKBACK_DAYS):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            f = DIFF_DIR / f"{d}.json"
            if f.exists():
                files.append(f)

    if not files:
        print("没有可处理的 diff JSON")
        return

    # 读取现有 feeds（保留人工写的条目，合并去重）
    try:
        existing = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []

    new_events = []
    for f in sorted(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        new_events.extend(extract_from_diff(data))

    print(f"从 {len(files)} 个 diff 文件提炼出 {len(new_events)} 个事件")

    # 合并：新事件优先（按日期），同 platform+title 去重
    merged = {}
    for e in new_events + existing:
        key = (e["platform"], norm_title(e["title"]))
        if key not in merged or e["date"] > merged[key]["date"]:
            merged[key] = e
    feeds = sorted(merged.values(), key=lambda e: e["date"], reverse=True)[:MAX_ITEMS]
    # 清理内部权重字段
    for e in feeds:
        e.pop("_weight", None)

    FEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDS_FILE.write_text(json.dumps(feeds, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"live_feeds.json 更新: {len(existing)} -> {len(feeds)} 条")
    for e in feeds[:8]:
        print(f"  {e['date']} [{e['type']}] {e['platform']}: {e['title'][:40]}")


if __name__ == "__main__":
    main()
