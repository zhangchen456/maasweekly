#!/usr/bin/env python3
"""8 家厂商 API 价格结构化抓取入口（对齐 fetch-leaderboards.py 模式）。

执行流：
  1. registry 八家定价页 → playwright 渲染（Kimi 多子页聚合）
  2. 每家 extractor 解析 → normalize 门禁
  3. 单家失败：记入 meta.failed_sources，沿用该家上一轮 facts（partial 模式）
  4. view_data 构建归一化 dataset（每 1M tokens、CNY/USD）→ ledger.json
  5. 与 ledger_history 最近一份 factdiff：
     - 变化事件写入 daily_changes.json 当日 price_changes（llm-digest 消费 → 今日要点）
     - 全量 facts 快照存 ledger_history/<today>.json

工程约束：
- 原子写：*.tmp → os.replace()；单家失败不阻塞其余
- 原始渲染 HTML 存档：data/snapshots/<today>/pricing__<provider>.html
- 依赖：playwright + beautifulsoup4（beautifulsoup4 是解析层唯一第三方依赖）

用法：
  python3 pipeline/scripts/fetch-prices.py [--dry-run] [--only openai,deepseek]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(BASE_DIR / "pipeline"))

from pricing.base import SourceSpec                      # noqa: E402
from pricing.extractors import get_extractor             # noqa: E402
from pricing.factdiff import diff_facts                  # noqa: E402
from pricing.normalize import normalize_and_validate     # noqa: E402
from pricing.providers import PlaywrightSourceProvider, provider_for, KimiPlaywrightProvider  # noqa: E402
from pricing.registry import all_entries                 # noqa: E402
from pricing.view_data import DEFAULT_FX, build_view_dataset, fact_to_dict  # noqa: E402

PRICING_DIR = BASE_DIR / "site" / "src" / "data" / "pricing"
LEDGER_FILE = PRICING_DIR / "ledger.json"
HISTORY_DIR = PRICING_DIR / "ledger_history"
SNAPSHOT_DIR = BASE_DIR / "data" / "snapshots"
DAILY_FILE = BASE_DIR / "site" / "src" / "data" / "daily_changes.json"

DEFAULT_CURRENCY = "CNY"


def atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def latest_history() -> dict | None:
    """ledger_history 最近一份存档（今天之外的，避免与自身对比）。"""
    if not HISTORY_DIR.exists():
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    files = sorted(p for p in HISTORY_DIR.glob("*.json") if p.stem != today)
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_price_changes(today: str, changes: list[dict]) -> None:
    """价格变化事件写入 daily_changes.json 当日 price_changes 数组。"""
    if not changes:
        return
    data = json.loads(DAILY_FILE.read_text(encoding="utf-8")) if DAILY_FILE.exists() else {"days": []}
    day = next((d for d in data.get("days", []) if d.get("date") == today), None)
    if day is None:
        day = {"date": today, "stats": {}, "changed": [], "first_fetch": False, "failed": []}
        data["days"].append(day)
        data["days"].sort(key=lambda d: d.get("date", ""))
    day["price_changes"] = changes
    atomic_write(DAILY_FILE, data)


def events_from_diff(diff, registry_urls: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """DiffResult → (变化事件列表, 新闻本事实列表)。变化含 changed；new 是新上架（另一种事件）。"""
    changes, news = [], []
    for d in diff.changed:
        nf, pf = d.new_fact, d.previous_fact
        changes.append({
            "provider": nf["provider_id"], "model": nf["model_key"],
            "component": nf["component"],
            "previous": pf.get("amount"), "current": nf.get("amount"),
            "currency": nf.get("currency"), "unit": "per_1m_tokens",
            "changed_fields": d.changed_fields,
            "evidence_url": registry_urls.get(f"{nf['provider_id']}:pricing", ""),
        })
    for d in diff.new:
        nf = d.new_fact
        news.append({
            "provider": nf["provider_id"], "model": nf["model_key"],
            "component": nf["component"], "current": nf.get("amount"),
            "currency": nf.get("currency"), "unit": "per_1m_tokens",
            "changed_fields": ["amount"],
            "evidence_url": registry_urls.get(f"{nf['provider_id']}:pricing", ""),
        })
    return changes, news


async def run(only: list[str] | None, dry_run: bool) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    snap_dir = SNAPSHOT_DIR / today
    snap_dir.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    entries = all_entries()
    if only:
        entries = [e for e in entries if e.provider_id in only]
    registry_urls = {e.source_key: e.url for e in all_entries()}

    # 上一轮数据（partial 沿用 + diff 基线）
    prev_history = latest_history()
    prev_facts: dict[str, list[dict]] = {}   # provider_id → facts
    if prev_history:
        for f in prev_history.get("facts", []):
            prev_facts.setdefault(f["provider_id"], []).append(f)

    ledger_old: dict = {}
    if LEDGER_FILE.exists():
        try:
            ledger_old = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ledger_old = {}

    failed: list[str] = []
    all_facts: list[dict] = []
    profiles: dict[str, str] = {}
    source_urls: dict[str, str] = {}

    try:
        for entry in entries:
            print(f"[{entry.source_key}] {entry.url}")
            spec = SourceSpec(source_key=entry.source_key, provider_id=entry.provider_id,
                              url=entry.url, fetcher_version="playwright-1")
            provider = provider_for(entry.source_key)
            try:
                snap = await provider.fetch(spec)
                # 原始渲染 HTML 存档
                (snap_dir / f"pricing__{entry.provider_id}.html").write_text(
                    snap.content, encoding="utf-8")
                result = get_extractor(entry.source_key).extract(snap)
                report = normalize_and_validate(result)
                if not report.accepted:
                    raise ValueError(
                        f"门禁全拒（{len(report.rejected)} 条），疑似结构漂移")
                for w in result.warnings:
                    print(f"  warn: {w}")
                for m in result.models:
                    profiles[f"{m.provider_id}:{m.model_key}"] = m.display_name
                for e in result.evidence:
                    source_urls[e.evidence_id] = snap.url
                facts = [fact_to_dict(f) for f in report.accepted]
                print(f"  ✓ {len(facts)} facts / {len(result.models)} models")
                all_facts.extend(facts)
            except Exception as e:  # noqa: BLE001
                failed.append(entry.source_key)
                print(f"  ✗ 失败，沿用上轮: {e}")
                # partial：沿用该家上一轮 facts（无历史则跳过）
                if entry.provider_id in prev_facts:
                    reused = [dict(f, field_state="stale",
                                   stale_reason="fetch_failed") for f in prev_facts[entry.provider_id]]
                    all_facts.extend(reused)
                    print(f"    沿用上轮 {len(reused)} 条（stale）")
    finally:
        await PlaywrightSourceProvider.shutdown()

    if not all_facts:
        print("全部来源失败且无历史可沿用，保留旧 ledger.json")
        return 1

    dataset = build_view_dataset(
        all_facts, profiles, source_urls,
        failed_sources=failed,
        published_at=time.time(),
        artifact_version=today,
        fx_snapshot=DEFAULT_FX,
        default_currency=DEFAULT_CURRENCY,
    )

    # diff 与事件
    if prev_history:
        prev_all = prev_history.get("facts", [])
        diff = diff_facts(all_facts, prev_all)
        changes, news = events_from_diff(diff, registry_urls)
        events = changes + news
        print(f"diff: {len(diff.new)} 新增 / {len(diff.changed)} 变更 / "
              f"{len(diff.unchanged)} 不变 / {len(diff.missing)} 缺失")
        if events:
            print(f"价格变化事件 {len(events)} 条 → daily_changes.json")
            if not dry_run:
                write_price_changes(today, events)
    else:
        print("无历史存档，跳过 diff（首轮）")

    if dry_run:
        print("dry-run：不写文件")
        print(f"  providers={dataset['providers']}")
        print(f"  prices={len(dataset['prices'])}")
        return 0

    atomic_write(LEDGER_FILE, dataset)
    atomic_write(HISTORY_DIR / f"{today}.json",
                 {"date": today, "facts": all_facts})
    print(f"ledger.json 已更新：{len(dataset['prices'])} 条价格 · "
          f"{len(dataset['providers'])} 家" + ("（partial）" if failed else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    ap.add_argument("--only", help="只跑指定厂商（逗号分隔，如 openai,deepseek）")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    try:
        return asyncio.run(run(only, args.dry_run))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
