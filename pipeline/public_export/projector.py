"""projector：原始归档 → 公开实体（Task 03 M2）。

字段映射采用白名单提取（显式列出每个输出字段），杜绝 provenance 等
内部字段（含本地路径）泄漏。任何缺字段/未知身份 → ExportError，
不静默修复、不猜测。

映射规则要点（见 docs/contracts/public-api-v1.md）：
- id/revision/status/permalink 原样保留——exporter 不重算公开 ID
- providerId 经 public_providers.json 显式映射；未知 sourceId 是门禁错误
- Task 01 记录 evidenceIds=[]（证据即来源 diff 本身，evidenceLevel=
  source_diff 已语义化；不伪造 ev_ 实体）
- Task 02 价格事件嵌入 before/after 事实版本与 comparison 原样
- prices 只投影 current.json 指向的已接受版本（stale 照常返回并带状态）
- quality 从 current.json sources / daily_changes failed 推导
"""
from __future__ import annotations

from collections import defaultdict

from .loaders import ExportError

# Task 07 T07-3：model identity 公开投影（唯一入口——registry 损坏 fail closed）
try:
    from model_identity.projector import ModelIdentityProjector
    _mi_projector = ModelIdentityProjector()
    _mi_gate_errors: list[str] = []  # 构建时累计 gate 违规（exporter 检查）
except Exception as _mi_ex:  # registry 损坏 → fail closed
    raise ExportError(f"model identity registry 加载失败（fail closed）: {_mi_ex}") from _mi_ex


def _model_identity_fields(provider_id: str, raw_model: str,
                           display_name: str | None = None) -> dict:
    """公开投影 + build gate（§十五：违规累计到 _mi_gate_errors）。"""
    out = _mi_projector.project(provider_id, raw_model, display_name)
    errs = _mi_projector.verify_projection(out)
    for e in errs:
        _mi_gate_errors.append(f"{provider_id}/{raw_model}: {e}")
    return out

VALID_SUMMARY_ORIGINS = {"rule", "llm", "manual", None}


def _provider_of(pm: dict, source_id: str) -> str | None:
    m = pm["sourceToProvider"].get(source_id)
    if source_id not in pm["sourceToProvider"]:
        raise ExportError(f"未知 sourceId（门禁错误）: {source_id}")
    return m


def _price_provider_of(pm: dict, pricing_provider_id: str) -> str:
    m = pm["pricingProviderIdToProvider"].get(pricing_provider_id)
    if m is None:
        raise ExportError(f"未知 pricing provider: {pricing_provider_id}")
    return m


def _price_source_id(pm: dict, source_key: str) -> str:
    m = pm["pricingSourceKeyToSourceId"].get(source_key)
    if m is None:
        raise ExportError(f"未知价格 source_key: {source_key}")
    return m


class SourceStatusIndex:
    """Task 01 来源状态：daily_changes failed 联查（滚动窗口，精度=日）。"""

    def __init__(self, daily_changes: dict, source_registry: list[dict]):
        # url → sourceId（primary_url 与 url_aliases 都算）
        self._url_to_sid: dict[str, str] = {}
        for s in source_registry:
            sid = s["source_id"]
            for u in [s.get("primary_url")] + (s.get("url_aliases") or []):
                if u:
                    self._url_to_sid[u] = sid
            # source_type + display 也可兜底定位（failed 条目没有 sourceId）
            self._url_to_sid.setdefault(f"{s.get('display_name')}|{s.get('source_type')}", sid)
        # sourceId → [(date, failed?)...] 按日期排序
        by_day: dict[str, dict[str, set]] = {}   # date → {sid_failed:set, sid_seen:set}
        for day in daily_changes.get("days", []):
            date = day.get("date")
            if not date:
                continue
            slot = by_day.setdefault(date, {"failed": set(), "seen": set()})
            for c in day.get("changed", []) or []:
                sid = self._resolve_entry(c)
                if sid:
                    slot["seen"].add(sid)
            for c in day.get("failed", []) or []:
                sid = self._resolve_entry(c)
                if sid:
                    slot["seen"].add(sid)
                    slot["failed"].add(sid)
        self._by_day = by_day

    def _resolve_entry(self, entry: dict) -> str | None:
        url = entry.get("url")
        if url and url in self._url_to_sid:
            return self._url_to_sid[url]
        key = f"{entry.get('platform')}|{entry.get('source_type')}"
        return self._url_to_sid.get(key)

    def status_of(self, source_id: str) -> dict:
        """{state, reason, lastAttemptDate, lastSuccessDate}（unknown 时时间为 null）。"""
        days = sorted(d for d, slot in self._by_day.items()
                      if source_id in slot["seen"])
        if not days:
            return {"state": "unknown", "reason": None,
                    "lastAttemptDate": None, "lastSuccessDate": None}
        last = days[-1]
        slot = self._by_day[last]
        if source_id in slot["failed"]:
            err = next((c.get("error") for c in
                        (self._by_day[last].get("entries_failed") or [])
                        if self._resolve_entry(c) == source_id), None)
            return {"state": "failing", "reason": err,
                    "lastAttemptDate": last,
                    "lastSuccessDate": _last_ok(days, self._by_day, source_id)}
        return {"state": "ok", "reason": None, "lastAttemptDate": last,
                "lastSuccessDate": last}


