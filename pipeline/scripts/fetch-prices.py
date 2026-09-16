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
  6. Task 02：Evidence/事实版本/快照元数据持久化到 data/price-*，
     价格事件归档 data/price-records（稳定 id + 修订），索引 → site/src/data

工程约束：
- 原子写：*.tmp → os.replace()；单家失败不阻塞其余
- 原始渲染 HTML 存档：data/snapshots/<today>/pricing__<provider>.html
- --dry-run 真实不写文件（不落快照不建目录）；--only 未运行来源保留现有状态
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

from pricing import archive as pa                                  # noqa: E402
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
ARCHIVE_ROOT = BASE_DIR / "data"
SITE_INDEX_DIR = BASE_DIR / "site" / "src" / "data"

DEFAULT_CURRENCY = "CNY"


def atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def latest_history(include_today: bool = False) -> dict | None:
    """ledger_history 最近一份存档。

    include_today=False（默认）：排除今天，作日 diff 基线（既有口径）。
    include_today=True：含今天，作失败沿用的「最新成功」状态——同日先成功
    后失败时，沿用当天已成功的 facts，不回退到昨天（Task 02 §4.5）。
    """
    if not HISTORY_DIR.exists():
        return None
    today = _sh_today()
    files = sorted(p for p in HISTORY_DIR.glob("*.json")
                   if include_today or p.stem != today)
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
    """DiffResult → (变化事件列表, 新收录事件列表)。

    Task 02：unit 用事实真实 unit_quantity/unit_name，不再硬编码 per_1m_tokens；
    金额保持 Decimal 字符串原值。旧消费者（llm-digest/首页）读 unit 字段兼容。
    """
    def _unit(f: dict) -> str:
        uq, un = f.get("unit_quantity"), f.get("unit_name")
        if uq == 1_000_000 and un == "token":
            return "per_1m_tokens"   # 既有消费者口径
        return f"per_{uq}_{un}" if uq else "unknown"

    changes, news = [], []
    for d in diff.changed:
        nf, pf = d.new_fact, d.previous_fact
        changes.append({
            "id": pa.price_record_id(nf["fact_key"], _sh_today()),
            "provider": nf["provider_id"], "model": nf["model_key"],
            "component": nf["component"],
            "previous": pf.get("amount"), "current": nf.get("amount"),
            "currency": nf.get("currency"), "unit": _unit(nf),
            "unit_quantity": nf.get("unit_quantity"),
            "unit_name": nf.get("unit_name"),
            "changed_fields": d.changed_fields,
            "evidence_url": registry_urls.get(f"{nf['provider_id']}:pricing", ""),
        })
    for d in diff.new:
        nf = d.new_fact
        news.append({
            "id": pa.price_record_id(nf["fact_key"], _sh_today()),
            "provider": nf["provider_id"], "model": nf["model_key"],
            "component": nf["component"], "current": nf.get("amount"),
            "currency": nf.get("currency"), "unit": _unit(nf),
            "unit_quantity": nf.get("unit_quantity"),
            "unit_name": nf.get("unit_name"),
            "changed_fields": ["amount"],
            "evidence_url": registry_urls.get(f"{nf['provider_id']}:pricing", ""),
        })
    return changes, news


def _sh_today() -> str:
    """上海日历日（与归档事件口径一致，不依赖执行机器时区）。"""
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


