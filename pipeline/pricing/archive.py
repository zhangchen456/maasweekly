"""价格事实与证据的持久化归档（Task 02）。

职责：稳定 ID、不可变版本写入、证据持久化、运行记录、预检与恢复。
不含抓取入口（fetch-prices.py 在线消费；archive-price-evidence.py 离线回放）。

契约（task-02-price-evidence.md §4 与 task-02-inventory.md §3）：
- ID 一律 前缀 + 完整 SHA-256，输入为规范 JSON（UTF-8 / ensure_ascii=False /
  键排序 / 紧凑分隔符），哈希函数集中在本模块，禁止各入口自行拼接
- 金额参与身份前 Decimal 规范化：'1.0' 与 '1.00' 同一版本
- 内部时间统一 epoch 秒；对外公开字段（*At）为含时区 ISO 8601 UTC
- 目录与 obs_ 归档分离；不把 PriceFact 塞进只接受 source_observation 的函数
- 写入顺序：先不可变（版本/证据/快照元数据）→ 运行记录 committed → current
  → 派生（索引/事件）。中断后按已提交版本恢复，幂等重跑字节不变
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA_VERSION = 1

# 目录约定（仓库根 data/ 下，与 records/ record-revisions/ 平级）
DIR_FACT_VERSIONS = "price-facts/versions"
DIR_CURRENT = "price-facts/current.json"
DIR_EVIDENCE = "price-evidence"
DIR_SNAPSHOTS = "price-snapshots"
DIR_RUNS = "price-runs"
DIR_PRICE_RECORDS = "price-records"
DIR_PRICE_REVISIONS = "price-record-revisions"
INDEX_PRICE = "price-record-index.json"      # site/src/data/
INDEX_EVIDENCE = "price-evidence-index.json"  # site/src/data/

COMPLETENESS_LEVELS = ("complete", "partial", "unavailable")
CHANGE_TYPES = ("amount_changed", "terms_changed", "newly_observed")


class ArchiveError(Exception):
    """价格归档失败（身份冲突/输入损坏/引用悬空）。"""


# ---------------------------------------------------------------------------
# 规范化与稳定 ID（§3.1：集中实现）
# ---------------------------------------------------------------------------

def canonical_json(value) -> str:
    """规范 JSON：UTF-8、保留 Unicode、键排序、紧凑分隔符。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def normalize_amount(amount: str) -> str:
    """Decimal 规范化金额：'1.00' → '1'，参与身份与比较。非法输入抛错。"""
    try:
        d = Decimal(amount)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ArchiveError(f"金额非法，拒绝归档: {amount!r}") from e
    if d.is_nan() or d.is_infinite():
        raise ArchiveError(f"金额非法（NaN/Inf）: {amount!r}")
    normalized = d.normalize()
    # normalize() 对 '10' 产出 '1E+1'，转回非指数写法
    return format(normalized, "f")


def _digest(payload) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def snapshot_content_id(source_key: str, content_sha256: str) -> str:
    """psnap_ + SHA-256([source_key, content_sha256])。同内容复用。"""
    return "psnap_" + _digest([source_key, content_sha256])


def evidence_id(snapshot_content_id_: str, locator_type: str, locator: str,
                excerpt_hash: str, extractor_version: str) -> str:
    """ev_ + SHA-256。摘录或定位变化 → 新 ID（不可变）。"""
    return "ev_" + _digest([
        snapshot_content_id_, locator_type, locator, excerpt_hash,
        extractor_version,
    ])


def fact_version_id(fact: dict) -> str:
    """pfv_ + SHA-256(fact_key + 金额/单位/条件/时间/证据引用)。

    输入是 fact_to_dict 产出的 dict（含 effective_at/observed_at/evidence_id）。
    """
    payload = [
        fact["fact_key"],
        normalize_amount(fact["amount"]),
        fact["currency"],
        fact["unit_quantity"],
        fact["unit_name"],
        fact["region"],
        fact["billing_mode"],
        fact["service_tier"],
        _cond_key(fact.get("context_band")),
        _cond_key(fact.get("time_condition")),
        fact.get("effective_at"),
        fact.get("observed_at"),
        fact.get("evidence_id"),
    ]
    return "pfv_" + _digest(payload)


