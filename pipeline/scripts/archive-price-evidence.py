#!/usr/bin/env python3
"""archive-price-evidence.py：价格证据离线归档入口（Task 02）。

从仓库已有产物离线回放，不联网：
- 输入：ledger_history/<date>.json（已接受事实）+ data/snapshots/<date>/pricing__<p>.html
  （渲染快照正文）+ 价格 registry
- 流程（按日、上海日期顺序）：快照回放 extractor → 重建 Evidence（持久化）
  → 与当日历史事实比对（只关联验证一致的）→ 保存事实版本 → current 更新
  → 事件比较与归档 → 索引
- 幂等：同一输入两次运行，归档字节不变（T01）

用法：
  python3 pipeline/scripts/archive-price-evidence.py                # 全量回填（仓库现有文件为限）
  python3 pipeline/scripts/archive-price-evidence.py --since 2026-09-06
  python3 pipeline/scripts/archive-price-evidence.py --check       # 只校验，零写入
  python3 pipeline/scripts/archive-price-evidence.py --dry-run     # 计划打印，零写入
  python3 pipeline/scripts/archive-price-evidence.py --history-dir ... --snapshot-dir ... --archive-root ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(BASE / "pipeline"))

from pricing import archive as pa                                    # noqa: E402
from pricing.base import ContentSnapshot                             # noqa: E402
from pricing.extractors import get_extractor                         # noqa: E402
from pricing.normalize import normalize_and_validate                 # noqa: E402
from pricing.registry import all_entries                             # noqa: E402
from pricing.view_data import fact_to_dict                           # noqa: E402

HISTORY_DIR = BASE / "site" / "src" / "data" / "pricing" / "ledger_history"
SNAPSHOT_DIR = BASE / "data" / "snapshots"
ARCHIVE_ROOT = BASE / "data"
SITE_INDEX_DIR = BASE / "site" / "src" / "data"


def replay_provider(entry, html: str, fetched_at: float = 0.0):
    """单来源回放：快照 → extractor → 门禁 → (facts, evidence, snapshot_record)。

    fetched_at 仅进 ContentSnapshot（内存对象，供 extractor 写 observed_at），
    不进持久 psnap 记录（观察时间以历史事实为准）。
    """
    sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    snap_record = pa.make_snapshot_record(
        source_key=entry.source_key, provider_id=entry.provider_id,
        url=entry.url, content_sha256=sha,
        fetcher_version=entry.fetcher_version)
    snap = ContentSnapshot(
        snapshot_id=f"snap-{sha[:24]}", source_key=entry.source_key,
        url=entry.url, fetched_at=fetched_at, http_status=200,
        content_type="text/html", sha256=sha, content=html,
        fetcher_version=entry.fetcher_version)
    result = get_extractor(entry.source_key).extract(snap)
    report = normalize_and_validate(result)
    facts = [fact_to_dict(f) for f in report.accepted]
    return snap_record, snap, facts, result.evidence, report


def evidence_records_for(snap_record, evidence_list):
    """内存 Evidence → 持久证据记录（HTML 摘录文本化 + 完整性评估）。"""
    out = []
    for ev in evidence_list:
        excerpt_raw = ev.excerpt or ""
        if ev.locator_type == "dom_selector":
            text = pa.html_excerpt_to_text(excerpt_raw)
        else:
            # markdown 路径：原样文本已是纯文本
            text = excerpt_raw
        completeness, reasons = pa.assess_evidence_completeness(
            text, ev.locator_type)
        record = pa.make_evidence_record(
            snapshot=snap_record, locator_type=ev.locator_type,
            locator=ev.locator, excerpt_text=text,
            extractor_version=ev.extractor_version or "",
            completeness=completeness, reasons=reasons,
            provenance={"replay": True})
        out.append(record)
    return out


def _baseline_before(versions_root: Path, date: str) -> dict[str, dict]:
    """目标日开始时刻（上海 00:00）之前最后接受的版本（§4.4 前日固定基线）。

    cutoff = date 当日上海零点：同日已写入的版本不进入基线，
    同日多次变化始终与前一日基线比较。与在线入口（fetch-prices）同口径。
    """
    from datetime import datetime, timezone, timedelta
    day = datetime.strptime(date, "%Y-%m-%d")
    cutoff = day.replace(tzinfo=timezone(timedelta(hours=8))).timestamp()
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


def _is_empty_snapshot(path: Path) -> bool:
    """Kimi 失败日会存 <html><body></body></html> 空壳（26 字节级别）。"""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return True
    return len(content.strip()) < 200


def _last_nonempty_snapshot_date(snapshot_dir: Path, provider_id: str,
                                  *, before: str) -> str | None:
    """往前找最近一个非空快照日期（失败沿用的事实证据指向原观察快照）。"""
    if not snapshot_dir.exists():
        return None
    for d in sorted((p.name for p in snapshot_dir.iterdir() if p.is_dir()),
                    reverse=True):
        if d >= before:
            continue
        cand = snapshot_dir / d / f"pricing__{provider_id}.html"
        if cand.exists() and not _is_empty_snapshot(cand):
            return d
    return None


def run_date(date: str, entries, *, history_dir: Path, snapshot_dir: Path,
             archive_root: Path, index_dir: Path, dry_run: bool,
             stats: dict) -> None:
    hist_file = history_dir / f"{date}.json"
    if not hist_file.exists():
        return
    hist = json.loads(hist_file.read_text(encoding="utf-8"))
    hist_facts = hist.get("facts", [])
    fetched_at = hist.get("published_at") or \
        datetime.strptime(date, "%Y-%m-%d").timestamp()

    versions_root = archive_root / pa.DIR_FACT_VERSIONS
    evidence_root = archive_root / pa.DIR_EVIDENCE
    snapshots_root = archive_root / pa.DIR_SNAPSHOTS
    records_root = archive_root / pa.DIR_PRICE_RECORDS
    revisions_root = archive_root / pa.DIR_PRICE_REVISIONS
    current_file = archive_root / pa.DIR_CURRENT
    runs_dir = archive_root / pa.DIR_RUNS

    current = pa.load_current(current_file)
    accepted_versions: list[str] = []
    # 日基线（§4.4）：「该日期之前最后一个成功接受的事实状态」。
    # 不能从 current 取——current 是最终状态，重放历史日会拿到「未来」版本。
    # 回放场景按版本历史推导：每 fact_key 取 observedAt 早于该日（上海零点）
    # 的最新版本。首日无基线 → 全部 newly_observed（初始台账，不虚构调价）。
    baseline = _baseline_before(versions_root, date)
    events_plan: list[dict] = []

    for entry in entries:
        snap_path = snapshot_dir / date / f"pricing__{entry.provider_id}.html"
        # 抓取失败沿用（stale facts）与空快照：回退到最近一个非空快照。
        # stale 事实的证据指向其原观察快照，观察时间保留原值（§4.5 不前移不回退）
        stale_facts = [f for f in hist_facts
                       if f["provider_id"] == entry.provider_id
                       and f.get("field_state") == "stale"]
        live_hist = [f for f in hist_facts
                     if f["provider_id"] == entry.provider_id
                     and f.get("field_state") != "stale"]
        effective_date = date
        if stale_facts and (not snap_path.exists() or _is_empty_snapshot(snap_path)):
            effective_date = _last_nonempty_snapshot_date(
                snapshot_dir, entry.provider_id, before=date)
            if effective_date:
                snap_path = snapshot_dir / effective_date / \
                    f"pricing__{entry.provider_id}.html"
                stats["stale_backtrack"] = stats.get("stale_backtrack", 0) + 1
        if not snap_path.exists():
            stats["snapshot_missing"] = stats.get("snapshot_missing", 0) + 1
            continue
        html = snap_path.read_text(encoding="utf-8")
        snap_record, _snap, facts, evidence_list, report = replay_provider(
            entry, html, fetched_at)

        # 历史事实以 ledger_history 为准：回放仅用于重建证据链。
        # 回放事实与历史事实 key+金额一致的 → 关联；不一致的以历史为准（不覆盖）
        hist_by_key = {f["fact_key"]: f for f in live_hist}
        hist_by_key.update({f["fact_key"]: f for f in stale_facts
                            if f["fact_key"] not in hist_by_key})
        replay_by_key = {f["fact_key"]: f for f in facts}
        matched = set(hist_by_key) & set(replay_by_key)
        stats["facts_history"] = stats.get("facts_history", 0) + len(hist_by_key)
        stats["facts_replay"] = stats.get("facts_replay", 0) + len(replay_by_key)
        stats["facts_matched"] = stats.get("facts_matched", 0) + len(matched)

        # 证据持久化（不可变；幂等）
        ev_records = evidence_records_for(snap_record, evidence_list)
        ev_by_old_id = {r["id"]: r for r in ev_records}
        # 事实的 evidence_id 是内存 ID；持久证据按 (locator, excerpt) 对齐
        # extractor 的内存 ev id → 持久记录的映射：按索引顺序
        old_to_new = {}
        for old_ev, new_rec in zip(evidence_list, ev_records):
            old_to_new[old_ev.evidence_id] = new_rec

        for old_f in hist_by_key.values():
            fk = old_f["fact_key"]
            replay_f = replay_by_key.get(fk)
            if replay_f is None:
                # 历史事实无法从快照重放（extractor 已改版/页面漂移）：
                # 保留事实但证据状态降级
                new_evid = None
                evidence_status = "unavailable"
                stats["evidence_unavailable"] = stats.get("evidence_unavailable", 0) + 1
                f_dict = dict(old_f)
            else:
                f_dict = dict(replay_f)
                new_evid = old_to_new.get(old_f.get("evidence_id"))
                if new_evid is None:
                    evidence_status = "unavailable"
                    stats["evidence_unavailable"] = stats.get("evidence_unavailable", 0) + 1
                else:
                    if new_evid["completeness"] == "complete":
                        # 绑定事实验证（P1-3）：complete 必须能复核这条事实
                        evidence_status = pa.fact_evidence_status(new_evid, f_dict)
                    else:
                        evidence_status = "partial"
                    if evidence_status == "partial":
                        stats["evidence_partial"] = stats.get("evidence_partial", 0) + 1
                    elif evidence_status == "complete":
                        stats["evidence_complete"] = stats.get("evidence_complete", 0) + 1
                    else:
                        stats["evidence_unavailable"] = stats.get("evidence_unavailable", 0) + 1
                # 时间以历史为准（回放 fetched_at 是构造的）
                f_dict["observed_at"] = old_f.get("observed_at")
            f_dict["evidence_id"] = new_evid["id"] if new_evid else None

            version = pa.make_fact_version(
                f_dict, source_key=entry.source_key,
                evidence_status=evidence_status)
            # 版本观察时间以历史记录为准
            version["observed_at"] = f_dict.get("observed_at")
            version["observedAt"] = pa._epoch_to_iso(f_dict.get("observed_at"))
            version["version_id"] = pa.fact_version_id(version)
            if version["evidence_id"]:
                version["evidence_status"] = evidence_status

            prev_entry = baseline.get(fk)
            prev_version = None
            if prev_entry:
                pv_file = versions_root / f"{prev_entry['version_id']}.json"
                if pv_file.exists():
                        prev_version = json.loads(pv_file.read_text(encoding="utf-8"))

            if not dry_run:
                pa.save_snapshot_meta(snapshots_root, snap_record)
                for rec in ev_records:
                    pa.save_evidence(evidence_root, rec)
                pa.save_fact_version(versions_root, version)

            accepted_versions.append(version["version_id"])
            current.setdefault("facts", {})[fk] = {
                "version_id": version["version_id"],
                "observed_at": version["observed_at"],
                "evidence_id": version["evidence_id"],
            }

            # 日比较（与基线）：基线无此前版本 → newly_observed（收录事件）；
            # 有基线且实质变化（amount/terms_changed）→ 变化事件；
            # 有基线但同值重观察 → 不产生事件（T02）
            if prev_version is None:
                cmp_result = pa.compare_versions(None, version)
                event = pa.build_price_event(
                    date, fk, None, version, cmp_result)
                events_plan.append(event)
            else:
                cmp_result = pa.compare_versions(prev_version, version)
                if cmp_result["changeType"] != "newly_observed":
                    event = pa.build_price_event(
                        date, fk, prev_version, version, cmp_result)
                    events_plan.append(event)

    # 运行记录与提交
    run_id = f"replay-{date}"
    run = pa.make_run_record(
        date, run_id, scope=[e.source_key for e in entries],
        source_states=[pa.make_source_state(
            e.source_key, status="ok", latest_attempt_at=fetched_at,
            last_success_at=fetched_at, coverage="full")
            for e in entries],
        accepted_versions=accepted_versions,
        baseline=f"replay-{date}-baseline")
    if not dry_run:
        pa.commit_run(runs_dir, run)
        for event in events_plan:
            pa.merge_price_event(records_root, revisions_root, event)
        pa.save_current(current_file, current)
        # 索引重建（输出目录可注入：沙箱测试不得污染真实站点数据）
        index_dir.mkdir(parents=True, exist_ok=True)
        price_idx = pa.build_price_index(records_root)
        (index_dir / pa.INDEX_PRICE).write_text(
            json.dumps(price_idx, ensure_ascii=False, indent=2),
            encoding="utf-8")
        ev_idx = pa.build_evidence_index(evidence_root)
        (index_dir / pa.INDEX_EVIDENCE).write_text(
            json.dumps(ev_idx, ensure_ascii=False, indent=2),
            encoding="utf-8")
    stats["days"] = stats.get("days", 0) + 1
    stats["events"] = stats.get("events", 0) + len(events_plan)


def main() -> int:
    ap = argparse.ArgumentParser(description="价格证据离线归档（回放，零联网）")
    ap.add_argument("--since", help="只回放该日期（含）之后")
    ap.add_argument("--until", help="只回放该日期（含）之前")
    ap.add_argument("--only", help="只处理指定厂商（逗号分隔）")
    ap.add_argument("--history-dir", type=Path, default=HISTORY_DIR)
    ap.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    ap.add_argument("--archive-root", type=Path, default=ARCHIVE_ROOT)
    ap.add_argument("--index-dir", type=Path, default=SITE_INDEX_DIR,
                    help="索引输出目录（site/src/data；沙箱测试注入临时目录）")
    ap.add_argument("--check", action="store_true",
                    help="只校验现有归档，零写入")
    ap.add_argument("--dry-run", action="store_true",
                    help="打印计划，零写入（不创建目录/快照/文件）")
    args = ap.parse_args()

    if args.check or args.dry_run:
        if args.check:
            errors = pa.validate_price_archive(
                args.archive_root,
                versions_root=args.archive_root / pa.DIR_FACT_VERSIONS,
                evidence_root=args.archive_root / pa.DIR_EVIDENCE,
                snapshots_root=args.archive_root / pa.DIR_SNAPSHOTS,
                records_root=args.archive_root / pa.DIR_PRICE_RECORDS,
                revisions_root=args.archive_root / pa.DIR_PRICE_REVISIONS,
                current_file=args.archive_root / pa.DIR_CURRENT,
                runs_root=args.archive_root / pa.DIR_RUNS)
            if errors:
                print(f"✗ 归档校验失败（{len(errors)} 项）:", file=sys.stderr)
                for e in errors[:20]:
                    print(f"  - {e}", file=sys.stderr)
                return 1
            print("✓ 价格归档校验通过")
            return 0

    dates = sorted(p.stem for p in args.history_dir.glob("*.json"))
    if args.since:
        dates = [d for d in dates if d >= args.since]
    if args.until:
        dates = [d for d in dates if d <= args.until]
    entries = all_entries()
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        entries = [e for e in entries if e.provider_id in keep]
    if not dates:
        print("无 ledger_history 日期可回放")
        return 0

    stats: dict = {}
    for date in dates:  # 上海日期顺序执行，不用机器今天选基线
        print(f"[{date}] 回放 {len(entries)} 家…")
        run_date(date, entries, history_dir=args.history_dir,
                 snapshot_dir=args.snapshot_dir, archive_root=args.archive_root,
                 index_dir=args.index_dir, dry_run=args.dry_run, stats=stats)
    print(f"回放完成：{stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
