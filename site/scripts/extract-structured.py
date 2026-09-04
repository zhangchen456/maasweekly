#!/usr/bin/env python3
"""把周报 Markdown 解析成结构化 JSON,供前端渲染卡片与折叠分区。

输入: src/content/weekly/*.md  (import-weekly.py 产出的带 frontmatter 版本)
输出: src/content/weekly-structured/<date>.json

每期周报的固定六节结构:
  一、重要更新摘要  -> headline (🔴 本周头条 / 🟡 值得关注)
  二、各平台详细追踪 -> platforms (每个 ### 一个平台)
  三、各平台状态汇总表 -> summary_table (markdown 表格)
  四、趋势洞察      -> trends (每个 ### 一条)
  五、关注时间点     -> watchpoints (markdown 表格)
  六、已报道事件索引 -> event_index (- [date] ... 列表)
"""
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC_DIR = BASE / "src" / "content" / "weekly"
DST_DIR = BASE / "src" / "content" / "weekly-structured"
DST_DIR.mkdir(parents=True, exist_ok=True)

# 状态 emoji -> 语义
STATUS_MAP = {
    "🟢": "active",
    "🟡": "stable",
    "🔴": "critical",
}
LEVEL_MAP = {
    "🔴": "critical",
    "🟡": "notable",
}


def split_frontmatter(text):
    """分离 frontmatter 与正文。"""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, m.group(2)


def split_h2_sections(body):
    """按 ## 标题切分,返回 {标题文本: 该节内容}。"""
    sections = {}
    # 匹配 ## 开头(非 ###)
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    # parts[0] 是第一个 ## 之前的内容(通常是报告头)
    if parts[0].strip():
        sections["_header"] = parts[0]
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        sections[title] = content
    return sections


def extract_headline(content):
    """解析'重要更新摘要'节,返回 headline 列表。

    结构: ### 🔴 本周头条  下接编号项 1. **...** ; 然后 ### 🟡 值得关注。
    每个编号项可能跨多行,直到下一个编号项或下一个 ###。
    """
    headlines = []

    # 先按 ### 切分
    h3_parts = re.split(r"^### (.+)$", content, flags=re.MULTILINE)
    # h3_parts[0] 是节首(可能空), 之后交替 标题/内容
    current_level = None
    for i in range(1, len(h3_parts), 2):
        title = h3_parts[i].strip()
        body = h3_parts[i + 1] if i + 1 < len(h3_parts) else ""

        # 判断 level
        level = None
        for emoji, lvl in LEVEL_MAP.items():
            if emoji in title:
                level = lvl
                break
        if level is None:
            continue
        current_level = level

        # 解析编号项: 1. **标题**(标记)...：正文
        # 编号项格式: 数字. 然后是加粗标题(可能含——破折号), 然后括号标记, 然后冒号, 然后正文(可能多行)
        # 用正则匹配每个编号项的开头
        items = re.split(r"^\d+\.\s+", body, flags=re.MULTILINE)
        for idx, item in enumerate(items[1:], start=1):  # 跳过第一个(编号前内容)
            item = item.strip()
            if not item:
                continue

            # 提取标题: 开头的 **...** 部分(可能跨行,但通常在一行)
            title_match = re.match(r"\*\*(.+?)\*\*\s*", item)
            title = title_match.group(1).strip() if title_match else item[:60]

            # 去掉标题后剩余
            rest = item[title_match.end():] if title_match else item

            # 提取标记: (新增报道) / (跟进报道) / (新增发现) 等
            # 括号内可能带日期: （新增报道，8月28日） / （跟进报道）
            is_new = None
            mark_match = re.search(
                r"[（(](新增报道|跟进报道|新增发现|跟进)[，,]?\s*[^)）]*[)）]",
                rest,
            )
            if mark_match:
                mark_text = mark_match.group(1)
                is_new = "新增" in mark_text
                # 从 rest 中删除整个标记(含括号内日期)
                rest = rest[: mark_match.start()] + rest[mark_match.end():]

            # 提取日期: 8月28日 / 8/28 等
            date_match = re.search(r"(\d+月\d+日|\d+/\d+)", title + " " + rest)
            date_mentioned = date_match.group(1) if date_match else ""

            # summary: 标题中 —— 后的部分,或正文第一句
            summary = ""
            if "——" in title:
                summary = title.split("——", 1)[1].strip()
            elif "：" in rest or ":" in rest:
                # 冒号后的第一句
                after_colon = re.split(r"[：:]", rest, 1)[-1]
                summary = after_colon.split("。")[0].strip()[:120]
            if not summary:
                summary = title[:80]

            # platform: 标题开头的平台名
            platform = ""
            platform_match = re.match(
                r"(腾讯混元|阿里百炼|百度千帆|火山方舟|硅基流动|智谱(?:\s*AI)?|Kimi|MiniMax|DeepSeek|月之暗面)",
                title,
            )
            if platform_match:
                platform = platform_match.group(1)

            # detail_markdown: 去掉标题和标记后的正文
            detail = rest.strip()
            # 去掉开头的冒号
            detail = re.sub(r"^[：:]\s*", "", detail)

            headlines.append({
                "rank": len(headlines) + 1,
                "level": current_level,
                "platform": platform,
                "title": title,
                "summary": summary,
                "detail_markdown": detail,
                "date_mentioned": date_mentioned,
                "is_new": is_new,
            })
    return headlines