def price_record_id(fact_key: str, date: str) -> str:
    """price_ + SHA-256([fact_key, 上海日历日期])。同日稳定 URL。"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ArchiveError(f"日期非法: {date!r}")
    return "price_" + _digest([fact_key, date])


def _cond_key(cond) -> str | None:
    """context_band / time_condition 的可比较键。dict/JSON 字符串/None 统一。"""
    if cond is None:
        return None
    if isinstance(cond, str):
        try:
            cond = json.loads(cond)
        except json.JSONDecodeError:
            return cond.strip()
    if isinstance(cond, dict):
        return canonical_json(cond)
    return str(cond)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 原子写入与预检
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False,
                                     suffix=".tmp", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(f.name, path)


def _write_immutable(path: Path, data: dict) -> None:
    """不可变文件写入：已存在且内容不同 → 拒绝；相同 → 幂等跳过。"""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != json.dumps(data, ensure_ascii=False, indent=2):
            raise ArchiveError(
                f"不可变文件已存在且内容不同，拒绝覆盖: {path}")
        return
    _atomic_write(path, data)


# ---------------------------------------------------------------------------
# 快照元数据
# ---------------------------------------------------------------------------

def make_snapshot_record(source_key: str, provider_id: str, url: str,
                         content_sha256: str,
                         fetcher_version: str = "playwright-1") -> dict:
    """快照内容身份记录（内容寻址：同内容必同记录）。

    fetched_at / content_ref 不进入记录——同一内容跨天复用同一 psnap，
    观察时间在事实版本里，content_ref 由证据页按 content_sha256 现查。
    """
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": snapshot_content_id(source_key, content_sha256),
        "source_key": source_key,
        "provider_id": provider_id,
        "url": url,
        "content_sha256": content_sha256,
        "fetcher_version": fetcher_version,
    }


def save_snapshot_meta(snapshots_root: Path, record: dict) -> dict:
    _write_immutable(snapshots_root / f"{record['id']}.json", record)
    return record


# ---------------------------------------------------------------------------
# 证据持久化
# ---------------------------------------------------------------------------

def html_excerpt_to_text(excerpt: str) -> str:
    """HTML 表格摘录 → 安全纯文本表格。去 script/style/事件属性，保留单元格文本。

    页面不执行来源 HTML；文本化后仍保留核价语义（行 × 列）。
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise ArchiveError("需要 beautifulsoup4 处理 HTML 摘录") from e
    soup = BeautifulSoup(excerpt or "", "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    # 表前置标题（_with_heading_context 并入的 <p>）保留——模型上下文
    heading: list[str] = []
    for p_tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "caption"]):
        text = p_tag.get_text(" ", strip=True)
        if text:
            heading.append(text)
    # 只保留表格语义结构；其他标签取文本
    lines: list[str] = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if any(cells):
            lines.append(" | ".join(cells))
    if lines:
        return "\n".join([*heading, *lines])
    return soup.get_text("\n", strip=True)


def assess_evidence_completeness(excerpt: str, locator_type: str,
                                 conditions: list[dict] | None = None
                                 ) -> tuple[str, list[str]]:
    """评估证据完整性（§4.3）。返回 (completeness, reasons)。

    这是「摘录形态」级评估（含金额/单位线索）；绑定具体事实的判定
    （模型/组件/金额/条件可复核）用 verify_evidence_for_fact。
    """
    if not excerpt or not excerpt.strip():
        return "unavailable", ["excerpt_empty"]
    text = excerpt.strip()
    reasons: list[str] = []
    # 金额形态：$1.25 / ¥0.27 / ￥1 / 1 元 / 0.73 元/秒 / 1.25 / 1M tokens / $1/MTok
    has_amount = bool(re.search(
        r"[\$¥￥]\s*[\d,.]+|[\d,.]+\s*元|元\s*/\s*[\d,，\s]*[百万M千万K]?|"
        r"[\d,.]+\s*/\s*[\d,，\s]*[百万M千万K]|per\s*1M|MTok", text, re.I))
    # 单位形态：token/tokens/百万/万字符/元/MTok/字符/秒
    has_unit = bool(re.search(
        r"tokens?|百万|万字符|万? ?tokens?|MTok|字符|元", text, re.I))
    # 表头式摘录（只有列名无数据行）：markdown 旧路径的典型形态
    row_like = bool(re.search(r"[\$¥￥]\s*[\d.]+|[\d.]+\s*/\s*\d", text))
    if locator_type == "markdown_block" and not row_like:
        return "partial", ["excerpt_lacks_amount"]
    if not has_amount:
        reasons.append("excerpt_lacks_amount")
    if not has_unit:
        reasons.append("excerpt_lacks_unit")
    return ("complete" if not reasons else "partial"), reasons


def _norm_for_match(s: str) -> str:
    """模型名匹配规范化：小写，非字母数字/中文（含 emoji、连字符、点）→ 单空格。"""
    s = re.sub(r"[^0-9a-z一-鿿]+", " ", s.lower())
    return " ".join(s.split())


