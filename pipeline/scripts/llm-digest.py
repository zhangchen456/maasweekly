#!/usr/bin/env python3
"""LLM 摘要层：把当日 diff（经 diff_clean 降噪后）提炼为"今日要点"人话摘要。

数据流：sync-diff-to-site.py 先跑（产出含 kind/pairs 的 daily_changes.json），
本脚本读取其中缺 highlights 的日期，把 substantive 信源的行喂给 LLM，
产出 highlights 写回 daily_changes.json。

要点条目结构：
  { "platform": "...", "text": "人话摘要", "type": "release|pricing|sunset|other" }

工程约束：
- 幂等：已有 highlights 的日期跳过（--force 可重做）
- 降级：LLM 调用失败时该日期 highlights 留空，前端回退到 signal_preview 规则版
- 成本：每信源最多喂 MAX_LINES_PER_SOURCE 行、每行截断 MAX_LINE_LEN 字符

环境变量：
  LLM_API_KEY   必填
  LLM_BASE_URL  默认 https://maas-api.cn-huabei-1.xf-yun.com/v2
  LLM_MODEL     默认 xopdeepseekv4flash0731

用法:
  python3 pipeline/scripts/llm-digest.py              # 处理 daily_changes.json 中缺 highlights 的最近日期
  python3 pipeline/scripts/llm-digest.py 2026-09-04   # 指定日期（--force 语义）
  python3 pipeline/scripts/llm-digest.py --all        # 回填全部缺失日期
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))
from diff_clean import filter_and_pair, humanize_line  # noqa: E402

DIFF_DIR = BASE / "data" / "diff"
DST_FILE = BASE / "site" / "src" / "data" / "daily_changes.json"

DEFAULT_BASE_URL = "https://maas-api.cn-huabei-1.xf-yun.com/v2"
DEFAULT_MODEL = "xopdeepseekv4flash0731"

MAX_LINES_PER_SOURCE = 12   # 每信源最多喂给 LLM 的行数
MAX_LINE_LEN = 160          # 每行截断长度
MAX_SOURCES = 25            # 单日最多处理的信源数
REQUEST_TIMEOUT = 120       # 秒

PROMPT = """你是 MaaS（模型即服务）行业追踪站点的编辑。下面是各平台信源今日的变化数据（已过滤噪声，"新增"行是新出现的内容，"删除"行是被替换的旧内容，"变化"行是同一实体旧值→新值）。

请提炼 3-6 条"今日要点"，要求：
1. 每条一句话，说清楚：哪个平台、发生了什么（新模型上线/下线/价格调整/新功能/重要公告）
2. 只提炼对 MaaS 行业观察者有信息量的事件；排行榜分数微调（±10 以内的 Elo 波动）、下载量计数变化不算要点
3. 排行榜变化只有"新模型上榜"或"排名大幅变动"才值得提
4. 用简体中文，模型名/产品名保留英文原名
5. 严格输出 JSON 数组，不要 markdown 代码块，格式：
[{"platform": "平台名", "text": "要点内容", "type": "release|pricing|sunset|other"}]

今日数据：
"""


def llm_call(api_key: str, base_url: str, model: str, prompt: str) -> str:
    """调用 OpenAI 兼容 /chat/completions，返回文本。"""
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2000,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_llm_json(text: str) -> list:
    """解析 LLM 输出的 JSON 数组，容忍 markdown 代码块包裹。"""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    # 截取第一个 [ 到最后一个 ] 之间（防前后缀说明文字）
    start, end = t.find("["), t.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"LLM 输出中找不到 JSON 数组: {text[:200]}")
    items = json.loads(t[start:end + 1])
    if not isinstance(items, list):
        raise ValueError("LLM 输出不是数组")
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("platform") and it.get("text"):
            out.append({
                "platform": str(it["platform"]),
                "text": str(it["text"]),
                "type": it.get("type") or "other",
            })
    return out


def build_day_prompt(date_str: str, changed: list) -> str:
    """把当日 substantive 信源组装成喂给 LLM 的文本。"""
    parts = [f"日期：{date_str}\n"]
    for c in changed[:MAX_SOURCES]:
        if c.get("kind") != "substantive":
            continue
        parts.append(f"\n## {c['platform']} · {c['source_type']}")
        for p in (c.get("pairs") or [])[:MAX_LINES_PER_SOURCE]:
            parts.append(f"  变化: {humanize_line(p['before'])[:MAX_LINE_LEN]} → {humanize_line(p['after'])[:MAX_LINE_LEN]}")
        for l in (c.get("added_lines") or [])[:MAX_LINES_PER_SOURCE]:
            parts.append(f"  新增: {humanize_line(l)[:MAX_LINE_LEN]}")
        for l in (c.get("removed_lines") or [])[:6]:
            parts.append(f"  删除: {humanize_line(l)[:MAX_LINE_LEN]}")
    return PROMPT + "\n".join(parts)


def process_day(day: dict, api_key: str, base_url: str, model: str) -> list | None:
    """处理单日：substantive 信源喂 LLM，返回 highlights 或 None（失败）。"""
    changed = [c for c in day.get("changed", []) if c.get("kind") == "substantive"]
    if not changed:
        return []
    prompt = build_day_prompt(day["date"], changed)
    print(f"  调用 LLM（prompt {len(prompt)} 字符）...", flush=True)
    try:
        raw = llm_call(api_key, base_url, model, prompt)
        highlights = parse_llm_json(raw)
    except Exception as e:  # noqa: BLE001 —— 任何失败都降级为无 highlights
        print(f"  ✗ LLM 调用/解析失败，跳过该日期: {e}")
        return None
    return highlights


def main():
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if not api_key:
        print("缺少 LLM_API_KEY 环境变量，退出（不阻塞构建）")
        return

    if not DST_FILE.exists():
        print("daily_changes.json 不存在，请先跑 sync-diff-to-site.py")
        return

    data = json.loads(DST_FILE.read_text(encoding="utf-8"))
    days = data.get("days", [])

    # 参数：指定日期 or --all or 默认最新一天
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    all_days = "--all" in sys.argv

    if args:
        targets = [d for d in days if d["date"] in args]
    elif all_days:
        targets = [d for d in days if not d.get("highlights") or force]
    else:
        latest = days[0] if days else None
        targets = [latest] if latest and (not latest.get("highlights") or force) else []

    if not targets:
        print("没有需要处理的日期（均已生成 highlights）")
        return

    print(f"待处理 {len(targets)} 天: {[d['date'] for d in targets]}")
    for day in targets:
        print(f"\n[{day['date']}]")
        hl = process_day(day, api_key, base_url, model)
        if hl is None:
            continue  # 失败降级：不写 highlights，前端用规则版预览
        day["highlights"] = hl
        for h in hl:
            print(f"  • [{h['type']}] {h['platform']}: {h['text'][:60]}")

    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    DST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ndaily_changes.json 已更新 -> {DST_FILE}")


if __name__ == "__main__":
    main()