def extract_platforms(content):
    """解析'各平台详细追踪'节,返回 platforms 列表。

    每个 ### N. 平台名 是一个平台块。
    块内: **状态**: 行 / **本周动态**: 下接 - 列表 / **近期动态回顾**: 下接 - 列表。
    """
    platforms = []
    h3_parts = re.split(r"^### (.+)$", content, flags=re.MULTILINE)

    for i in range(1, len(h3_parts), 2):
        title = h3_parts[i].strip()
        body = h3_parts[i + 1] if i + 1 < len(h3_parts) else ""

        # 平台名: 去掉前缀编号 "1. "
        name = re.sub(r"^\d+\.\s*", "", title).strip()

        # 状态行: **状态**: 🟢 活跃更新 — ...
        status = "stable"
        status_text = ""
        status_match = re.search(
            r"\*\*状态\*\*\s*[：:]\s*(.+)()", body
        )
        if status_match:
            status_line = status_match.group(1).strip()
            for emoji, sem in STATUS_MAP.items():
                if emoji in status_line:
                    status = sem
                    break
            # 去掉 emoji,保留文字
            status_text = re.sub(r"[🟢🟡🔴]", "", status_line).strip()
            # 去掉末尾的 — 或 -
            status_text = re.sub(r"\s*[—-]\s*$", "", status_text).strip()

        # 本周动态 / 近期动态回顾
        this_week = []
        recent = []

        # 切分两个子节
        tw_match = re.search(
            r"\*\*本周动态\*\*\s*[：:]?\n(.*?)(?=\*\*近期动态回顾\*\*|\Z)",
            body,
            re.DOTALL,
        )
        if tw_match:
            this_week = extract_list_items(tw_match.group(1))

        recent_match = re.search(
            r"\*\*近期动态回顾\*\*\s*[：:]?\n(.*?)(?=\*\*状态\*\*|\Z)",
            body,
            re.DOTALL,
        )
        if recent_match:
            recent = extract_list_items(recent_match.group(1))

        platforms.append({
            "name": name,
            "status": status,
            "status_text": status_text,
            "this_week": this_week,
            "recent": recent,
        })
    return platforms


def extract_list_items(text):
    """从文本中提取 - 开头的列表项,每项保留原始 markdown(含加粗等)。

    一个列表项可能跨行(续行缩进),合并到一项。
    """
    items = []
    lines = text.splitlines()
    current = None

    for line in lines:
        # 顶级列表项: - 开头
        m = re.match(r"^-\s+(.*)$", line)
        if m:
            if current is not None:
                items.append(current.strip())
            current = m.group(1)
        elif current is not None and line.startswith("   "):
            # 续行(缩进3空格)
            current += " " + line.strip()
        elif current is not None and not line.strip():
            # 空行结束当前项
            items.append(current.strip())
            current = None
        elif current is not None:
            # 非缩进非空行,也可能是续行(某些周报格式)
            current += " " + line.strip()

    if current is not None:
        items.append(current.strip())

    # 过滤空项和纯分割线
    return [it for it in items if it and it != "---"]


def extract_table(text):
    """从文本中提取第一个 markdown 表格,返回 {headers: [...], rows: [[...], ...]}。"""
    lines = text.splitlines()
    table_lines = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            in_table = True
        elif in_table and not stripped.startswith("|"):
            break

    if len(table_lines) < 2:
        return None

    def parse_row(row):
        cells = [c.strip() for c in row.strip("|").split("|")]
        return cells

    headers = parse_row(table_lines[0])
    # 第二行是分隔符 |---|---|
    rows = [parse_row(r) for r in table_lines[2:]] if len(table_lines) > 2 else []

    return {"headers": headers, "rows": rows}


def extract_trends(content):
    """解析'趋势洞察'节,每个 ### 一条,返回 [{title, body_markdown}]。"""
    trends = []
    h3_parts = re.split(r"^### (.+)$", content, flags=re.MULTILINE)

    for i in range(1, len(h3_parts), 2):
        title = h3_parts[i].strip()
        body = h3_parts[i + 1] if i + 1 < len(h3_parts) else ""
        # 去掉标题前缀编号 "1. "
        title = re.sub(r"^\d+\.\s*", "", title).strip()
        trends.append({
            "title": title,
            "body_markdown": body.strip(),
        })
    return trends


def extract_event_index(content):
    """解析'已报道事件索引'节,返回 [{date, text}]。"""
    items = []
    for line in content.splitlines():
        m = re.match(r"^-\s*\[(\d{4}-\d{2}-\d{2})\]\s*(.+)$", line)
        if m:
            items.append({
                "date": m.group(1),
                "text": m.group(2).strip(),
            })
    return items