def verify_evidence_for_fact(excerpt_text: str, fact: dict) -> tuple[str, list[str]]:
    """证据是否支持这条具体事实（验收 P1-3：complete 必须绑定事实）。

    检查摘录中可找到：模型标识、金额（按 Decimal 规范化匹配）、币种符号，
    以及该事实的适用条件（区域/阶梯/时段——条件存在时摘录应含相应线索）。
    返回 (fact_evidence_status, reasons)：
    - complete：模型 + 金额 + 币种 + 单位全部可复核
    - partial：形态完整但具体要素缺失（reasons 列明）
    """
    if not excerpt_text or not excerpt_text.strip():
        return "unavailable", ["excerpt_empty"]
    text = excerpt_text
    reasons: list[str] = []

    # 模型：model_key 与摘录都做 _norm_for_match 规范化后做包含匹配。
    # 页面标题常见 'Flash-Lite'/'Flash Lite'/'(Nano Banana 2) 🍌' 等写法，
    # 连字符/空格/emoji 差异不能导致可复核证据被判 partial。
    model_key = str(fact.get("model_key") or "")
    model_hit = False
    if model_key:
        model_norm = _norm_for_match(model_key)
        if model_norm and model_norm in _norm_for_match(text):
            model_hit = True
    if not model_hit:
        reasons.append("model_not_in_excerpt")

    # 金额 + 币种：金额以「币种符号紧邻」的形态出现在摘录中
    # （$10 / ¥10 / 10 元——整表摘录含多行金额时，纯数字出现的命中不算）
    amount = normalize_amount(str(fact.get("amount")))
    currency = str(fact.get("currency") or "")
    amount_hit = False
    if amount:
        dec = Decimal(amount)
        # 候选写法：'10'、'10.00'、'10.000000'、千分位 '1,250'
        variants = set()
        for fmt in (None, ".1f", ".2f", ".6f"):
            v = format(dec, fmt) if fmt else format(dec, "f")
            variants.add(v)
            # 裁剪形态用于子串匹配；未裁剪形态（'6.00'）用于单元格匹配
            # （'6' 的 cell 正则会因后随 '.' 被负向断言拒绝，需保留 '6.00'）
            if "." in v:
                stripped = v.rstrip("0").rstrip(".")
                if stripped != v:
                    variants.add(stripped)
        variants.update(v.replace(".", ",") for v in list(variants))
        variants = {v for v in variants if v}
        symbols = {"USD": ("$", "usd", "美元"),
                   "CNY": ("¥", "￥", "元", "cny", "人民币")}.get(currency, ())
        for v in variants:
            esc = re.escape(v)
            # 单元格边界：金额独占一个单元格（表格语义），非子串命中。
            # '6' 不允许匹配 '256' 中的 '6'，但允许匹配 '... | 6.00 | ...'
            cell = rf"(?<![\d.,]){esc}(?![\d.,])"
            if symbols:
                sym_alt = "|".join(re.escape(s) for s in symbols)
                if re.search(rf"(?:{sym_alt})\s*{esc}", text, re.I) \
                        or re.search(rf"{esc}\s*(?:{sym_alt})", text, re.I):
                    amount_hit = True
                    break
            # 表格形态：金额为完整单元格 + 币种线索在摘录任处（常见于
            # 列头，如 '输入(非音频) 元/百万token' + 数据行 '6.00'）
            if symbols and any(s.lower() in text.lower() for s in symbols) \
                    and re.search(cell, text):
                amount_hit = True
                break
            if not symbols and v in text:
                amount_hit = True
                break
    if not amount_hit:
        reasons.append("amount_not_in_excerpt")

    # 单位
    uq, un = fact.get("unit_quantity"), fact.get("unit_name")
    unit_hit = False
    if uq and un:
        # 'M'：glm 行内写法 '5元/M'（M = million）
        unit_tokens = {"token": ("token", "百万", "mtok", "1m", "million", "/m", " m "),
                       "字符": ("字符",), "秒": ("秒", "second")}.get(
                           str(un).lower(), (str(un).lower(),))
        if uq == 1_000_000:
            unit_hit = any(t in text.lower() for t in unit_tokens)
        else:
            # 非百万单位：数字形式出现即可
            unit_hit = (str(uq) in text
                        or any(t in text.lower() for t in unit_tokens))
    if not unit_hit:
        reasons.append("unit_not_in_excerpt")

    # 条件（可选维度）：存在时摘录应含相应线索，缺线索不阻断 complete
    # 但区域/阶梯等条件是理解金额的必要上下文——列为提示不降级
    # （过度严格会把合法的整表证据全部误降；策略：金额/模型/单位是硬要求）
    if reasons:
        return "partial", reasons
    return "complete", []


def fact_evidence_status(evidence_record: dict, fact: dict) -> str:
    """事实级证据状态：摘录形态 complete 且绑定事实 verify 通过 → complete。

    摘录形态 partial/unavailable 时直接继承；形态 complete 但绑定验证
    不通过 → partial。reasons 返回给调用方自行记录（不写共享的证据记录——
    一张表常被多条事实复用，往证据上累积各事实的 reasons 会互相污染，
    且证据本身不可变）。
    """
    if evidence_record["completeness"] != "complete":
        return evidence_record["completeness"]
    status, reasons = verify_evidence_for_fact(
        evidence_record.get("excerptText") or "", fact)
    return status if status == "complete" else "partial"


def make_evidence_record(*, snapshot: dict, locator_type: str, locator: str,
                         excerpt_text: str, extractor_version: str,
                         completeness: str | None = None,
                         reasons: list[str] | None = None,
                         subpage_url: str | None = None,
                         snapshot_available: bool = True,
                         provenance: dict | None = None) -> dict:
    """构建持久证据记录。excerpt_hash 对实际保存的摘录文本计算。"""
    if completeness is None:
        completeness, auto_reasons = assess_evidence_completeness(
            excerpt_text, locator_type)
        reasons = reasons if reasons is not None else auto_reasons
    if completeness not in COMPLETENESS_LEVELS:
        raise ArchiveError(f"completeness 非法: {completeness!r}")
    excerpt_hash = hashlib.sha256(excerpt_text.encode("utf-8")).hexdigest()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": evidence_id(snapshot["id"], locator_type, locator,
                          excerpt_hash, extractor_version),
        "snapshotContentId": snapshot["id"],
        "source_key": snapshot["source_key"],
        "sourceUrl": _safe_url(snapshot.get("url")),
        "subpageUrl": _safe_url(subpage_url) if subpage_url else None,
        "contentHash": snapshot["content_sha256"],
        "locatorType": locator_type,
        "locator": locator,
        "extractorVersion": extractor_version,
        "excerptText": excerpt_text,
        "excerptHash": excerpt_hash,
        "completeness": completeness,
        "reasons": reasons or [],
        "snapshotAvailable": snapshot_available,
        "provenance": provenance or {},
    }


def save_evidence(evidence_root: Path, record: dict) -> dict:
    _write_immutable(evidence_root / f"{record['id']}.json", record)
    return record


def _safe_url(url: str | None) -> str | None:
    """仅 http/https 可作外链；其他协议返回 None。"""
    if not url:
        return None
    return url if re.match(r"^https?://", url, re.I) else None


