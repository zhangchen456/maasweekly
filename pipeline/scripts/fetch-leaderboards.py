#!/usr/bin/env python3
"""OpenRouter 榜单数据抓取脚本。

从 OpenRouter Data API（CC BY 4.0）拉取四个数据集，聚合后写入站点数据源：
  1. rankings-daily  → site/src/data/leaderboards/openrouter.json          模型调用量 Top10（含环比）
                    → site/src/data/leaderboards/openrouter_market_share.json  厂商份额
  2. session-cost    → site/src/data/leaderboards/openrouter_session_cost.json  编程 Agent 会话成本
  3. app-rankings    → site/src/data/leaderboards/openrouter_apps.json      Top Apps（popular + trending）

工程约束（对齐 fetch_sources.py / refresh-logos.py 的既有模式）：
- 零第三方依赖：curl 子进程 + 标准库
- 降级：单个数据集失败保留旧文件不覆盖；缺 API key 直接退出（exit 0，不阻塞 CI）
- 原子写：*.tmp → os.replace()
- 环比：rankings-daily 无 trending，拉「最近两个滚动 7 日窗」脚本端计算
- 原始响应存档：data/snapshots/<today>/leaderboards__openrouter__<dataset>.json

环境变量：
  OPENROUTER_API_KEY  必填（https://openrouter.ai/settings/keys，任何可调用推理的 key）

用法：
  python3 pipeline/scripts/fetch-leaderboards.py [--dry-run] [--only rankings|session-cost|apps]
"""

import json
import os
import subprocess
import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root
LB_DIR = BASE_DIR / "site" / "src" / "data" / "leaderboards"
SNAPSHOT_DIR = BASE_DIR / "data" / "snapshots"
API_BASE = "https://openrouter.ai/api/v1"

# permaslug 前缀 → 展示名（对齐 site/src/data/platform-logos.json 才能 logoFor 命中）
VENDOR_MAP = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google Gemini API",
    "deepseek": "DeepSeek", "moonshotai": "Kimi", "minimax": "MiniMax",
    "z-ai": "智谱AI", "zai": "智谱AI", "xai": "xAI", "mistralai": "Mistral AI",
    "meta-llama": "Meta", "meta": "Meta", "nvidia": "NVIDIA", "qwen": "Qwen",
    "tencent": "腾讯", "perplexity": "Perplexity", "openrouter": "OpenRouter",
    "microsoft": "Microsoft", "amazon": "Amazon", "cohere": "Cohere", "ai21": "AI21",
    "baidu": "百度千帆", "bytedance": "字节跳动", "alibaba": "阿里云", "xirity": "讯飞星辰MaaS",
    "inception": "Inception", "gryphe": "Gryphe", "nousresearch": "Nous",
    "featherless": "Featherless", "valyu": "Valyu", "stepfun-ai": "阶跃星辰",
}
OTHER_VENDOR = "Other"  # rankings-daily 聚合长尾行


def fetch_json(url: str, api_key: str):
    """curl 抓 JSON，返回 (data, error)。校验 HTTP/JSON/结构。"""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "40", "--fail-with-body",
             "-H", f"Authorization: Bearer {api_key}",
             "-H", "Accept: application/json", url],
            capture_output=True, text=True, timeout=45,
        )
        raw = result.stdout.strip()
        if result.returncode != 0:
            return None, f"HTTP {result.returncode} (stderr: {result.stderr[:150]})"
        data = json.loads(raw)
        if not isinstance(data.get("data"), list) or not data.get("data"):
            return None, "响应 data 为空"
        if not data.get("meta", {}).get("as_of"):
            return None, "响应缺 meta.as_of"
        return data, None
    except subprocess.TimeoutExpired:
        return None, "curl 超时 (40s)"
    except json.JSONDecodeError:
        return None, "JSON 解析失败"
    except Exception as e:
        return None, f"请求失败: {e}"