def _last_ok(days: list[str], by_day: dict, sid: str) -> str | None:
    for d in reversed(days):
        if sid not in by_day[d]["failed"]:
            return d
    return None


def _quality_from_state(state: dict) -> dict:
    return {"state": {"ok": "fresh", "failing": "stale",
                      "unknown": "unknown"}[state["state"]],
            "reason": state.get("reason"),
            "lastSuccessAt": state.get("lastSuccessDate")}


def project_source_change(record: dict, status_index: SourceStatusIndex,
                          pm: dict) -> dict:
    """Task 01 obs_ 记录 → 公开 change。"""
    source_id = record.get("sourceId")
    provider_id = _provider_of(pm, source_id)
    origin = record.get("summaryOrigin")
    if origin not in VALID_SUMMARY_ORIGINS:
        raise ExportError(f"非法 summaryOrigin: {record['id']}: {origin!r}")
    diff = record.get("diff") or {}
    st = status_index.status_of(source_id)
    return {
        "id": record["id"],
        "revision": record["revision"],
        "status": record["status"],
        "recordType": "source_observation",
        "providerId": provider_id,
        "sourceId": source_id,
        "sourceType": record.get("sourceType"),
        "observedAt": record.get("observedAt"),
        "observationDate": record["date"],
        "timePrecision": record.get("timePrecision") or "date",
        "publishedAt": None,
        "updatedAt": record.get("revisedAt"),
        "title": record.get("title") or "",
        "summary": record.get("summary"),
        "summaryOrigin": origin,
        "changeType": record.get("changeType"),
        "evidenceLevel": record.get("evidenceLevel"),
        "quality": _quality_from_state(st),
        "diff": {
            "addedLines": diff.get("added_lines") or [],
            "removedLines": diff.get("removed_lines") or [],
            "addedCount": diff.get("added_count") or 0,
            "removedCount": diff.get("removed_count") or 0,
            "completeness": record.get("diffCompleteness"),
        },
        "links": {
            "permalink": record["permalink"],
            "sourceUrl": record.get("sourceUrl"),
        },
        "evidenceIds": [],
    }


def project_price_change(record: dict, fact_versions: dict,
                         evidence: dict, pm: dict,
                         price_source_status: dict) -> dict:
    """Task 02 price_ 事件 → 公开 change。"""
    after_v = fact_versions.get(record.get("afterVersionId") or "")
    before_v = fact_versions.get(record.get("beforeVersionId") or "")
    if record.get("afterVersionId") and after_v is None:
        raise ExportError(f"价格事件引用悬空 afterVersionId: {record['id']}")
    if record.get("beforeVersionId") and before_v is None:
        raise ExportError(f"价格事件引用悬空 beforeVersionId: {record['id']}")
    source_key = (after_v or before_v).get("source_key")
    provider_id = _price_provider_of(pm, (after_v or before_v)["provider_id"])
    source_id = _price_source_id(pm, source_key)
    after_ev = evidence.get(record.get("afterEvidenceId") or "") or {}
    ev_ids = [e for e in (record.get("beforeEvidenceId"),
                          record.get("afterEvidenceId")) if e]
    for eid in ev_ids:
        if eid not in evidence:
            raise ExportError(f"价格事件证据引用悬空: {record['id']} → {eid}")
    # 价格源状态（Task 02）：ok→fresh，failed→stale（携带原因）
    src = price_source_status.get(source_key) or {}
    state = "fresh" if src.get("status") == "ok" else "stale"
    return {
        "id": record["id"],
        "revision": record["revision"],
        "status": record["status"],
        "recordType": "price_change",
        **_model_identity_fields(provider_id, record["model"]),
        "providerId": provider_id,
        "sourceId": source_id,
        "sourceType": "pricing",
        "observedAt": record.get("afterObservedAt"),
        "observationDate": record["date"],
        "timePrecision": "datetime" if record.get("afterObservedAt") else "date",
        "publishedAt": None,
        "updatedAt": record.get("revisedAt"),
        "title": _price_title(pm, provider_id, record),
        "summary": None,
        "summaryOrigin": None,
        "changeType": record.get("changeType"),
        "evidenceLevel": "fact_versions",
        "quality": {"state": state, "reason": src.get("reason"),
                    "lastSuccessAt": src.get("lastSuccessAt")},
        "price": {
            "factKey": record["fact_key"],
            "model": record["model"],
            "component": record["component"],
            "currency": record["currency"],
            "unitQuantity": record["unitQuantity"],
            "unitName": record["unitName"],
            "region": record["region"],
            "billingMode": record["billingMode"],
            "serviceTier": record["serviceTier"],
            "contextBand": record.get("contextBand"),
            "timeCondition": record.get("timeCondition"),
            "beforeAmount": (before_v or {}).get("amount"),
            "afterAmount": (after_v or {}).get("amount"),
            "beforeVersionId": record.get("beforeVersionId"),
            "afterVersionId": record.get("afterVersionId"),
            "changedFields": record.get("changedFields") or [],
            "comparison": record.get("comparison"),
        },
        "links": {
            "permalink": record["permalink"],
            "sourceUrl": after_ev.get("sourceUrl"),
        },
        "evidenceIds": ev_ids,
    }