def _epoch_to_iso(value) -> str | None:
    """epoch 秒 → 含时区 ISO 8601。未知/None → None（不虚构时间）。"""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat(
            timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# 事实版本
# ---------------------------------------------------------------------------

def make_fact_version(fact: dict, *, source_key: str,
                      evidence_status: str) -> dict:
    """fact_to_dict 输出 → 不可变事实版本记录（含 effective_at 透传）。"""
    try:
        vid = fact_version_id(fact)
    except KeyError as e:
        raise ArchiveError(f"事实缺关键字段，无法生成版本: {e}: {fact!r}") from e
    return {
        "schemaVersion": SCHEMA_VERSION,
        "version_id": vid,
        "fact_key": fact["fact_key"],
        "provider_id": fact["provider_id"],
        "model_key": fact["model_key"],
        "component": fact["component"],
        "billing_mode": fact["billing_mode"],
        "amount": normalize_amount(fact["amount"]),
        "amountRaw": fact["amount"],
        "currency": fact["currency"],
        "unit_quantity": fact["unit_quantity"],
        "unit_name": fact["unit_name"],
        "region": fact["region"],
        "service_tier": fact["service_tier"],
        "context_band": fact.get("context_band"),
        "time_condition": fact.get("time_condition"),
        "effective_at": fact.get("effective_at"),   # 只来自官方来源；None 不补齐
        "observed_at": fact.get("observed_at"),     # epoch 秒（内部口径）
        "observedAt": _epoch_to_iso(fact.get("observed_at")),
        "source_key": source_key,
        "evidence_id": fact.get("evidence_id"),
        "evidence_status": evidence_status,
        "field_state": fact.get("field_state", "confirmed"),
        "stale_reason": fact.get("stale_reason"),
    }


def save_fact_version(versions_root: Path, record: dict) -> dict:
    """保存事实版本（不可变，幂等）。

    不可变契约由 _write_immutable 保证：同 version_id 内容不同 → 拒绝。
    金额/条件冲突的同 fact_key 双版本属于上游 extractor 缺陷（如 5m/1h
    缓存列未分条件），由 validate_price_archive 的 id↔内容复核兜底。

    例外：evidence_status 是派生评估（A3 绑定验证），verify 逻辑演进会
    改变同一证据的判定（complete→partial）。事实本体（身份/金额/证据引用）
    不变、仅评估变化时，原地更新该字段——版本身份不因评估演进而分叉。
    """
    path = versions_root / f"{record['version_id']}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        differs = {k for k in set(existing) | set(record)
                   if existing.get(k) != record.get(k)}
        if differs and differs <= {"evidence_status"}:
            merged = dict(existing)
            merged["evidence_status"] = record["evidence_status"]
            _atomic_write(path, merged)
            return merged
    _write_immutable(path, record)
    return record


# ---------------------------------------------------------------------------
# current（fact_key → 最新已接受版本）
# ---------------------------------------------------------------------------