# 模型名中的品牌缩写（prettify 的 title-case 无法处理）
BRAND_TOKENS = {
    "glm": "GLM", "gpt": "GPT", "gemma": "Gemma", "mimo": "MiMo", "hy": "Hy",
    "qwen": "Qwen", "kimi": "Kimi", "ernie": "ERNIE", "muse": "Muse",
    "dbrx": "DBRX", "olmo": "OLMo", "llama": "Llama", "deepseek": "DeepSeek",
    "minimax": "MiniMax", "claude": "Claude", "gemini": "Gemini", "grok": "Grok",
    "nemotron": "Nemotron", "sonnet": "Sonnet", "opus": "Opus", "fable": "Fable",
    "mistral": "Mistral", "sora": "Sora", "codex": "Codex", "spark": "Spark",
    "oss": "OSS", "astra": "Astra", "terra": "Terra", "luna": "Luna", "sol": "Sol",
    "kimi": "Kimi", "longcat": "LongCat", "ernie": "ERNIE",
}


def prettify_model(permaslug: str) -> str:
    """permaslug → 展示名：deepseek/deepseek-v4-flash-0731 → DeepSeek V4 Flash 0731"""
    name = permaslug.split("/", 1)[-1]
    name = name.replace(":free", " (free)").replace(":", " ")
    parts = []
    for token in name.split("-"):
        if not token:
            continue
        key = token.lower()
        if key in ("v2", "v3", "v4", "v5", "v6"):
            parts.append(token.upper())
        elif key in BRAND_TOKENS:
            parts.append(BRAND_TOKENS[key])
        elif token[0].isupper():
            parts.append(token)
        else:
            parts.append(token[0].upper() + token[1:])
    return " ".join(parts)


def vendor_of(permaslug: str) -> tuple[str, str]:
    """返回 (展示名, vendor_key)。"""
    prefix = permaslug.split("/", 1)[0] if "/" in permaslug else permaslug
    return VENDOR_MAP.get(prefix, prefix.replace("-", " ").title()), prefix


def to_t(tokens) -> float:
    return round(int(tokens) / 1e12, 2)


def iso_date(d) -> str:
    return d.strftime("%Y-%m-%d")


def save_snapshot(dataset: str, payload: dict, today: str):
    """原始响应存档到快照目录（与 fetch_sources.py 同约定）。"""
    snap_dir = SNAPSHOT_DIR / today
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / f"leaderboards__openrouter__{dataset}__{today}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def atomic_write(rel_name: str, payload: dict, dry_run: bool):
    if dry_run:
        print(f"  [dry-run] {rel_name}: 跳过写盘")
        return
    target = LB_DIR / rel_name
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    print(f"  写入 {rel_name}")