def parse_report(md_text):
    """解析一篇周报 markdown,返回结构化 dict。"""
    fm, body = split_frontmatter(md_text)
    sections = split_h2_sections(body)

    date = fm.get("date", "")
    period = fm.get("period", "")

    # 识别各节(用关键词匹配,兼容标题序号变化)
    headline_content = ""
    platforms_content = ""
    summary_content = ""
    trends_content = ""
    watchpoints_content = ""
    event_index_content = ""

    for title, content in sections.items():
        if "重要更新" in title or "摘要" in title:
            headline_content = content
        elif "平台详细" in title or "各平台" in title and "详细" in title:
            platforms_content = content
        elif "状态汇总" in title or "汇总表" in title:
            summary_content = content
        elif "趋势" in title:
            trends_content = content
        elif "关注时间" in title or "时间点" in title:
            watchpoints_content = content
        elif "事件索引" in title or "去重" in title or "已报道" in title:
            event_index_content = content

    headline = extract_headline(headline_content)
    platforms = extract_platforms(platforms_content)
    summary_table = extract_table(summary_content)
    trends = extract_trends(trends_content)
    watchpoints = extract_table(watchpoints_content)
    event_index = extract_event_index(event_index_content)

    return {
        "date": date,
        "period": period,
        "headline": headline,
        "platforms": platforms,
        "summary_table": summary_table,
        "trends": trends,
        "watchpoints": watchpoints,
        "event_index": event_index,
    }


def main():
    count = 0
    for md_file in sorted(SRC_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        try:
            data = parse_report(text)
        except Exception as e:
            print(f"  [ERROR] {md_file.name}: {e}")
            continue

        out_path = DST_DIR / f"{md_file.stem}.json"
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        count += 1

        # 简要统计
        h_count = len(data["headline"])
        p_count = len(data["platforms"])
        t_count = len(data["trends"])
        e_count = len(data["event_index"])
        print(
            f"  {md_file.name} -> OK  "
            f"头条{h_count} 平台{p_count} 趋势{t_count} 索引{e_count}"
        )

    print(f"\nDone: {count} reports extracted to {DST_DIR}")

    build_timeline()


def parse_event_date(text, report_date):
    """从事件文本里解析真实日期,用周报日期补年份。

    text 里的日期格式: 8/28, 8月28日, (8/28), 8/26 等。
    report_date: YYYY-MM-DD (周报发布日),事件一定 <= 这一天。
    """
    year = report_date[:4]

    # 匹配 X月Y日 或 X/Y (其中 X 1-12, Y 1-31)
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if not m:
        m = re.search(r"[（(]?(\d{1,2})/(\d{1,2})[)）]?", text)
    if not m:
        return None

    month, day = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None

    date_str = f"{year}-{month:02d}-{day:02d}"
    # 事件不应晚于周报发布日;如果晚,说明是跨年事件,年份减1
    if date_str > report_date:
        date_str = f"{int(year)-1}-{month:02d}-{day:02d}"
    return date_str


def split_event_text(text):
    """把一条 event_index 的 text 拆成单条事件。

    分隔符: 、；（分号、顿号）
    但要保留括号内的内容(如 8/28, Apache 2.0 不拆)。
    """
    events = []
    # 用顿号/分号拆,但跳过括号内
    depth = 0
    buf = ""
    for ch in text:
        if ch in "（(":
            depth += 1
            buf += ch
        elif ch in "）)":
            depth -= 1
            buf += ch
        elif depth == 0 and ch in "、；;":
            if buf.strip():
                events.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        events.append(buf.strip())
    return events


def build_timeline():
    """聚合所有期次的 event_index,生成按日期排列的全局时间线 JSON。

    输出: src/content/timeline.json
    结构: [{"date": "2026-09-01", "events": [{text, source_date}]}]
    """
    all_events = []  # [(date, text, source_date)]

    for json_file in sorted(DST_DIR.glob("*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        report_date = data["date"]

        for idx_entry in data["event_index"]:
            idx_date = idx_entry["date"]  # 周报日期
            for ev in split_event_text(idx_entry["text"]):
                ev_date = parse_event_date(ev, idx_date)
                if ev_date:
                    all_events.append((ev_date, ev, idx_date))

    # 按日期聚合 + 去重(同一文本只留一次)
    by_date = {}
    seen = set()
    for date, text, source_date in all_events:
        # 去重: 文本前30字作为指纹
        fp = text[:30]
        if fp in seen:
            continue
        seen.add(fp)
        by_date.setdefault(date, []).append({
            "text": text,
            "source_date": source_date,
        })

    # 倒序输出
    timeline = []
    for date in sorted(by_date.keys(), reverse=True):
        timeline.append({
            "date": date,
            "events": by_date[date],
        })

    out_path = BASE / "src" / "content" / "timeline.json"
    out_path.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(len(d["events"]) for d in timeline)
    print(f"Timeline: {len(timeline)} days, {total} events -> {out_path.name}")


if __name__ == "__main__":
    main()