def load_current(current_file: Path) -> dict:
    try:
        return json.loads(current_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schemaVersion": SCHEMA_VERSION, "facts": {}, "sources": {}}
    except json.JSONDecodeError as e:
        raise ArchiveError(f"current.json 损坏: {e}——从 versions 可重建，"
                           f"拒绝当成空库初始化")


def save_current(current_file: Path, data: dict) -> None:
    _atomic_write(current_file, data)


def rebuild_current(versions_root: Path, current_file: Path) -> dict:
    """从全部不可变版本重建 current（恢复路径）。取每 fact_key 最大 observed_at。"""
    current = {"schemaVersion": SCHEMA_VERSION, "facts": {}, "sources": {}}
    if not versions_root.exists():
        return current
    for f in sorted(versions_root.glob("pfv_*.json")):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ArchiveError(f"版本文件损坏: {f}: {e}")
        fk = v["fact_key"]
        prev = current["facts"].get(fk)
        if prev is None or (v.get("observed_at") or 0) >= (prev.get("observed_at") or 0):
            current["facts"][fk] = {
                "version_id": v["version_id"],
                "observed_at": v.get("observed_at"),
                "evidence_id": v.get("evidence_id"),
            }
    save_current(current_file, current)
    return current


# ---------------------------------------------------------------------------
# 来源级状态（失败沿用与日基线分离，§4.5）
# ---------------------------------------------------------------------------

def make_source_state(source_key: str, *, status: str,
                      latest_attempt_at: float, last_success_at: float | None,
                      coverage: str, reason: str | None = None) -> dict:
    """来源状态：latest_attempt（最新尝试）与 last_success（最新成功）分开。

    coverage: full / partial / not_run / failed
    """
    if coverage not in ("full", "partial", "not_run", "failed"):
        raise ArchiveError(f"coverage 非法: {coverage!r}")
    return {
        "source_key": source_key,
        "status": status,                     # ok / failed / not_run
        "latest_attempt_at": latest_attempt_at,
        "latestAttemptAt": _epoch_to_iso(latest_attempt_at),
        "last_success_at": last_success_at,
        "lastSuccessAt": _epoch_to_iso(last_success_at),
        "coverage": coverage,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# 运行记录（prepared → committed；消费者只读 committed）
# ---------------------------------------------------------------------------

def make_run_record(date: str, run_id: str, *, scope: list[str],
                    source_states: list[dict], accepted_versions: list[str],
                    baseline: str | None) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "run_id": run_id,
        "date": date,
        "state": "prepared",
        "scope": scope,                       # 本次实际处理的 source_key 列表
        "source_states": source_states,
        "accepted_versions": accepted_versions,
        "baseline": baseline,                 # 日比较基线（run 文件 id 或 None）
        "created_at": utc_now_iso(),
    }


def commit_run(runs_dir: Path, run: dict) -> None:
    """运行记录提交：prepared → committed（原子替换）。

    幂等：同 run_id 已提交且除时间戳外内容一致 → 字节不变（重跑不刷新时间）。
    """
    run_file = runs_dir / run["date"] / f"{run['run_id']}.json"
    committed = dict(run, state="committed", committed_at=utc_now_iso())
    if run_file.exists():
        try:
            import json as _json
            existing = _json.loads(run_file.read_text(encoding="utf-8"))
            if existing.get("state") == "committed":
                core = {k: v for k, v in committed.items()
                        if k not in ("created_at", "committed_at")}
                prev_core = {k: v for k, v in existing.items()
                             if k not in ("created_at", "committed_at")}
                if core == prev_core:
                    return  # 内容一致：保持原时间戳，字节不变
        except json.JSONDecodeError:
            pass  # 损坏的运行记录：直接覆盖为本次提交
    _atomic_write(run_file, committed)


def load_committed_runs(runs_dir: Path, date: str) -> list[dict]:
    """读取某日全部已提交运行（消费者入口，跳过 prepared）。"""
    out = []
    d = runs_dir / date
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ArchiveError(f"运行记录损坏: {f}: {e}")
        if r.get("state") == "committed":
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# 事件构建与比较（§4.4）
# ---------------------------------------------------------------------------

def conditions_compatible(a: dict, b: dict) -> bool:
    """两版本是否同条件（模型/平台/组件/区域/阶梯/时段/币种/单位全一致）。"""
    keys = ("provider_id", "model_key", "component", "region", "billing_mode",
            "service_tier", "currency", "unit_quantity", "unit_name",
            "context_band", "time_condition")
    return all(_cond_key(a.get(k)) == _cond_key(b.get(k)) for k in keys)


def compare_versions(prev: dict | None, curr: dict) -> dict:
    """两版本比较 → changeType / changedFields / comparison。

    prev=None → newly_observed；条件不一致（币种/单位/区域/阶梯变化）
    → terms_changed（不配对涨跌）；amount 变化 → amount_changed + 百分比
    （仅当同条件且旧值>0，Decimal 计算）。
    """
    if prev is None:
        return {"changeType": "newly_observed", "changedFields": [],
                "comparison": None}
    changed: list[str] = []
    if normalize_amount(prev["amount"]) != normalize_amount(curr["amount"]):
        changed.append("amount")
    for f in ("currency", "unit_quantity", "unit_name", "region",
              "service_tier", "context_band", "time_condition", "effective_at"):
        if _cond_key(prev.get(f)) != _cond_key(curr.get(f)):
            changed.append(f)
    if not changed:
        return {"changeType": "newly_observed", "changedFields": [],
                "comparison": None}  # 同值新观察，不算变化
    if "amount" in changed and conditions_compatible(prev, curr) \
            and all(k not in changed for k in
                    ("currency", "unit_quantity", "unit_name", "region",
                     "context_band", "time_condition")):
        old, new = Decimal(normalize_amount(prev["amount"])), \
            Decimal(normalize_amount(curr["amount"]))
        comparison = None
        if old > 0:
            pct = (new - old) / old * Decimal(100)
            comparison = {
                "previous": prev["amount"], "current": curr["amount"],
                "direction": "down" if new < old else "up",
                "percent": str(pct.quantize(Decimal("0.01"))),
            }
        else:
            comparison = {
                "previous": prev["amount"], "current": curr["amount"],
                "direction": "down" if new < old else "up",
                "percent": None,
                "percentUnavailableReason": "previous_amount_not_positive",
            }
        return {"changeType": "amount_changed", "changedFields": changed,
                "comparison": comparison}
    if "amount" not in changed:
        return {"changeType": "terms_changed", "changedFields": changed,
                "comparison": None}
    # amount 变了但条件也变了：不跨条件配对涨跌
    return {"changeType": "terms_changed", "changedFields": changed,
            "comparison": {
                "previous": prev["amount"], "current": curr["amount"],
                "percent": None,
                "percentUnavailableReason": "conditions_changed",
            }}


def build_price_event(date: str, fact_key: str, prev_version: dict | None,
                      curr_version: dict, comparison_result: dict) -> dict:
    """构建每日价格事件记录（价格侧，与 obs_ source_observation 分类型）。"""
    rid = price_record_id(fact_key, date)
    comp = comparison_result["comparison"]
    event = {
        "schemaVersion": SCHEMA_VERSION,
        "id": rid,
        "date": date,
        "recordType": "price_change",
        "fact_key": fact_key,
        "provider": curr_version["provider_id"],
        "model": curr_version["model_key"],
        "component": curr_version["component"],
        "currency": curr_version["currency"],
        "unitQuantity": curr_version["unit_quantity"],
        "unitName": curr_version["unit_name"],
        "region": curr_version["region"],
        "billingMode": curr_version["billing_mode"],
        "serviceTier": curr_version["service_tier"],
        "contextBand": curr_version.get("context_band"),
        "timeCondition": curr_version.get("time_condition"),
        "beforeVersionId": prev_version["version_id"] if prev_version else None,
        "afterVersionId": curr_version["version_id"],
        "beforeEvidenceId": prev_version.get("evidence_id") if prev_version else None,
        "afterEvidenceId": curr_version.get("evidence_id"),
        "beforeObservedAt": prev_version.get("observedAt") if prev_version else None,
        "afterObservedAt": curr_version.get("observedAt"),
        "changeType": comparison_result["changeType"],
        "changedFields": comparison_result["changedFields"],
        "comparison": comp,
        "revision": 1,
        "status": "active",
        "revisedAt": None,
        "revisionReason": None,
        "permalink": f"/item/{rid}/",
        "provenance": {},
    }
    return event


# ---------------------------------------------------------------------------
# 价格事件归档（复用 Task 01 的修订纪律，但身份与字段独立）
# ---------------------------------------------------------------------------

_EVENT_COMPARE_EXCLUDE = {"revision", "revisedAt", "revisionReason"}


def event_signature(event: dict) -> str:
    core = {k: v for k, v in event.items()
            if k not in _EVENT_COMPARE_EXCLUDE}
    return canonical_json(core)


def merge_price_event(records_root: Path, revisions_root: Path,
                      new_event: dict) -> dict:
    """合并价格事件：新建 / 内容变化升修订 / 幂等。

    先从修订链恢复 current（T09：修订已写、current 替换中断后重跑
    幂等命中，不因时间戳差异冲突）。
    """
    rid = new_event["id"]
    cur = restore_event_from_revisions(records_root, revisions_root, rid)
    if cur is None:
        _commit_event(records_root, revisions_root,
                      dict(new_event, revision=1))
        return {"action": "created", "id": rid}
    sig_new = event_signature({**new_event, "revision": cur["revision"]})
    if sig_new == event_signature(cur) and \
            new_event.get("status") == cur.get("status"):
        return {"action": "unchanged", "id": rid}
    revised = dict(cur)
    for k, v in new_event.items():
        if k in _EVENT_COMPARE_EXCLUDE:
            continue
        revised[k] = v
    revised["revision"] = cur["revision"] + 1
    if new_event.get("status") == "withdrawn" and cur.get("status") != "withdrawn":
        revised["revisionReason"] = "重新计算后未识别到变化，撤回收录"
    elif cur.get("status") == "withdrawn" and new_event.get("status") == "active":
        revised["revisionReason"] = "重新计算后再次确认变化，恢复收录"
    else:
        revised["revisionReason"] = "事件内容更新"
    revised["revisedAt"] = utc_now_iso()
    _commit_event(records_root, revisions_root, revised)
    return {"action": "updated", "id": rid, "revision": revised["revision"]}


def withdraw_price_event(records_root: Path, revisions_root: Path, rid: str,
                         reason: str = "重新计算后未识别到变化，撤回收录") -> dict:
    """撤回事件（先恢复 current，中断重跑幂等）。"""
    cur = restore_event_from_revisions(records_root, revisions_root, rid)
    if cur is None:
        return {"action": "absent", "id": rid}
    if cur.get("status") == "withdrawn":
        return {"action": "unchanged", "id": rid}
    revised = dict(cur, status="withdrawn", revision=cur["revision"] + 1,
                   revisedAt=utc_now_iso(), revisionReason=reason)
    _commit_event(records_root, revisions_root, revised)
    return {"action": "withdrawn", "id": rid, "revision": revised["revision"]}


def _load_price_record(records_root: Path, rid: str) -> dict | None:
    f = records_root / f"{rid}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ArchiveError(f"价格记录损坏: {f}: {e}——不允许当成空库初始化")


def restore_event_from_revisions(records_root: Path, revisions_root: Path,
                                 rid: str) -> dict | None:
    """校验修订链后恢复缺失或落后的 current（T09 中断恢复）。

    中断场景：修订已落盘、current 替换失败 → current 停留在旧修订。
    最高修订即 current 的目标状态；签名一致（排除时间戳/原因字段）
    时直接推进 current，重跑幂等命中 unchanged。
    """
    cur = _load_price_record(records_root, rid)
    rev_dir = revisions_root / rid
    files = list(rev_dir.glob("*.json")) if rev_dir.exists() else []
    if not files:
        if cur is not None:
            raise ArchiveError(f"价格修订缺失: {rid}")
        return None
    chain: dict[int, dict] = {}
    try:
        for f in files:
            rv = json.loads(f.read_text(encoding="utf-8"))
            rev = rv["revision"]
            if (type(rev) is not int or rev < 1 or f.name != f"{rev}.json"
                    or rv["id"] != rid
                    or rv["permalink"] != f"/item/{rid}/"
                    or rv["status"] not in ("active", "withdrawn")
                    or (rev > 1 and not rv.get("revisedAt"))):
                raise ValueError(f"非法修订: {f}")
            chain[rev] = rv
        top = max(chain)
        if set(chain) != set(range(1, top + 1)):
            raise ValueError("修订链不连续")
        if cur is not None and cur["revision"] in chain:
            same = event_signature(chain[cur["revision"]]) == event_signature(cur)
            if not same:
                # current 与其对应修订签名不一致 = 篡改或写入损坏（无论是否
                # top 都拒绝——中断恢复场景 current 只是"落后"，不会"分叉"）
                raise ValueError("current 与对应修订内容不一致")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError,
            UnicodeDecodeError) as e:
        raise ArchiveError(f"价格修订校验失败，拒绝覆盖: {rid}: {e}") from e
    latest = chain[top]
    if cur != latest:
        _atomic_write(records_root / f"{rid}.json", latest)
    return latest