def load_existing(rel_name: str):
    try:
        return json.loads((LB_DIR / rel_name).read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------- rankings-daily：模型 Top10 + 厂商份额 ----------

def fetch_rankings(api_key: str, today: str, dry_run: bool) -> bool:
    # 滚动 7 日窗：本窗 = [today-7, today-1]（最近完整 UTC 日为止），上窗 = 前移 7 天
    now = datetime.now(timezone.utc)
    end = now.date() - timedelta(days=1)
    cur_start, cur_end = end - timedelta(days=6), end
    prev_start, prev_end = cur_start - timedelta(days=7), cur_start - timedelta(days=1)
    url = (f"{API_BASE}/datasets/rankings-daily"
           f"?start_date={iso_date(prev_start)}&end_date={iso_date(cur_end)}&period=day")
    data, err = fetch_json(url, api_key)
    if err:
        print(f"  ✗ rankings-daily 失败，保留旧数据：{err}")
        return False
    save_snapshot("rankings-daily", data, today)

    rows = data["data"]
    as_of = data["meta"]["as_of"]
    snapshot_date = iso_date(cur_end)

    # 按窗口聚合模型 token（other 是 API 的长尾聚合行，只作分母不进榜）
    cur, prev = {}, {}
    for r in rows:
        d, slug = r["date"], r["model_permaslug"]
        tgt = cur if d >= iso_date(cur_start) else prev
        tgt[slug] = tgt.get(slug, 0) + int(r["total_tokens"])

    cur_top = sorted(((s, t) for s, t in cur.items() if s != "other"), key=lambda kv: -kv[1])
    prev_rank = {slug: i + 1 for i, (slug, _) in enumerate(
        sorted(prev.items(), key=lambda kv: -kv[1]))}

    old = load_existing("openrouter.json")

    top = []
    for i, (slug, tokens) in enumerate(cur_top[:10]):
        model_prev = prev_rank.get(slug)
        change_pct = None
        if slug in prev and prev[slug] > 0:
            change_pct = round((tokens - prev[slug]) / prev[slug] * 100)
        vendor, vendor_key = vendor_of(slug)
        top.append({
            "rank": i + 1,
            "model": prettify_model(slug),
            "permaslug": slug,
            "vendor": vendor,
            "vendor_key": vendor_key,
            "tokens_t": to_t(tokens),
            "tokens_raw": str(tokens),
            "prev_rank": model_prev,
            "change_pct": change_pct,
            "is_new": slug not in prev,
        })

    atomic_write("openrouter.json", {
        "source": "OpenRouter Rankings",
        "source_url": "https://openrouter.ai/rankings",
        "snapshot_date": snapshot_date,
        "as_of": as_of,
        "window": {"start": iso_date(cur_start), "end": iso_date(cur_end), "grain": "rolling-7d"},
        "manual": False,
        "note": "按 OpenRouter API 实际 token 处理量排名（7 日滚动窗口），反映开发者采用而非质量；"
                "不反映全市场流量。环比为与上一个 7 日窗口 token 量变化。",
        "top": top,
    }, dry_run)

    # 厂商份额：本窗按前缀聚合，other 长尾行进分母
    total = sum(cur.values())  # 含 other 行（若 API 返回）
    vendor_tokens = {}
    for slug, tokens in cur.items():
        if slug == "other":
            continue
        vendor_tokens[slug.split("/", 1)[0]] = vendor_tokens.get(slug.split("/", 1)[0], 0) + tokens
    prev_total = sum(prev.values())
    prev_vt = {}
    for slug, tokens in prev.items():
        if slug == "other":
            continue
        p = slug.split("/", 1)[0]
        prev_vt[p] = prev_vt.get(p, 0) + tokens

    shares = []
    for i, (prefix, tokens) in enumerate(sorted(vendor_tokens.items(), key=lambda kv: -kv[1])[:10]):
        share = round(tokens / total * 100, 1) if total else 0
        prev_share = round(prev_vt.get(prefix, 0) / prev_total * 100, 1) if prev_total else None
        vendor, vendor_key = vendor_of(f"{prefix}/x")
        shares.append({
            "rank": i + 1,
            "vendor": vendor,
            "vendor_key": prefix,
            "tokens_t": to_t(tokens),
            "share_pct": share,
            "change_pp": round(share - prev_share, 1) if prev_share is not None else None,
        })

    atomic_write("openrouter_market_share.json", {
        "source": "OpenRouter Rankings (vendor aggregate)",
        "source_url": "https://openrouter.ai/rankings",
        "snapshot_date": snapshot_date,
        "as_of": as_of,
        "window": {"start": iso_date(cur_start), "end": iso_date(cur_end)},
        "manual": False,
        "note": "按模型 permaslug 厂商前缀聚合的 token 份额（7 日滚动窗口）。口径为 top-50 近似："
                "分母含 other 长尾聚合行，未上榜模型计入长尾。",
        "shares": shares,
    }, dry_run)
    return True


# ---------- session-cost：编程 Agent 会话成本 ----------

def fetch_session_cost(api_key: str, today: str, dry_run: bool) -> bool:
    data, err = fetch_json(f"{API_BASE}/datasets/session-cost?limit=500", api_key)
    if err:
        print(f"  ✗ session-cost 失败，保留旧数据：{err}")
        return False
    save_snapshot("session-cost", data, today)

    as_of = data["meta"]["as_of"]
    window_end = data["meta"].get("window_end_date", today)

    # 按 harness 分组；主 cell 取 10-49-turns 档（典型工作会话），
    # 展示该档成本最低的 3 个模型组合；无该档数据的 harness 回退到全部档位
    by_app = {}
    for r in data["data"]:
        by_app.setdefault(r["app_slug"], {"app_name": r["app_name"], "cells": []})["cells"].append({
            "model": prettify_model(r["model_permaslug"]),
            "permaslug": r["model_permaslug"],
            "turn_range": r["turn_range"],
            "median_cost_usd": r["median_session_cost_usd"],
        })
    apps = []
    for slug, info in by_app.items():
        primary = [c for c in info["cells"] if c["turn_range"] == "10-49-turns"]
        pool = primary or info["cells"]
        cells = sorted(pool, key=lambda c: c["median_cost_usd"])[:3]
        apps.append({"app_name": info["app_name"], "app_slug": slug, "cells": cells})
    apps.sort(key=lambda a: a["cells"][0]["median_cost_usd"])

    atomic_write("openrouter_session_cost.json", {
        "source": "OpenRouter Session Cost",
        "source_url": "https://openrouter.ai/rankings",
        "snapshot_date": window_end,
        "as_of": as_of,
        "window_days": data["meta"].get("window_days"),
        "manual": False,
        "note": "编程 Agent 每次会话成本中位数（USD，付费流量），按 harness × 模型 × 轮次聚合，"
                "源数据每周刷新。主口径为 10-49 轮的典型工作会话，每组 harness 展示该档成本最低的 3 个模型组合。",
        "apps": apps,
    }, dry_run)
    return True


# ---------- app-rankings：Top Apps ----------

def fetch_apps(api_key: str, today: str, dry_run: bool) -> bool:
    now = datetime.now(timezone.utc)
    end = now.date() - timedelta(days=1)
    start = end - timedelta(days=6)
    base = f"{API_BASE}/datasets/app-rankings?start_date={iso_date(start)}&end_date={iso_date(end)}"

    popular_data, err1 = fetch_json(f"{base}&sort=popular&limit=10", api_key)
    trending_data, err2 = fetch_json(f"{base}&sort=trending&limit=10", api_key)
    if err1:
        print(f"  ✗ app-rankings(popular) 失败，保留旧数据：{err1}")
        return False
    save_snapshot("app-rankings-popular", popular_data, today)
    if err2:
        print(f"  ⚠ app-rankings(trending) 失败，只更新 popular：{err2}")
        trending_data = None
    else:
        save_snapshot("app-rankings-trending", trending_data, today)

    as_of = popular_data["meta"]["as_of"]

    def to_rows(payload):
        return [{
            "rank": r["rank"],
            "app_name": r["app_name"],
            "app_id": r.get("app_id"),
            "tokens_t": to_t(r["total_tokens"]),
            "requests_k": round(r.get("total_requests", 0) / 1000, 1),
        } for r in payload["data"][:10]]

    payload = {
        "source": "OpenRouter Apps",
        "source_url": "https://openrouter.ai/apps",
        "snapshot_date": iso_date(end),
        "as_of": as_of,
        "window": {"start": iso_date(start), "end": iso_date(end)},
        "manual": False,
        "note": "经 OpenRouter 路由的公开应用 token 消耗榜（7 日窗口）。popular 按消耗量排名；"
                "trending 按绝对超额增长（窗口量减前三个等长周期均量）排名，增长为零的应用不入选。",
        "popular": to_rows(popular_data),
        "trending": to_rows(trending_data) if trending_data else [],
    }
    atomic_write("openrouter_apps.json", payload, dry_run)
    return True


def main():
    parser = argparse.ArgumentParser(description="OpenRouter 榜单数据抓取")
    parser.add_argument("--dry-run", action="store_true", help="不写文件")
    parser.add_argument("--only", choices=["rankings", "session-cost", "apps"], help="只跑指定数据集")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("⚠ 未设置 OPENROUTER_API_KEY，跳过榜单抓取（保留现有数据）")
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"== OpenRouter 榜单抓取 {today} ==")

    tasks = {
        "rankings": fetch_rankings,
        "session-cost": fetch_session_cost,
        "apps": fetch_apps,
    }
    results = []
    for name, fn in tasks.items():
        if args.only and name != args.only:
            continue
        print(f"[{name}]")
        results.append(fn(api_key, today, args.dry_run))

    ok = sum(results)
    print(f"== 完成：{ok}/{len(results)} 数据集成功 ==")
    if results and ok == 0:
        return 1  # 全部失败才报错（CI continue-on-error 兜底）
    return 0


if __name__ == "__main__":
    sys.exit(main())
