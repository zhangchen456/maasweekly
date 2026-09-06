#!/usr/bin/env python3
"""LLM 摘要层：把当日 diff（经 diff_clean 降噪后）提炼为"今日要点"人话摘要。

数据流：sync-diff-to-site.py 先跑（产出含 kind/pairs 的 daily_changes.json），
本脚本读取其中缺 highlights 的日期，把 substantive 信源的行喂给 LLM，
产出 highlights 写回 daily_changes.json。

要点条目结构（v2，按平台分组）：
  {
    "platform": "...", "logo_summary": "该平台今日一句话总评（≤40字）",
    "items": [
      { "text": "要点内容（模型名/价格等关键实体放句首或加粗概念）", "type": "release|pricing|sunset|other" }
    ]
  }

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

请完成两件事：

【一、按平台分组的"今日要点"】
1. 以平台为维度组织：每个平台给一个 logo_summary（该平台今日动态的一句话总评，≤40字，概括性质如"旗舰模型发布+定价调整"）和 1-3 条 items
2. 每条 item 一句话说清楚发生了什么（新模型上线/下线/价格调整/新功能/重要公告），关键实体（模型名、价格数字、日期）尽量放在句子前部
3. 只提炼对 MaaS 行业观察者有信息量的事件；排行榜分数微调（±10 以内的 Elo 波动）、下载量计数变化不算要点
4. 当日没有实质变化的平台不要输出

【二、信源级变化解读】
对输入数据中每个信源（platform+source_type 组合）给一段 2-3 句的 summary：这批增删变化合起来代表什么意思（例如"新增了 GPT-6 Astra 的输入/输出定价行，同时移除了旧的定价说明，对应新模型上架"）。解读要克制，只陈述数据可见的事实。

要求：
- 简体中文，模型名/产品名保留英文原名
- 平台按事件重要性排序
- 严格输出一个 JSON 对象（不要 markdown 代码块）：
{
  "highlights": [{"platform": "平台名", "logo_summary": "一句话总评", "items": [{"text": "要点", "type": "release|pricing|sunset|other"}]}],
  "source_summaries": {"平台名|source_type": "2-3句解读"}
}

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


def parse_llm_json(text: str) -> dict:
    """解析 LLM 输出的 JSON 对象（v3：{highlights, source_summaries}）。

    highlights: [{platform, logo_summary, items: [{text, type}]}]
    source_summaries: {"平台名|source_type": "解读"}
    """
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM 输出中找不到 JSON 对象: {text[:200]}")
    obj = json.loads(t[start:end + 1])

    # highlights（平台分组）
    out_hl = []
    for it in obj.get("highlights") or []:
        if isinstance(it, dict) and it.get("platform") and isinstance(it.get("items"), list) and it["items"]:
            parsed_items = []
            for sub in it["items"]:
                if isinstance(sub, dict) and sub.get("text"):
                    parsed_items.append({
                        "text": str(sub["text"]),
                        "type": sub.get("type") or "other",
                    })
            if parsed_items:
                out_hl.append({
                    "platform": str(it["platform"]),
                    "logo_summary": str(it.get("logo_summary") or ""),
                    "items": parsed_items,
                })

    # source_summaries（信源解读）
    out_ss = {}
    ss = obj.get("source_summaries")
    if isinstance(ss, dict):
        for k, v in ss.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                out_ss[k] = v.strip()
    return {"highlights": out_hl, "source_summaries": out_ss}


def build_day_prompt(date_str: str, changed: list, price_changes: list | None = None) -> str:
    """把当日 substantive 信源 + 价格变化事件组装成喂给 LLM 的文本。"""
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
    # 价格变化事件（fetch-prices.py 结构化产出，来自 8 家厂商官方定价页 diff）
    if price_changes:
        parts.append("\n## 官方定价页价格变化（结构化，已按模型×计费组件归一）")
        for pc in price_changes[:20]:
            if "previous" in pc and pc.get("previous"):
                parts.append(f"  {pc['provider']}/{pc['model']} {pc['component']}: "
                             f"{pc['previous']} → {pc['current']} {pc.get('currency','')}/百万tokens")
            else:
                parts.append(f"  {pc['provider']}/{pc['model']} {pc['component']}: "
                             f"新定价 {pc['current']} {pc.get('currency','')}/百万tokens")
    return PROMPT + "\n".join(parts)


def process_day(day: dict, api_key: str, base_url: str, model: str) -> dict | None:
    """处理单日：substantive 信源 + 价格变化喂 LLM，返回 {highlights, source_summaries} 或 None（失败）。"""
    changed = [c for c in day.get("changed", []) if c.get("kind") == "substantive"]
    price_changes = day.get("price_changes") or []
    if not changed and not price_changes:
        return {"highlights": [], "source_summaries": {}}
    prompt = build_day_prompt(day["date"], changed, price_changes)
    print(f"  调用 LLM（prompt {len(prompt)} 字符）...", flush=True)
    try:
        raw = llm_call(api_key, base_url, model, prompt)
        result = parse_llm_json(raw)
    except Exception as e:  # noqa: BLE001 —— 任何失败都降级为无 highlights
        print(f"  ✗ LLM 调用/解析失败，跳过该日期: {e}")
        return None
    return result


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
        result = process_day(day, api_key, base_url, model)
        if result is None:
            continue  # 失败降级：不写 highlights，前端用规则版预览
        day["highlights"] = result["highlights"]
        # 信源级解读挂到对应 changed 条目上（按 platform|source_type 匹配）
        summaries = result["source_summaries"]
        if summaries:
            for c in day.get("changed", []):
                key = f"{c.get('platform')}|{c.get('source_type')}"
                if key in summaries:
                    c["llm_summary"] = summaries[key]
        for h in result["highlights"]:
            for item in h["items"]:
                print(f"  • [{item['type']}] {h['platform']}: {item['text'][:60]}")

    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    DST_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ndaily_changes.json 已更新 -> {DST_FILE}")


if __name__ == "__main__":
    main()