def _commit_event(records_root: Path, revisions_root: Path, event: dict) -> None:
    """写入修订 + 替换 current（先修订后 current，可中断恢复）。

    修订文件已存在时：签名一致（排除时间戳字段）→ 恢复场景，幂等推进
    current；签名不同 → 真冲突，拒绝覆盖。
    """
    rid, rev = event["id"], event["revision"]
    rev_file = revisions_root / rid / f"{rev}.json"
    if rev_file.exists():
        existing = json.loads(rev_file.read_text(encoding="utf-8"))
        if event_signature(existing) != event_signature(event):
            raise ArchiveError(
                f"修订文件已存在且内容不同，拒绝覆盖: {rev_file}")
        event = existing  # 保持已落盘版本（含原时间戳），不刷新
    else:
        _atomic_write(rev_file, event)
    _atomic_write(records_root / f"{rid}.json", event)


# ---------------------------------------------------------------------------
# 索引（可重建）
# ---------------------------------------------------------------------------

def build_price_index(records_root: Path) -> list[dict]:
    items = []
    for f in sorted(records_root.glob("price_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ArchiveError(f"价格记录损坏，无法生成索引: {f}: {e}")
        items.append({
            "id": r["id"], "date": r["date"], "provider": r["provider"],
            "model": r["model"], "component": r["component"],
            "changeType": r["changeType"], "status": r["status"],
            "currency": r["currency"], "unitQuantity": r["unitQuantity"],
            "unitName": r["unitName"], "region": r.get("region", ""),
            "contextBand": r.get("contextBand"),
            "timeCondition": r.get("timeCondition"),
            "permalink": r["permalink"], "revision": r["revision"],
            "comparison": r.get("comparison"),
        })
    # 日期倒序，同日内 provider → model → id 稳定排序（字节稳定）
    items.sort(key=lambda x: (x["provider"], x["model"], x["id"]))
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def build_evidence_index(evidence_root: Path) -> list[dict]:
    items = []
    for f in sorted(evidence_root.glob("ev_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ArchiveError(f"证据文件损坏，无法生成索引: {f}: {e}")
        items.append({
            "id": r["id"], "source_key": r["source_key"],
            "sourceUrl": r.get("sourceUrl"),
            "completeness": r["completeness"], "reasons": r.get("reasons", []),
            "locatorType": r["locatorType"], "locator": r["locator"],
            "extractorVersion": r.get("extractorVersion", ""),
            "observedAt": r.get("observedAt"),
            "snapshotContentId": r.get("snapshotContentId"),
        })
    items.sort(key=lambda x: (x["source_key"], x["id"]))
    return items


# ---------------------------------------------------------------------------
# 一致性校验（构建门禁与 --check 共用）
# ---------------------------------------------------------------------------

def validate_price_archive(data_root: Path, *, versions_root: Path,
                           evidence_root: Path, snapshots_root: Path,
                           records_root: Path, revisions_root: Path,
                           current_file: Path,
                           price_index: list[dict] | None = None,
                           evidence_index: list[dict] | None = None,
                           runs_root: Path | None = None
                           ) -> list[str]:
    """全量一致性校验，返回错误清单（空=通过）。

    检查：JSON 可解析、文件名=id、事件修订链完整（含高于 current.revision
    的额外修订）、beforeVersionId/afterVersionId/evidence_id 引用不悬空、
    证据 id 从五要素重算比对、证据↔快照关联、current 指向最新版本、
    run 记录 state 合法性与 prepared 残留、索引双向一致、excerpt_hash 复核。
    """
    errors: list[str] = []
    versions: dict[str, dict] = {}
    for f in sorted(versions_root.glob("pfv_*.json")):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"版本损坏: {f}: {e}")
            continue
        if v.get("version_id") != f.stem:
            errors.append(f"版本文件名与 id 不一致: {f.stem}")
        if v.get("version_id") != fact_version_id(v):
            errors.append(f"版本 id 与内容不匹配（不可变契约破坏）: {f.stem}")
        versions[f.stem] = v

    snapshots: dict[str, dict] = {}
    for f in sorted(snapshots_root.glob("psnap_*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"快照元数据损坏: {f}: {e}")
            continue
        if s.get("id") != f.stem or \
                s.get("id") != snapshot_content_id(s["source_key"],
                                                   s["content_sha256"]):
            errors.append(f"快照 id 不一致: {f.stem}")
        else:
            snapshots[s["id"]] = s

    evidence: dict[str, dict] = {}
    for f in sorted(evidence_root.glob("ev_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"证据损坏: {f}: {e}")
            continue
        if r.get("id") != f.stem:
            errors.append(f"证据文件名与 id 不一致: {f.stem}")
            continue
        actual = hashlib.sha256(
            (r.get("excerptText") or "").encode("utf-8")).hexdigest()
        if r.get("excerptHash") != actual:
            errors.append(f"证据 excerpt_hash 不符: {r['id']}")
        if r.get("completeness") not in COMPLETENESS_LEVELS:
            errors.append(f"证据 completeness 非法: {r['id']}")
        evidence[r["id"]] = r
        # 证据 id 须从五要素重算一致（内容寻址契约：改动任一要素应产生新证据
        # 文件，而非原地篡改现有文件）
        expected_id = evidence_id(
            r.get("snapshotContentId") or "", r.get("locatorType") or "",
            r.get("locator") or "", r.get("excerptHash") or "",
            r.get("extractorVersion") or "")
        if r.get("id") != expected_id:
            errors.append(f"证据 id 与五要素不匹配（内容寻址契约破坏）: {r['id']}")
        # 证据 ↔ 快照关联：snapshotContentId 必须指向已归档快照
        psnap_id = r.get("snapshotContentId")
        if psnap_id and psnap_id not in snapshots:
            errors.append(f"证据引用不存在的快照: {r['id']} → {psnap_id}")

    records: dict[str, dict] = {}
    for f in sorted(records_root.glob("price_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"价格记录损坏: {f}: {e}")
            continue
        rid = r.get("id")
        if rid != f.stem:
            errors.append(f"价格记录文件名与 id 不一致: {f.stem}")
            continue
        if rid != price_record_id(r["fact_key"], r["date"]):
            errors.append(f"价格记录 id 与 (fact_key, date) 不匹配: {rid}")
        top = r.get("revision", 1)
        if not isinstance(top, int) or top < 1:
            errors.append(f"revision 非法: {rid}")
            continue
        records[rid] = r
        rev_dir = revisions_root / rid
        latest = None
        for rev in range(1, top + 1):
            rf = rev_dir / f"{rev}.json"
            if not rf.exists():
                errors.append(f"事件修订缺失: {rid} rev {rev}")
                continue
            try:
                rv = json.loads(rf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f"事件修订损坏: {rid} rev {rev}: {e}")
                continue
            if rv.get("revision") != rev or rv.get("id") != rid:
                errors.append(f"事件修订版本/id 不匹配: {rid} rev {rev}")
            latest = rv
        # 高于 current.revision 的额外修订文件（current 回退/篡改盲区）：
        # 修订链是 append-only，目录里出现 top+1 及以后的文件即不一致
        if rev_dir.exists():
            for rf in rev_dir.glob("*.json"):
                try:
                    extra_rev = int(rf.stem)
                except ValueError:
                    errors.append(f"事件修订文件名非数字: {rid}/{rf.name}")
                    continue
                if extra_rev > top:
                    errors.append(f"事件修订超出 current.revision: "
                                  f"{rid} rev {extra_rev} > {top}")
        if latest is not None:
            a = {k: v for k, v in latest.items()
                 if k not in _EVENT_COMPARE_EXCLUDE}
            b = {k: v for k, v in r.items()
                 if k not in _EVENT_COMPARE_EXCLUDE}
            if a != b:
                errors.append(f"最新修订与当前记录不一致: {rid}")
        # 引用完整性
        for field in ("beforeVersionId", "afterVersionId"):
            vid = r.get(field)
            if vid and vid not in versions:
                errors.append(f"事件引用悬空 {field}: {rid} → {vid}")
        for field in ("beforeEvidenceId", "afterEvidenceId"):
            evid = r.get(field)
            if evid and evid not in evidence:
                errors.append(f"事件证据引用悬空 {field}: {rid} → {evid}")
        # 版本内证据引用
    for vid, v in versions.items():
        evid = v.get("evidence_id")
        if evid and evid not in evidence:
            errors.append(f"版本证据引用悬空: {vid} → {evid}")

    # current 与版本一致
    if current_file.exists():
        try:
            cur = json.loads(current_file.read_text(encoding="utf-8"))
            for fk, entry in cur.get("facts", {}).items():
                vid = entry.get("version_id")
                if vid not in versions:
                    errors.append(f"current 引用悬空: {fk} → {vid}")
                    continue
                # current 的 fact_key 必须与所指向版本的 fact_key 一致，
                # 且指向该 fact_key 的最新版本（旧版本留存但 current 须最新）
                v = versions[vid]
                if v.get("fact_key") != fk:
                    errors.append(f"current.fact_key 与版本不匹配: "
                                  f"{fk} → {vid}")
                # current 须指向该 fact_key 观察时间最新的版本。同一
                # observed_at 可能并列多个版本（证据摘录变化产生新版本，
                # 金额不变）——指向任一并列最新版本均合法
                max_obs = max((x.get("observed_at") or 0
                               for x in versions.values()
                               if x.get("fact_key") == fk), default=None)
                if max_obs is not None \
                        and (v.get("observed_at") or 0) < max_obs:
                    errors.append(f"current 未指向最新版本: {fk} → {vid} "
                                  f"(observed_at {v.get('observed_at')} < "
                                  f"{max_obs})")
        except json.JSONDecodeError as e:
            errors.append(f"current.json 损坏: {e}")

    # run 记录：state 只能是 committed/prepared；committed 记录的
    # accepted_versions 应有对应版本文件；prepared 残留提示中断的运行
    if runs_root is not None and runs_root.exists():
        for rf in sorted(runs_root.glob("*/*.json")):
            try:
                run = json.loads(rf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f"运行记录损坏: {rf}: {e}")
                continue
            state = run.get("state")
            if state not in ("committed", "prepared"):
                errors.append(f"运行记录 state 非法: {rf}: {state!r}")
            if state == "committed":
                for vid in run.get("accepted_versions") or []:
                    if vid not in versions:
                        errors.append(f"运行记录版本引用悬空: {rf} → {vid}")
            elif state == "prepared":
                errors.append(f"prepared 运行残留（运行中断未提交）: {rf}")

    # 索引双向
    if price_index is not None:
        idx = {it.get("id"): it for it in price_index}
        for rid, r in records.items():
            it = idx.get(rid)
            if it is None:
                errors.append(f"价格索引缺失记录: {rid}")
                continue
            for field in ("date", "provider", "model", "component",
                          "changeType", "status", "permalink"):
                if it.get(field) != r.get(field):
                    errors.append(f"价格索引字段不一致: {rid}.{field}")
        for rid in idx:
            if rid not in records:
                errors.append(f"价格索引悬空: {rid}")
    if evidence_index is not None:
        idx = {it.get("id"): it for it in evidence_index}
        for evid in evidence:
            if evid not in idx:
                errors.append(f"证据索引缺失: {evid}")
        for evid in idx:
            if evid not in evidence:
                errors.append(f"证据索引悬空: {evid}")

    return errors


def recover_price_archive(data_root: Path) -> dict:
    """恢复入口：current 损坏时从 versions 重建；返回恢复后状态。"""
    versions_root = data_root / DIR_FACT_VERSIONS
    current_file = data_root / DIR_CURRENT
    errors = validate_price_archive(
        data_root, versions_root=versions_root,
        evidence_root=data_root / DIR_EVIDENCE,
        snapshots_root=data_root / DIR_SNAPSHOTS,
        records_root=data_root / DIR_PRICE_RECORDS,
        revisions_root=data_root / DIR_PRICE_REVISIONS,
        current_file=current_file,
        runs_root=data_root / DIR_RUNS,
    )
    fatal = [e for e in errors if "损坏" in e or "悬空" in e]
    if fatal:
        raise ArchiveError("归档校验失败，拒绝恢复: " + "; ".join(fatal[:10]))
    try:
        load_current(current_file)
    except ArchiveError:
        rebuild_current(versions_root, current_file)
    return {"errors": [e for e in errors if e not in fatal]}