_CHANGE_LABEL = {"newly_observed": "新观察", "amount_changed": "价格变化",
                 "terms_changed": "条件变化"}


def _price_title(pm: dict, provider_id: str, record: dict) -> str:
    name = next((p["displayName"] for p in pm["providers"]
                 if p["providerId"] == provider_id), provider_id)
    label = _CHANGE_LABEL.get(record.get("changeType"), record.get("changeType"))
    return f"{name} · {record['model']} {record['component']} {label}"


def project_item(change: dict, revisions: list[dict] | None) -> dict:
    """公开 change → item 详情（+修订链）。"""
    hist = [{"revision": r.get("revision"),
             "revisedAt": r.get("revisedAt"),
             "reason": r.get("revisionReason")}
            for r in (revisions or [])]
    return dict(change, revisionHistory=hist)


def project_price_fact(pfv: dict, pm: dict,
                       price_source_status: dict,
                       latest_event_by_fact: dict) -> dict:
    """current 指向的 fact version → 公开 price。"""
    source_key = pfv.get("source_key")
    provider_id = _price_provider_of(pm, pfv["provider_id"])
    source_id = _price_source_id(pm, source_key)
    src = price_source_status.get(source_key) or {}
    stale = pfv.get("field_state") == "stale" or src.get("status") != "ok"
    ev = {
        "id": pfv["version_id"],
        "factKey": pfv["fact_key"],
        "providerId": provider_id,
        "sourceId": source_id,
        "modelKey": pfv["model_key"],
        **_model_identity_fields(provider_id, pfv["model_key"]),
        "component": pfv["component"],
        "amount": pfv["amount"],
        "currency": pfv["currency"],
        "unitQuantity": pfv["unit_quantity"],
        "unitName": pfv["unit_name"],
        "region": pfv["region"],
        "billingMode": pfv["billing_mode"],
        "serviceTier": pfv["service_tier"],
        "contextBand": pfv.get("context_band"),
        "timeCondition": pfv.get("time_condition"),
        "effectiveAt": _iso(pfv.get("effective_at")),
        "observedAt": pfv.get("observedAt"),
        "evidenceId": pfv.get("evidence_id"),
        "evidenceStatus": pfv.get("evidence_status"),
        "quality": {
            "state": "stale" if stale else "fresh",
            "reason": pfv.get("stale_reason") or (src.get("reason") if stale else None),
            "lastSuccessAt": src.get("lastSuccessAt"),
        },
        "links": {
            "itemPermalink": latest_event_by_fact.get(pfv["fact_key"]),
        },
    }
    return ev


def _iso(epoch_or_none) -> str | None:
    """epoch 秒 → ISO UTC；None 透传。"""
    if epoch_or_none is None:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_or_none, tz=timezone.utc) \
        .isoformat(timespec="seconds").replace("+00:00", "Z")


