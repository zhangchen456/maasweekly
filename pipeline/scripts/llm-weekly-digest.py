#!/usr/bin/env python3
"""LLM 周度串讲：把一周的每日要点与实质变化聚合成结构化周度回顾。

数据流：sync-diff-to-site.py 先跑（产出 weekly-digest.json），
本脚本读取其中缺 story 的周（默认最新一周），把当周 highlights +
每日 substantive 变化喂给 LLM，产出 {theme, sections:[{title, body}]}
写回 weekly-digest.json（前端优先渲染 sections，兼容旧纯文本 story）。

工程约束：
- 幂等：已有 story/sections 的周跳过（--force 可重做）
- 降级：LLM 失败时该周 story 留空，前端只显示统计聚合
- 触发：weekly-update.yml 周一跑；也可手动补任意周

环境变量与 llm-digest.py 一致：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL

用法:
  python3 pipeline/scripts/llm-weekly-digest.py              # 处理最新一周
  python3 pipeline/scripts/llm-weekly-digest.py 2026-W36     # 指定周（--force 语义）
  python3 pipeline/scripts/llm-weekly-digest.py --all        # 回填全部缺失周
"""
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import importlib.util

BASE = Path(__file__).resolve().parent.parent.parent
# llm-digest.py 文件名带连字符，不能直接 import，用 importlib 挂载复用 llm_call
_spec = importlib.util.spec_from_file_location(
    "llm_digest", BASE / "pipeline" / "scripts" / "llm-digest.py")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["llm_digest"] = _mod
_spec.loader.exec_module(_mod)
llm_call = _mod.llm_call

WEEKLY_FILE = BASE / "site" / "src" / "data" / "weekly-digest.json"
DAILY_FILE = BASE / "site" / "src" / "data" / "daily_changes.json"
REQUEST_TIMEOUT = 180

MAX_DAYS = 7                  # 一周最多 7 天
MAX_HIGHLIGHTS = 40           # 喂给 LLM 的要点上限
MAX_PREVIEW_PER_DAY = 30      # 每日 substantive 信源预览行上限

PROMPT = """你是 MaaS（模型即服务）行业追踪站点的资深编辑。下面是本周各平台逐日的变化要点与信号（每日要点由 AI 提炼，信号行是降噪后的 diff 增量）。

请写本周的周度串讲，要求：
1. 不是流水账：归纳本周主线（比如"新模型密集发布周"/"调价周期"/"下线清理周"），把同平台、同主题的事件串起来讲
2. 分 2-4 个 section，每个 section 有一个小标题（如"密集发布：…"、"下线与清理"、"价格锚点"），标题本身要点出该节核心结论；节内正文 60-120 字，短段落，一句话一个事实
3. 有观点但克制：只在数据支撑的范围内下判断（如"本周 X 家平台同步上架同一模型，说明…"），不做无依据预测
4. 保留具体锚点：关键模型名、价格数字、日期要出现在正文里
5. 简体中文，模型名/产品名保留英文原名
6. 严格输出 JSON 对象（不要 markdown 代码块）：
{"theme": "一句话主题（≤20字）", "sections": [{"title": "小节标题（≤16字，含核心结论）", "body": "小节正文（60-120字）"}]}

本周数据：
"""


def build_week_prompt(week: dict, days_by_date: dict) -> str:
    parts = [f"周次：{week['week']}（{week['start']} ~ {week['end']}）\n"]
    highlights = week.get("highlights", [])[:MAX_HIGHLIGHTS]
    if highlights:
        parts.append("## 每日要点")
        for h in highlights:
            parts.append(f"- [{h['date']}][{h['platform']}][{h['type']}] {h['text']}")
    parts.append("\n## 每日信号明细（substantive 变化的信源与预览行）")
    for date in sorted(week["days"].keys())[:MAX_DAYS]:
        day = days_by_date.get(date)
        if not day:
            continue
        parts.append(f"\n### {date}")
        shown = 0
        for c in day.get("changed", []):
            if c.get("kind") != "substantive" or shown >= MAX_PREVIEW_PER_DAY:
                continue
            preview = c.get("signal_preview") or ""
            parts.append(f"- {c['platform']}({c['source_type']}): {preview[:120]}")
            shown += 1
    return PROMPT + "\n".join(parts)


def parse_story(raw: str) -> dict:
    """解析 LLM 输出。新结构 {"theme", "sections": [{title, body}]}；
    兼容旧纯文本 {"theme", "story"}（前端对两者都能渲染）。"""
    import re
    t = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM 输出中找不到 JSON 对象: {raw[:200]}")
    obj = json.loads(t[start:end + 1])
    theme = obj.get("theme", "")
    if obj.get("sections"):
        sections = [s for s in obj["sections"] if s.get("title") and s.get("body")]
        if sections:
            return {"theme": theme, "sections": sections}
    if obj.get("story"):
        return {"theme": theme, "story": obj["story"]}
    raise ValueError("LLM 输出缺少 sections 或 story 字段")


def main():
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        print("缺少 LLM_API_KEY 环境变量，退出（不阻塞构建）")
        return
    if not WEEKLY_FILE.exists():
        print("weekly-digest.json 不存在，请先跑 sync-diff-to-site.py")
        return

    weekly = json.loads(WEEKLY_FILE.read_text(encoding="utf-8"))
    days_by_date = {}
    if DAILY_FILE.exists():
        for d in json.loads(DAILY_FILE.read_text(encoding="utf-8")).get("days", []):
            days_by_date[d["date"]] = d

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    all_weeks = "--all" in sys.argv

    if args:
        targets = [w for w in weekly if w["week"] in args]
    elif all_weeks:
        targets = [w for w in weekly if not w.get("story") or force]
    else:
        latest = weekly[0] if weekly else None
        # 最新一周只在该周结束（或今天是周日之后）才串讲，避免半周数据出"周报"；
        # --force 或指定周号可强制
        targets = [latest] if latest and (not latest.get("story") or force) else []
        if targets and not force:
            today = datetime.now().strftime("%Y-%m-%d")
            if today <= targets[0]["end"]:
                print(f"本周（{targets[0]['week']}）尚未结束（至 {targets[0]['end']}），跳过；"
                      f"如需强制生成请加 --force")
                targets = []

    if not targets:
        print("没有需要处理的周")
        return

    print(f"待处理 {len(targets)} 周: {[w['week'] for w in targets]}")
    changed = False
    for week in targets:
        print(f"\n[{week['week']}]")
        prompt = build_week_prompt(week, days_by_date)
        print(f"  调用 LLM（prompt {len(prompt)} 字符）...", flush=True)
        try:
            raw = llm_call(api_key,
                           os.environ.get("LLM_BASE_URL", "https://maas-api.cn-huabei-1.xf-yun.com/v2"),
                           os.environ.get("LLM_MODEL", "xopdeepseekv4flash0731"),
                           prompt)
            story = parse_story(raw)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ LLM 调用/解析失败，跳过: {e}")
            continue
        week["story"] = story
        changed = True
        print(f"  主题: {story['theme']}")
        print(f"  {story['story'][:100]}...")

    if changed:
        WEEKLY_FILE.write_text(json.dumps(weekly, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nweekly-digest.json 已更新 -> {WEEKLY_FILE}")
    else:
        print("\n无更新")


if __name__ == "__main__":
    main()
