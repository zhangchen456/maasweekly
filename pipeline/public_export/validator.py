"""validator：公开实体的结构与引用校验（Task 03 M2）。

校验分三层（exporter 两阶段流程中全量执行）：
1. validate_entities：结构与枚举（手写校验，与 Task 01/02 风格一致；
   schemas/public-v1/*.schema.json 是对外契约，测试交叉验证两者一致）
2. validate_references：公开数据内部引用闭合（changes→evidence、
   evidence→fact、prices→evidence、item→revisionHistory）
3. validate_release_files：release 文件与 manifest 的 hash/bytes/路径
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .loaders import ExportError

CHANGE_TYPES = {"source_updated", "model_released", "model_deprecated",
                "price_changed", "amount_changed", "terms_changed",
                "newly_observed"}
EVIDENCE_LEVELS = {"source_diff", "fact_versions"}
RECORD_TYPES = {"source_observation", "price_change"}
STATUSES = {"active", "withdrawn"}
SUMMARY_ORIGINS = {"rule", "llm", "manual", None}
PRECISIONS = {"date", "datetime"}
QUALITY_STATES = {"fresh", "stale", "unknown"}
EVIDENCE_STATUSES = {"complete", "partial", "unavailable"}
COMPONENTS = {"input", "output", "cache_read", "cache_write"}
CURRENCIES = {"USD", "CNY"}

_ID_RE = re.compile(r"^(obs|price)_[0-9a-f]{64}$")
_EV_RE = re.compile(r"^ev_[0-9a-f]{64}$")
_PFV_RE = re.compile(r"^pfv_[0-9a-f]{64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def validate_entities(changes: list[dict], prices: list[dict],
                      evidence: list[dict], weekly: list[dict],
                      status: dict) -> list[str]:
    """结构 + 枚举 + 排序校验（返回错误清单，空=通过）。"""
    errors: list[str] = []
    prev_key = None
    for c in changes:
        cid = c.get("id")
        if not _ID_RE.match(cid or ""):
            _err(errors, f"change id 非法: {cid}")
            continue
        if c.get("recordType") not in RECORD_TYPES:
            _err(errors, f"recordType 非法: {cid}: {c.get('recordType')}")
        if c.get("status") not in STATUSES:
            _err(errors, f"status 非法: {cid}")
        if c.get("changeType") not in CHANGE_TYPES:
            _err(errors, f"changeType 非法: {cid}: {c.get('changeType')}")
        if c.get("evidenceLevel") not in EVIDENCE_LEVELS:
            _err(errors, f"evidenceLevel 非法: {cid}")
        if c.get("summaryOrigin") not in SUMMARY_ORIGINS:
            _err(errors, f"summaryOrigin 非法: {cid}: {c.get('summaryOrigin')}")
        if c.get("timePrecision") not in PRECISIONS:
            _err(errors, f"timePrecision 非法: {cid}")
        if not _DATE_RE.match(c.get("observationDate") or ""):
            _err(errors, f"observationDate 非法: {cid}")
        q = c.get("quality") or {}
        if q.get("state") not in QUALITY_STATES:
            _err(errors, f"quality.state 非法: {cid}")
        if c.get("recordType") == "price_change":
            p = c.get("price") or {}
            if not p.get("factKey"):
                _err(errors, f"价格事件缺 factKey: {cid}")
            for fld in ("beforeAmount", "afterAmount"):
                if p.get(fld) is not None:
                    from decimal import Decimal, InvalidOperation
                    try:
                        Decimal(p[fld])
                    except (InvalidOperation, ValueError):
                        _err(errors, f"{fld} 非 Decimal 字符串: {cid}: {p[fld]!r}")
        # 排序（日期倒序 + id 升序）：前面日期应更大或相等；同日期 id 严格递增
        key = (c.get("observationDate") or "", cid)
        if prev_key is not None:
            pd, pi = prev_key
            cd, ci = key
            if pd < cd or (pd == cd and pi >= ci):
                _err(errors, f"changes 排序错误: {pi} 先于 {ci}")
        prev_key = key
    for p in prices:
        pid = p.get("id")
        if not _PFV_RE.match(pid or ""):
            _err(errors, f"price id 非法: {pid}")
            continue
        if p.get("component") not in COMPONENTS:
            _err(errors, f"component 非法: {pid}: {p.get('component')}")
        if p.get("currency") not in CURRENCIES:
            _err(errors, f"currency 非法: {pid}: {p.get('currency')}")
        if p.get("evidenceStatus") not in EVIDENCE_STATUSES:
            _err(errors, f"evidenceStatus 非法: {pid}")
        from decimal import Decimal, InvalidOperation
        try:
            Decimal(p.get("amount") or "")
        except (InvalidOperation, ValueError):
            _err(errors, f"amount 非 Decimal 字符串: {pid}: {p.get('amount')!r}")
        if (p.get("quality") or {}).get("state") not in QUALITY_STATES:
            _err(errors, f"quality.state 非法: {pid}")
    for e in evidence:
        eid = e.get("id")
        if not _EV_RE.match(eid or ""):
            _err(errors, f"evidence id 非法: {eid}")
            continue
        if e.get("completeness") not in EVIDENCE_STATUSES:
            _err(errors, f"completeness 非法: {eid}")
        rng = e.get("observedAtRange")
        if rng is not None and (not isinstance(rng, list) or len(rng) != 2):
            _err(errors, f"observedAtRange 非法: {eid}")
    for w in weekly:
        if not _DATE_RE.match(w.get("id") or ""):
            _err(errors, f"weekly id 非法: {w.get('id')}")
    if not status.get("providers"):
        _err(errors, "status.providers 为空")
    return errors


def validate_references(changes: list[dict], prices: list[dict],
                        evidence: list[dict],
                        fact_versions: dict | None = None) -> list[str]:
    """公开数据内部引用闭合。"""
    errors: list[str] = []
    ev_ids = {e["id"] for e in evidence}
    for c in changes:
        for eid in c.get("evidenceIds") or []:
            if eid not in ev_ids:
                _err(errors, f"change 证据引用悬空: {c['id']} → {eid}")
        if c.get("links", {}).get("permalink") != f"/item/{c['id']}/":
            _err(errors, f"permalink 与 id 不符: {c['id']}")
    for p in prices:
        eid = p.get("evidenceId")
        if eid and eid not in ev_ids:
            _err(errors, f"price 证据引用悬空: {p['id']} → {eid}")
    # relatedFactIds 双向：evidence 引用的 fact 必须在公开数据可达
    reachable = {p["id"] for p in prices}
    for c in changes:
        pr = c.get("price") or {}
        for v in (pr.get("beforeVersionId"), pr.get("afterVersionId")):
            if v:
                reachable.add(v)
    for e in evidence:
        for f in e.get("relatedFactIds") or []:
            if f not in reachable:
                _err(errors, f"evidence relatedFact 不可达: {e['id']} → {f}")
    return errors


def validate_identity_catalog(catalog) -> list[str]:
    """catalog 只保存公开身份；校验结构、唯一性与正式 family 引用。"""
    if not isinstance(catalog, dict) or not all(
            isinstance(catalog.get(key), list) for key in ("models", "families")):
        return ["identity catalog 结构非法"]
    errors = []
    families, models = {}, set()
    def valid_id(value):
        return isinstance(value, str) and re.fullmatch(r"[a-z0-9-]+:[a-z0-9.-]+", value)
    def valid_name(value):
        return isinstance(value, str) and bool(value.strip())
    for family in catalog["families"]:
        if not isinstance(family, dict):
            errors.append("identity catalog family 结构非法")
            continue
        fid, name = family.get("familyId"), family.get("familyName")
        if not valid_id(fid) or not valid_name(name) or fid in families:
            errors.append("identity catalog family 非法/重复")
            continue
        families[fid] = name
    for model in catalog["models"]:
        if not isinstance(model, dict):
            errors.append("identity catalog model 结构非法")
            continue
        mid = model.get("modelId")
        if not valid_id(mid) or not valid_name(model.get("modelName")) or mid in models or mid in families:
            errors.append("identity catalog model 非法/重复")
            continue
        models.add(mid)
        if "familyId" in model or "familyName" in model:
            fid, name = model.get("familyId"), model.get("familyName")
            if (not valid_id(fid) or not valid_name(name) or fid not in families
                    or families[fid] != name or mid.split(":")[0] != fid.split(":")[0]):
                errors.append("identity catalog model 引用非正式 family")
    return errors


def validate_release_files(root: Path, manifest: dict) -> list[str]:
    """manifest 与 release 文件的 hash/bytes/路径校验（--check 与服务端共用）。"""
    errors: list[str] = []
    root = root.resolve()
    catalog_path = f"releases/{manifest.get('datasetVersion')}/model-identities.json"
    if sum(f.get("path") == catalog_path for f in manifest.get("files", [])) != 1:
        errors.append("manifest 必须包含唯一 model-identities.json")
    for f in manifest.get("files") or []:
        rel = f.get("path") or ""
        if not re.match(r"^releases/ds_[0-9a-f]{64}/[a-z]+(?:-[a-z]+)*\.json$", rel):
            _err(errors, f"manifest 路径非法: {rel}")
            continue
        p = root / rel
        # 符号链接/穿越
        cur = root
        ok = True
        for part in Path(rel).parts:
            cur = cur / part
            if cur.is_symlink() or part == "..":
                _err(errors, f"manifest 路径含符号链接/穿越: {rel}")
                ok = False
                break
        if not ok:
            continue
        if not p.exists():
            _err(errors, f"manifest 文件缺失: {rel}")
            continue
        data = p.read_bytes()
        if len(data) != f.get("bytes"):
            _err(errors, f"manifest bytes 不符: {rel} "
                         f"{len(data)} != {f.get('bytes')}")
        actual = hashlib.sha256(data).hexdigest()
        if actual != f.get("sha256"):
            _err(errors, f"manifest sha256 不符: {rel}")
        if rel == catalog_path:
            try:
                errors.extend(validate_identity_catalog(json.loads(data)))
            except (ValueError, UnicodeError):
                errors.append("identity catalog JSON 损坏")
    # manifest 自身
    if not re.match(r"^ds_[0-9a-f]{64}$", manifest.get("datasetVersion") or ""):
        _err(errors, "manifest datasetVersion 非法")
    return errors