def project_evidence(ev: dict, pm: dict, related_fact_ids: list[str],
                     observed_range: list[str] | None) -> dict:
    """Task 02 不可变证据 → 公开 evidence（剔除 snapshotContentId/provenance）。"""
    source_key = ev.get("source_key")
    source_id = _price_source_id(pm, source_key)
    provider_id = _provider_of(pm, source_id)
    return {
        "id": ev["id"],
        "sourceId": source_id,
        "providerId": provider_id,
        "sourceUrl": ev.get("sourceUrl"),
        "subpageUrl": ev.get("subpageUrl"),
        "observedAtRange": observed_range,
        "locatorType": ev["locatorType"],
        "locator": ev["locator"],
        "extractorVersion": ev.get("extractorVersion") or "",
        "excerptText": ev.get("excerptText") or "",
        "excerptHash": ev["excerptHash"],
        "contentHash": ev["contentHash"],
        "completeness": ev["completeness"],
        "reasons": ev.get("reasons") or [],
        "relatedFactIds": related_fact_ids,
    }


def project_weekly(entry: dict) -> dict:
    """正式周报（structured 已校验与 md 一一对应）。"""
    s = entry["structured"]
    fm = entry["frontmatter"]
    return {
        "id": entry["id"],
        "title": fm.get("title") or s.get("title") or f"MaaS 平台周度追踪报告 - {entry['id']}",
        "date": s["date"],
        "period": s.get("period"),
        "url": f"/weekly/{entry['id']}/",
        "headline": s.get("headline") or [],
        "platforms": s.get("platforms") or [],
        "summary_table": s.get("summary_table"),
        "trends": s.get("trends") or [],
        "watchpoints": s.get("watchpoints"),
        "event_index": s.get("event_index"),
    }


def project_status(li: LoadedInputs, changes: list[dict], prices: list[dict],
                   weekly: list[dict], status_index: SourceStatusIndex) -> dict:
    """三类数据流状态聚合。"""
    pm = li.provider_map
    price_streams = []
    for source_key, src in (li.current.get("sources") or {}).items():
        try:
            sid = _price_source_id(pm, source_key)
        except ExportError:
            raise
        provider_id = _price_source_id(pm, source_key)
        provider_id = pm["sourceToProvider"].get(sid)
        price_streams.append({
            "sourceKey": source_key,
            "sourceId": sid,
            "providerId": provider_id,
            "state": src.get("status") if src.get("status") in ("ok", "failing") else "unknown",
            "coverage": src.get("coverage"),
            "lastAttemptAt": _iso(src.get("latest_attempt_at")),
            "lastSuccessAt": _iso(src.get("last_success_at")),
            "reason": src.get("reason"),
        })
    source_streams = []
    for s in li.source_registry:
        sid = s["source_id"]
        st = status_index.status_of(sid)
        source_streams.append({
            "sourceId": sid,
            "providerId": _provider_of(pm, sid),
            "state": st["state"],
            "lastAttemptDate": st["lastAttemptDate"],
            "lastSuccessDate": st["lastSuccessDate"],
            "reason": st["reason"],
        })
    return {
        "providers": pm["providers"],
        "sourceStreams": source_streams,
        "priceStreams": price_streams,
        "weekly": {"count": len(weekly),
                   "latestId": weekly[-1]["id"] if weekly else None},
        "counts": {
            "changes": sum(1 for c in changes if c["status"] == "active"),
            "withdrawnChanges": sum(1 for c in changes if c["status"] == "withdrawn"),
            "prices": len(prices),
            "evidence": len(li.evidence),
            "weekly": len(weekly),
        },
    }


def build_price_source_status(current: dict) -> dict:
    """current.json sources → source_key → 状态（含 ISO 时间）。"""
    out = {}
    for source_key, src in (current.get("sources") or {}).items():
        out[source_key] = {
            "status": src.get("status"),
            "coverage": src.get("coverage"),
            "reason": src.get("reason"),
            "lastSuccessAt": _iso(src.get("last_success_at")),
        }
    return out


def build_latest_event_by_fact(price_records: list[dict]) -> dict[str, str]:
    """fact_key → 最新 active 事件 permalink（prices.links 用）。"""
    best: dict[str, tuple] = {}
    for r in price_records:
        if r.get("status") != "active":
            continue
        key = r["fact_key"]
        stamp = r.get("date") or ""
        if key not in best or stamp > best[key][0]:
            best[key] = (stamp, r["permalink"])
    return {k: v[1] for k, v in best.items()}


def build_evidence_reverse_index(fact_versions: dict) -> dict:
    """evidence_id → {fact_ids: [...], observed: [min, max] | None}。"""
    idx: dict[str, list] = defaultdict(list)
    for vid, v in fact_versions.items():
        eid = v.get("evidence_id")
        if eid:
            idx[eid].append(v)
    out = {}
    for eid, vs in idx.items():
        times = sorted(v.get("observedAt") or "" for v in vs if v.get("observedAt"))
        out[eid] = {
            "fact_ids": sorted(v["version_id"] for v in vs),
            "observed": [times[0], times[-1]] if times else None,
        }
    return out