async def run(only: list[str] | None, dry_run: bool) -> int:
    today = _sh_today()  # 上海日历日（与事件归档口径一致）
    snap_dir = SNAPSHOT_DIR / today
    if not dry_run:
        snap_dir.mkdir(parents=True, exist_ok=True)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    entries = all_entries()
    if only:
        entries = [e for e in entries if e.provider_id in only]
    registry_urls = {e.source_key: e.url for e in all_entries()}

    # Task 02 持久化目录
    versions_root = ARCHIVE_ROOT / pa.DIR_FACT_VERSIONS
    evidence_root = ARCHIVE_ROOT / pa.DIR_EVIDENCE
    snapshots_root = ARCHIVE_ROOT / pa.DIR_SNAPSHOTS
    records_root = ARCHIVE_ROOT / pa.DIR_PRICE_RECORDS
    revisions_root = ARCHIVE_ROOT / pa.DIR_PRICE_REVISIONS
    current_file = ARCHIVE_ROOT / pa.DIR_CURRENT

    # 上一轮数据（partial 沿用 + diff 基线）
    # Task 02 修正：失败沿用取「最新成功」历史（含今天，同日重跑不回退到昨天），
    # 日 diff 基线取「今天之外最近一份」（保持既有口径）
    prev_success = latest_history(include_today=True)
    prev_history = latest_history()
    prev_facts: dict[str, list[dict]] = {}   # provider_id → facts
    if prev_success:
        for f in prev_success.get("facts", []):
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
    # Task 02：归档两阶段收集（内存计划，统一预检后落盘）
    archive_plan: dict = {"snapshots": [], "evidence": [], "versions": []}
    source_states: list[dict] = []
    accepted_versions: list[str] = []
    events_plan: list[dict] = []
    evidence_links: dict[str, str] = {}   # 内存 ev id → 持久 ev_id（台账入口）
    now = time.time()

    try:
        for entry in entries:
            print(f"[{entry.source_key}] {entry.url}")
            spec = SourceSpec(source_key=entry.source_key, provider_id=entry.provider_id,
                              url=entry.url, fetcher_version="playwright-1")
            provider = provider_for(entry.source_key)
            try:
                snap = await provider.fetch(spec)
                # 原始渲染 HTML 存档（快照正文是抓取产物，不是归档契约文件；
                # 同名覆盖属既有行为——内容寻址的归档元数据在提交阶段写入）
                if not dry_run:
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

                # Task 02：归档记录先在内存构建（不落盘）——契约错误在
                # 提交阶段统一预检，抓取失败不吞 ArchiveError（验收 P1-2）
                if not dry_run:
                    _plan_provider_archive(
                        entry, snap, result, report, today, now,
                        archive_plan, evidence_links)
                source_states.append(pa.make_source_state(
                    entry.source_key, status="ok", latest_attempt_at=now,
                    last_success_at=now, coverage="full"))
            except pa.ArchiveError:
                # 归档契约错误（身份冲突/归档损坏）不是抓取失败：
                # 直接中止整个运行，不沿用上轮、不写任何后续产物
                raise
            except Exception as e:  # noqa: BLE001
                failed.append(entry.source_key)
                print(f"  ✗ 失败，沿用上轮: {e}")
                # partial：沿用该家最新成功 facts（无历史则跳过）
                if entry.provider_id in prev_facts:
                    reused = [dict(f, field_state="stale",
                                   stale_reason="fetch_failed") for f in prev_facts[entry.provider_id]]
                    all_facts.extend(reused)
                    print(f"    沿用上轮 {len(reused)} 条（stale）")
                source_states.append(pa.make_source_state(
                    entry.source_key, status="failed", latest_attempt_at=now,
                    last_success_at=_last_success_at(current_file, entry.source_key),
                    coverage="failed", reason=str(e)[:200]))
    finally:
        await PlaywrightSourceProvider.shutdown()

    if not all_facts:
        print("全部来源失败且无历史可沿用，保留旧 ledger.json")
        return 1

    # Task 02：--only 未运行的来源——保留状态 + 既有事实合回台账。
    # 否则局部调试会把全站台账覆盖成只有本次运行的厂商（T07 缺陷修正）。
    if only:
        ran = {e.provider_id for e in entries}
        for e in all_entries():
            if e.provider_id not in ran:
                source_states.append(pa.make_source_state(
                    e.source_key, status="not_run", latest_attempt_at=now,
                    last_success_at=_last_success_at(current_file, e.source_key),
                    coverage="not_run"))
                if e.provider_id in prev_facts:
                    reused = [dict(f, field_state="stale",
                                   stale_reason="not_run_kept")
                              for f in prev_facts[e.provider_id]]
                    all_facts.extend(reused)
                    print(f"  [not_run] {e.source_key} 保留既有 {len(reused)} 条事实")

    dataset = build_view_dataset(
        all_facts, profiles, source_urls,
        failed_sources=failed,
        published_at=time.time(),
        artifact_version=today,
        fx_snapshot=DEFAULT_FX,
        default_currency=DEFAULT_CURRENCY,
        evidence_links=evidence_links,
    )

    # diff 与事件（旧口径：daily_changes.price_changes 兼容消费者）
    # --only 时 diff 范围限定本次运行的厂商（合回的 not_run 事实不参与，
    # 避免未运行来源产生假 missing/unchanged 噪声）
    if prev_history:
        prev_all = prev_history.get("facts", [])
        if only:
            ran_ids = {e.provider_id for e in entries}
            diff_facts_in = [f for f in all_facts
                             if f["provider_id"] in ran_ids]
            prev_all = [f for f in prev_all
                        if f["provider_id"] in ran_ids]
        else:
            diff_facts_in = all_facts
        diff = diff_facts(diff_facts_in, prev_all)
        changes, news = events_from_diff(diff, registry_urls)
        events = changes + news
        print(f"diff: {len(diff.new)} 新增 / {len(diff.changed)} 变更 / "
              f"{len(diff.unchanged)} 不变 / {len(diff.missing)} 缺失")
        if not dry_run:
            if events:
                print(f"价格变化事件 {len(events)} 条 → daily_changes.json")
            write_price_changes(today, events)
            # Task 02：完整重算后零事件 → 撤回当日既有事件（全量范围才撤回，
            # --only 局部范围不清空未运行来源的事件）
            if not events and not only:
                withdrawn = _withdraw_today_events(records_root, revisions_root, today)
                if withdrawn:
                    print(f"撤回当日既有事件 {withdrawn} 条（重算无变化）")
    else:
        print("无历史存档，跳过 diff（首轮）")

    if dry_run:
        print("dry-run：不写文件（含快照）")
        print(f"  providers={dataset['providers']}")
        print(f"  prices={len(dataset['prices'])}")
        total_ran = len(entries)
        if total_ran and len(failed) == total_ran:
            print("RUN-STATUS: failed——全部来源抓取失败，检查运行环境（Playwright/网络）")
            return 2
        print(f"RUN-STATUS: {'partial' if failed else 'ok'} "
              f"{total_ran - len(failed)}/{total_ran} 来源成功")
        return 0

    # Task 02：归档提交（两阶段——全量预检零写入，再统一落盘）。
    # 任何契约冲突在任何来源发现 → 抛 ArchiveError，此时无任何写入（P1-2）。
    if archive_plan:
        _commit_archive_plan(
            archive_plan, today, versions_root, evidence_root,
            snapshots_root, source_states, prev_history, entries, events_plan)
    accepted_versions.extend(archive_plan.get("_accepted_versions", []))

    atomic_write(LEDGER_FILE, dataset)
    # ledger_history 存全量事实（--only 时含合回的 not_run 来源），
    # 保证次日全量 diff 的基线完整，不被局部调试截断
    atomic_write(HISTORY_DIR / f"{today}.json",
                 {"date": today, "facts": all_facts})

    # 事件合并（归档提交后；事件自身有修订链恢复）
    for event in events_plan:
        pa.merge_price_event(records_root, revisions_root, event)

    current = pa.load_current(current_file)
    _update_current(current, accepted_versions, versions_root, source_states)
    pa.save_current(current_file, current)
    SITE_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_INDEX_DIR / pa.INDEX_PRICE).write_text(
        json.dumps(pa.build_price_index(records_root), ensure_ascii=False, indent=2),
        encoding="utf-8")
    (SITE_INDEX_DIR / pa.INDEX_EVIDENCE).write_text(
        json.dumps(pa.build_evidence_index(evidence_root), ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"ledger.json 已更新：{len(dataset['prices'])} 条价格 · "
          f"{dataset['providers']} 家" + ("（partial）" if failed else ""))

    # 运行状态（验收 2026-09-16：全来源失败不能返回 0，否则运行环境
    # 完全失效（如 Playwright 未安装）会被 CI 当成成功掩盖）。
    # - 全部来源失败（无论是否有历史可沿用）→ 退出码 2
    # - 部分失败（失败沿用降级生效）→ 退出码 0，状态行标 partial
    total_ran = len(entries)
    ok_count = total_ran - len(failed)
    if failed:
        print(f"RUN-STATUS: partial {ok_count}/{total_ran} 来源成功"
              f"（失败: {', '.join(failed)}）")
    else:
        print(f"RUN-STATUS: ok {ok_count}/{total_ran} 来源成功")
    if total_ran and ok_count == 0:
        print("RUN-STATUS: failed——全部来源抓取失败，检查运行环境（Playwright/网络）")
        return 2
    return 0


def _plan_provider_archive(entry, snap, result, report, today, now,
                           archive_plan, evidence_links) -> None:
    """单来源抓取结果 → 归档记录（仅内存构建，不落盘）。

    契约错误（金额非法等）在此抛出 → 上层 ArchiveError 直通分支中止整个运行。
    """
    snap_record = pa.make_snapshot_record(
        source_key=entry.source_key, provider_id=entry.provider_id,
        url=entry.url, content_sha256=snap.sha256,
        fetcher_version=entry.fetcher_version)

    ev_records = []
    old_to_new = {}
    for ev in result.evidence:
        text = (pa.html_excerpt_to_text(ev.excerpt or "")
                if ev.locator_type == "dom_selector" else (ev.excerpt or ""))
        completeness, reasons = pa.assess_evidence_completeness(text, ev.locator_type)
        rec = pa.make_evidence_record(
            snapshot=snap_record, locator_type=ev.locator_type, locator=ev.locator,
            excerpt_text=text, extractor_version=ev.extractor_version or "",
            completeness=completeness, reasons=reasons)
        ev_records.append(rec)
        old_to_new[ev.evidence_id] = rec

    archive_plan["snapshots"].append(snap_record)
    archive_plan["evidence"].extend(ev_records)

    for fact in report.accepted:
        f_dict = fact_to_dict(fact)
        new_evid = old_to_new.get(f_dict.get("evidence_id"))
        evidence_status = ("complete" if new_evid and new_evid["completeness"] == "complete"
                           else "partial" if new_evid else "unavailable")
        if evidence_status == "complete" and new_evid:
            # 绑定事实验证（P1-3）：complete 必须能复核这条事实
            evidence_status = pa.fact_evidence_status(new_evid, f_dict)
        f_dict["evidence_id"] = new_evid["id"] if new_evid else None
        version = pa.make_fact_version(f_dict, source_key=entry.source_key,
                                       evidence_status=evidence_status)
        archive_plan["versions"].append(version)
        archive_plan.setdefault("_accepted_versions", []).append(
            version["version_id"])
        if new_evid:
            evidence_links[fact.evidence_id] = new_evid["id"]


def _commit_archive_plan(archive_plan, today, versions_root, evidence_root,
                         snapshots_root, source_states, prev_history,
                         entries, events_plan,
                         runs_root: Path | None = None) -> None:
    """两阶段提交：全量预检（零写入）→ 统一落盘 → 事件判定。

    预检：计划内重复 ID 内容冲突、计划与磁盘不可变文件冲突。
    任一失败抛 ArchiveError——此时没有任何写入发生（验收 P1-2）。
    runs_root：运行记录目录（默认真实归档；测试注入沙箱）。
    """
    # ---- 阶段 1：预检（零写入） ----
    seen: dict[str, str] = {}
    for v in archive_plan["versions"]:
        vid = v["version_id"]
        body = pa.canonical_json(v)
        if vid in seen and seen[vid] != body:
            raise pa.ArchiveError(f"计划内版本内容冲突: {vid}")
        seen[vid] = body
        disk = versions_root / f"{vid}.json"
        if disk.exists():
            if disk.read_text(encoding="utf-8") != json.dumps(
                    v, ensure_ascii=False, indent=2):
                raise pa.ArchiveError(
                    f"不可变版本文件已存在且内容不同，拒绝覆盖: {disk}")
    for rec in archive_plan["evidence"]:
        ev_file = evidence_root / f"{rec['id']}.json"
        if ev_file.exists():
            if ev_file.read_text(encoding="utf-8") != json.dumps(
                    rec, ensure_ascii=False, indent=2):
                raise pa.ArchiveError(
                    f"不可变证据文件已存在且内容不同，拒绝覆盖: {ev_file}")
    for rec in archive_plan["snapshots"]:
        snap_file = snapshots_root / f"{rec['id']}.json"
        if snap_file.exists():
            if snap_file.read_text(encoding="utf-8") != json.dumps(
                    rec, ensure_ascii=False, indent=2):
                raise pa.ArchiveError(
                    f"不可变快照元数据已存在且内容不同，拒绝覆盖: {snap_file}")

    # ---- 阶段 2：统一落盘（不可变，幂等） ----
    for rec in archive_plan["snapshots"]:
        pa.save_snapshot_meta(snapshots_root, rec)
    for rec in archive_plan["evidence"]:
        pa.save_evidence(evidence_root, rec)
    for v in archive_plan["versions"]:
        pa.save_fact_version(versions_root, v)

    # ---- 事件判定（版本已提交；基线 = 前日固定基线） ----
    baseline = _baseline_before(versions_root, today)
    versions_by_key: dict[str, list] = {}
    for v in archive_plan["versions"]:
        versions_by_key.setdefault(v["fact_key"], []).append(v)
    for fk, vs in versions_by_key.items():
        latest = max(vs, key=lambda x: x.get("observed_at") or 0)
        prev_version = baseline.get(fk)
        if prev_version is None:
            events_plan.append(pa.build_price_event(
                today, fk, None, latest, pa.compare_versions(None, latest)))
        else:
            cmp_result = pa.compare_versions(prev_version, latest)
            if cmp_result["changeType"] != "newly_observed":
                events_plan.append(pa.build_price_event(
                    today, fk, prev_version, latest, cmp_result))

    # ---- 运行记录（committed） ----
    run = pa.make_run_record(
        today, f"fetch-{today}", scope=[e.source_key for e in entries],
        source_states=source_states,
        accepted_versions=archive_plan.get("_accepted_versions", []),
        baseline=str(prev_history.get("date")) if prev_history else None)
    pa.commit_run((runs_root if runs_root is not None
                   else ARCHIVE_ROOT / pa.DIR_RUNS), run)


def _baseline_before(versions_root: Path, date: str) -> dict[str, dict]:
    """目标日开始时刻（上海 00:00）之前最后接受的版本（§4.4 前日固定基线）。

    cutoff = date 当日上海零点。同日多次变化（10 → 8 → 9）始终与前一日
    基线（10）比较——同日已写入的版本不进入基线，事件表示为 10 → 9，
    当日回到旧值（8 → 10）不产生事件（与基线同值）。
    """
    from datetime import timedelta, timezone as tz
    day = datetime.strptime(date, "%Y-%m-%d")
    cutoff = day.replace(tzinfo=tz(timedelta(hours=8))).timestamp()
    out: dict[str, dict] = {}
    if not versions_root.exists():
        return out
    for f in versions_root.glob("pfv_*.json"):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if (v.get("observed_at") or 0) >= cutoff:
            continue
        fk = v.get("fact_key")
        prev = out.get(fk)
        if prev is None or (v.get("observed_at") or 0) > (prev.get("observed_at") or 0):
            out[fk] = v
    return out


def _last_success_at(current_file: Path, source_key: str) -> float | None:
    """来源最新成功时间（从 current 的 sources 取，失败沿用展示用）。"""
    try:
        cur = pa.load_current(current_file)
        s = cur.get("sources", {}).get(source_key)
        return s.get("last_success_at") if s else None
    except pa.ArchiveError:
        return None


def _update_current(current: dict, accepted_versions: list[str],
                    versions_root: Path, source_states: list[dict]) -> None:
    """把本日接受的版本与来源状态合入 current。

    只前进不回退：本日版本 observed_at 更新才替换 current.facts；
    sources 记 latest_attempt_at / last_success_at（失败沿用展示用）。
    """
    facts = current.setdefault("facts", {})
    sources = current.setdefault("sources", {})
    for vid in accepted_versions:
        f = versions_root / f"{vid}.json"
        if not f.exists():
            continue
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        fk = v["fact_key"]
        prev = facts.get(fk)
        if prev is None or (v.get("observed_at") or 0) >= (prev.get("observed_at") or 0):
            facts[fk] = {
                "version_id": v["version_id"],
                "observed_at": v.get("observed_at"),
                "evidence_id": v.get("evidence_id"),
            }
    for s in source_states:
        prev = sources.get(s["source_key"]) or {}
        sources[s["source_key"]] = {
            "status": s["status"],
            "latest_attempt_at": s["latest_attempt_at"],
            "last_success_at": (s.get("last_success_at")
                                or prev.get("last_success_at")),
            "coverage": s["coverage"],
            "reason": s.get("reason"),
        }


def _withdraw_today_events(records_root: Path, revisions_root: Path,
                           today: str) -> int:
    """完整重算零事件 → 撤回当日既有事件（保留链接与原因）。"""
    n = 0
    if not records_root.exists():
        return 0
    for f in records_root.glob("price_*.json"):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if r.get("date") == today and r.get("status") == "active":
            pa.withdraw_price_event(records_root, revisions_root, r["id"])
            n += 1
    return n


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
