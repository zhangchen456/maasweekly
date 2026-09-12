#!/usr/bin/env python3
"""record_archive.py：来源变化条目归档的纯逻辑模块（Task 01）。

职责：source 映射、稳定 ID、输入校验、归档写入、修订比较、撤回/恢复、索引生成。
不含 IO 入口（入口见 archive-source-changes.py / sync-diff-to-site.py 调用）。

数据规则（与 task-01-stable-records.md 4.x 一致）：
- source_id 由 registry 固定分配；未映射/歧义 → 显式报错，不静默分配
- 条目粒度 = (source_id, 上海日历日期)；ID = obs_ + SHA-256(规范 JSON [source_id, date])
- 当前版本 data/records/<id>.json；历史版本 data/record-revisions/<id>/<rev>.json 不可覆盖
- 幂等：相同公开内容重复归档，文件字节与 revision 不变
- unchanged 明确出现且已有条目 → withdrawn；输入缺失/抓取失败不撤回
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = 1
RECORDS_DIR = "records"
REVISIONS_DIR = "record-revisions"
INDEX_FILE = "record-index.json"


class ArchiveError(Exception):
    """归档失败（未映射来源/身份冲突/输入损坏）。"""


# ---------------------------------------------------------------------------
# registry 与 source_id
# ---------------------------------------------------------------------------

def load_registry(path: Path) -> dict:
    """加载 registry，返回 {source_id: {...}} 与别名索引。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ArchiveError(f"source registry 不存在: {path}")
    except json.JSONDecodeError as e:
        raise ArchiveError(f"source registry 损坏: {e}")
    sources = {}
    for s in data.get("sources", []):
        sid = s.get("source_id")
        if not sid or sid in sources:
            raise ArchiveError(f"registry 内 source_id 缺失或重复: {sid}")
        sources[sid] = s
    return sources


def resolve_source_id(registry: dict, platform: str, source_type: str,
                      url: str | None) -> str:
    """(platform, source_type[, url]) → source_id。

    匹配顺序：平台名+类型完全匹配；URL 命中别名时确认平台类型一致。
    未映射或有歧义 → ArchiveError（含待补配置提示）。
    """
    candidates = []
    for sid, s in registry.items():
        if s.get("display_name") == platform and s.get("source_type") == source_type:
            candidates.append(sid)
    if len(candidates) > 1 and url:
        # 同平台同类型多来源时用 URL 别名消歧
        url_matched = [sid for sid in candidates
                       if url in (registry[sid].get("url_aliases") or [])]
        if len(url_matched) == 1:
            return url_matched[0]
        if len(url_matched) > 1:
            raise ArchiveError(
                f"来源映射歧义: {platform}|{source_type}|{url} 命中多个 "
                f"source_id: {url_matched}")
    if len(candidates) == 1:
        sid = candidates[0]
        # URL 变化只做告警（别名机制处理），不改身份
        if url and url not in (registry[sid].get("url_aliases") or []):
            # 新 URL：归档仍用原 source_id（身份不随 URL 变化），
            # 由维护者按需把新 URL 加入 registry 的 url_aliases
            pass
        return sid
    if len(candidates) == 0:
        raise ArchiveError(
            f"来源未映射: platform={platform!r} source_type={source_type!r} "
            f"url={url!r}——请在 pipeline/config/source_registry.json 补充条目")
    raise ArchiveError(
        f"来源映射歧义: {platform}|{source_type} 命中多个 source_id: {candidates}")


# ---------------------------------------------------------------------------
# 稳定 ID
# ---------------------------------------------------------------------------

def make_record_id(source_id: str, date: str) -> str:
    """obs_ + SHA-256(紧凑 JSON [source_id, date])。不掺其他任何输入。"""
    canonical = json.dumps([source_id, date], ensure_ascii=False,
                           separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"obs_{digest}"


def make_permalink(record_id: str) -> str:
    return f"/item/{record_id}/"


# ---------------------------------------------------------------------------
# 输入 → 条目
# ---------------------------------------------------------------------------

def _safe_url(url: str | None) -> str | None:
    """仅 http/https 生成外链；其他协议返回 None（页面不渲染为可点击）。"""
    if not url:
        return None
    if re.match(r"^https?://", url, re.I):
        return url
    return None


def build_record(diff_entry: dict, date: str, source_id: str, registry: dict,
                 provenance: dict) -> dict:
    """从 diff 变化条目构建归档记录（公开内容部分）。

    diff_entry: data/diff/*.json changes[] 中 status=changed 的条目
    provenance: {"diff_file": 相对路径}（内部可追溯字段）
    """
    reg = registry[source_id]
    platform = diff_entry.get("platform", reg["display_name"])
    stype = diff_entry.get("source_type", reg["source_type"])
    url = _safe_url(diff_entry.get("url") or reg.get("primary_url"))

    kind = "substantive" if diff_entry.get("kind") == "substantive" else "jitter"
    # 注意：sync-diff-to-site 调用前应先跑 filter_and_pair 得到 kind；
    # 直接归档原始 diff 时由调用方预处理。这里信任输入的 kind，没有则为 jitter。

    summary, summary_origin = None, None
    if diff_entry.get("llm_summary"):
        summary, summary_origin = diff_entry["llm_summary"], "llm"
    elif diff_entry.get("signal_preview"):
        summary, summary_origin = diff_entry["signal_preview"], "rule"

    # 完整性：diff 原始产物有增删行上限；有原始计数可比对时判 truncated
    added = list(diff_entry.get("added_lines") or [])
    removed = list(diff_entry.get("removed_lines") or [])
    added_count = diff_entry.get("added_count")
    removed_count = diff_entry.get("removed_count")
    completeness = "unknown"
    if added_count is not None and removed_count is not None:
        if len(added) < added_count or len(removed) < removed_count:
            completeness = "truncated"

    record = {
        "schemaVersion": SCHEMA_VERSION,
        "id": make_record_id(source_id, date),
        "sourceId": source_id,
        "date": date,
        "recordType": "source_observation",
        "changeType": "source_updated",
        "revision": 1,
        "status": "active",
        "platform": platform,
        "sourceType": stype,
        "sourceUrl": url,
        "title": f"{platform} · {reg.get('type_label') or stype}来源更新",
        "summary": summary,
        "summaryOrigin": summary_origin,
        "observedAt": None,
        "timePrecision": "date",
        "revisedAt": None,
        "revisionReason": None,
        "kind": kind,
        "diff": {
            "pairs": list(diff_entry.get("pairs") or []),
            "added_lines": added,
            "removed_lines": removed,
            "added_count": added_count if added_count is not None else len(added),
            "removed_count": removed_count if removed_count is not None else len(removed),
            "raw_added_count": diff_entry.get("raw_added_count"),
            "raw_removed_count": diff_entry.get("raw_removed_count"),
        },
        "evidenceLevel": "source_diff",
        "diffCompleteness": completeness,
        "provenance": provenance,
        "permalink": make_permalink(make_record_id(source_id, date)),
    }
    return record


# ---------------------------------------------------------------------------
# 修订比较（公开内容，排除辅助字段）
# ---------------------------------------------------------------------------

_COMPARE_EXCLUDE = {"revision", "revisedAt", "revisionReason", "updated_at",
                    # provenance 是内部可追溯字段（diff 文件定位），不属于公开内容：
                    # 重新回填时同一输入的 provenance 不应触发"有意义修订"
                    "provenance"}


def content_signature(record: dict) -> str:
    """参与修订判定的公开内容签名（排除程序辅助字段）。"""
    core = {k: v for k, v in record.items() if k not in _COMPARE_EXCLUDE}
    return json.dumps(core, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def load_current(records_root: Path, record_id: str) -> dict | None:
    f = records_root / f"{record_id}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ArchiveError(f"已有归档损坏: {f} ({e})——不允许当成空库重新初始化")


def restore_current_from_revisions(records_root: Path,
                                   revisions_root: Path, rid: str) -> dict | None:
    """校验完整修订链后恢复缺失或落后的 current，复用已提交版本。"""
    cur = load_current(records_root, rid)
    files = list((revisions_root / rid).glob("*.json"))
    if not files:
        if cur is not None:
            raise ArchiveError(f"修订缺失: {rid}")
        return None
    chain = {}
    try:
        for f in files:
            rv = json.loads(f.read_text(encoding="utf-8"))
            rev = rv["revision"]
            if (type(rev) is not int or rev < 1 or f.name != f"{rev}.json"
                    or rv["id"] != rid
                    or make_record_id(rv["sourceId"], rv["date"]) != rid
                    or rv["permalink"] != make_permalink(rid)
                    or rv["status"] not in ("active", "withdrawn")
                    or (rev > 1 and (not rv.get("revisedAt") or not rv.get("revisionReason")))):
                raise ValueError(f"非法修订: {f}")
            chain[rev] = rv
        top = max(chain)
        if set(chain) != set(range(1, top + 1)):
            raise ValueError("修订链不连续")
        if cur is not None and chain.get(cur["revision"]) != cur:
            raise ValueError("当前记录与对应修订不一致")
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
        raise ArchiveError(f"修订校验失败，拒绝覆盖: {rid}: {e}") from e
    latest = chain[top]
    if cur != latest:
        _atomic_write(records_root / f"{rid}.json", latest)
    return latest


def merge_record(records_root: Path, revisions_root: Path, new: dict,
                 actor: str = "sync") -> dict:
    """合并一条记录到归档。返回 {"action": created|updated|unchanged|...}。

    规则：
    - 新条目 → 落盘 revision=1
    - 公开内容有实质变化 → 保留 ID，revision+1，旧版本存档，记录原因
    - 内容相同 → 不动（幂等，文件字节不变）
    - 摘要合并（R4）：新输入无摘要（None）→ 保留已有；
      新输入为 rule 且已有 llm → 保留 llm（不降级）；
      显式提供新摘要（含 llm 新值）→ 更新
    - withdrawn 后再次 changed → 恢复 active，新修订

    写入顺序（R3）：先预检修订文件可写 → 先写修订 → 再写当前记录。
    修订写入失败时当前记录保持旧版完好，可幂等重跑。
    """
    rid = new["id"]
    # 恢复缺失或落后的当前记录，保留已提交修订的时间与内容。
    cur = restore_current_from_revisions(records_root, revisions_root, rid)

    if cur is not None:
        # 摘要保留规则（R4：共用逻辑，两个入口一致）
        new = _merge_summary(cur, new)

    if cur is None:
        new["revision"] = 1
        _commit(records_root, revisions_root, new)
        return {"action": "created", "id": rid}

    new_status = new.get("status", "active")
    cur_status = cur.get("status", "active")

    sig_new = content_signature({**new, "revision": cur["revision"]})
    sig_cur = content_signature(cur)

    if sig_new == sig_cur and new_status == cur_status:
        return {"action": "unchanged", "id": rid}

    revised = dict(cur)
    for k, v in new.items():
        if k in ("revision", "revisedAt", "revisionReason"):
            continue
        revised[k] = v
    revised["revision"] = cur["revision"] + 1

    if cur_status == "withdrawn" and new_status == "active":
        revised["revisionReason"] = "重新计算后再次确认变化，恢复收录"
    elif new_status == "withdrawn":
        revised["revisionReason"] = "重新计算后未识别到变化，撤回收录"
    else:
        revised["revisionReason"] = _diff_reason(cur, new)
    import datetime as _dt
    revised["revisedAt"] = _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="seconds")

    _commit(records_root, revisions_root, revised)
    return {"action": "updated", "id": rid, "revision": revised["revision"]}


def _merge_summary(cur: dict, new: dict) -> dict:
    """摘要合并规则（R4）：
    - 新输入无摘要 → 保留已有摘要（不因退窗/无输入清空）
    - 新输入 rule 且已有 llm → 保留 llm（不降级）
    - 显式新摘要（llm 新值或 rule→有值）→ 用新值
    """
    if new.get("summary") is None and cur.get("summary") is not None:
        new = dict(new)
        new["summary"] = cur["summary"]
        new["summaryOrigin"] = cur.get("summaryOrigin")
    elif (new.get("summaryOrigin") == "rule"
          and cur.get("summaryOrigin") == "llm"
          and cur.get("summary") is not None
          and new.get("summary") != cur.get("summary")):
        # rule 输入与已有 llm 摘要不同：视为同一变化的规则预览，不降级 llm
        new = dict(new)
        new["summary"] = cur["summary"]
        new["summaryOrigin"] = cur.get("summaryOrigin")
    return new


def _commit(records_root: Path, revisions_root: Path, record: dict) -> None:
    """可靠写入（R3）：预检 → 先修订 → 后当前。

    修订文件预检（存在且内容不同 → 拒绝）失败时抛 ArchiveError，
    当前记录未被触碰；修订写入成功后才原子替换当前记录。
    """
    rid = record["id"]
    _check_revision_writable(revisions_root, rid, record)
    _write_revision(revisions_root, rid, record)
    _atomic_write(records_root / f"{rid}.json", record)


def _check_revision_writable(revisions_root: Path, record_id: str,
                             record: dict) -> None:
    rev_file = revisions_root / record_id / f"{record['revision']}.json"
    if rev_file.exists():
        existing = rev_file.read_text(encoding="utf-8")
        new_content = json.dumps(record, ensure_ascii=False, indent=2)
        if existing != new_content:
            raise ArchiveError(
                f"修订版本文件已存在且内容不同，拒绝覆盖（当前记录未修改）: {rev_file}")


def withdraw_record(records_root: Path, revisions_root: Path, record_id: str,
                    reason: str = "重新计算后未识别到变化，撤回收录",
                    actor: str = "sync") -> dict:
    """明确 unchanged 输入触发的撤回（保留 ID 与内容）。"""
    cur = restore_current_from_revisions(records_root, revisions_root, record_id)
    if cur is None:
        return {"action": "absent", "id": record_id}
    if cur.get("status") == "withdrawn":
        return {"action": "unchanged", "id": record_id}
    revised = dict(cur)
    revised["status"] = "withdrawn"
    revised["revision"] = cur["revision"] + 1
    revised["revisionReason"] = reason
    import datetime as _dt
    revised["revisedAt"] = _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="seconds")
    _commit(records_root, revisions_root, revised)
    return {"action": "withdrawn", "id": record_id, "revision": revised["revision"]}


def _diff_reason(cur: dict, new: dict) -> str:
    reasons = []
    if cur.get("summary") != new.get("summary"):
        reasons.append("摘要更新")
    if cur.get("diff") != new.get("diff"):
        reasons.append("变化内容更新")
    if cur.get("kind") != new.get("kind"):
        reasons.append("分类更新")
    if cur.get("platform") != new.get("platform") \
            or cur.get("sourceUrl") != new.get("sourceUrl"):
        reasons.append("来源元数据更新")
    return "；".join(reasons) or "内容修订"


# ---------------------------------------------------------------------------
# IO 辅助
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, data: dict) -> None:
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False,
                                     suffix=".tmp", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(f.name, path)


def _write_revision(revisions_root: Path, record_id: str, record: dict) -> None:
    """历史版本追加（预检由 _check_revision_writable 完成；此处幂等写入）。"""
    rev_file = revisions_root / record_id / f"{record['revision']}.json"
    if rev_file.exists():
        return  # 预检确认内容一致，幂等
    _atomic_write(rev_file, record)


def load_revision(revisions_root: Path, record_id: str, revision: int) -> dict:
    f = revisions_root / record_id / f"{revision}.json"
    if not f.exists():
        raise ArchiveError(f"修订不存在: {f}")
    return json.loads(f.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 索引
# ---------------------------------------------------------------------------

def build_index(records_root: Path) -> list[dict]:
    """从 data/records/*.json 生成稳定排序的可重建索引。"""
    items = []
    for f in sorted(records_root.glob("obs_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ArchiveError(f"归档损坏，无法生成索引: {f} ({e})")
        items.append({
            "id": r["id"], "date": r["date"], "platform": r["platform"],
            "sourceId": r["sourceId"], "kind": r["kind"], "status": r["status"],
            "title": r["title"], "permalink": r["permalink"],
            "revision": r["revision"],
        })
    # 排序：日期倒序 → 平台 → id（全序，保证字节稳定）
    items.sort(key=lambda x: (x["date"], x["platform"], x["id"]), reverse=True)
    # date 倒序但同日内稳定：分两步
    items.sort(key=lambda x: (x["platform"], x["id"]))
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def validate_archive(records_root: Path, revisions_root: Path,
                     index_items: list[dict] | None = None) -> list[str]:
    """一致性校验（R1/RR3 增强）。

    检查项：
    - 当前记录：JSON 可解析、文件名=id、permalink、id 由 (sourceId,date) 派生
    - 修订链：1..revision 全部存在、逐版本 JSON 可解析、版本号连续、
      最新修订内容与当前记录一致（排除程序辅助字段后）
    - 索引（传入时）：双向完整、字段一致
    - 孤立修订目录
    返回错误清单（空=通过）。
    """
    errors = []
    records = {}
    for f in sorted(records_root.glob("obs_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"归档损坏: {f}: {e}")
            continue
        rid = r.get("id")
        if rid != f.stem:
            errors.append(f"归档文件名与内部 id 不一致: {f.stem} != {rid}")
            continue
        if r.get("permalink") != make_permalink(rid):
            errors.append(f"permalink 不一致: {rid}")
        if r.get("sourceId") and r.get("date"):
            if make_record_id(r["sourceId"], r["date"]) != rid:
                errors.append(f"id 与 (sourceId, date) 不匹配: {rid}")
        top_rev = r.get("revision", 1)
        if not isinstance(top_rev, int) or top_rev < 1:
            errors.append(f"revision 非法: {rid} = {top_rev!r}")
            continue
        records[rid] = r

        # 修订链逐版本校验（R3）
        rev_dir = revisions_root / rid
        # 修订目录中不得有超出当前 revision 的版本（写入中断/篡改痕迹）
        if rev_dir.exists():
            extra = [f for f in rev_dir.glob("*.json")
                     if f.stem.isdigit() and int(f.stem) > top_rev]
            for f in extra:
                errors.append(
                    f"孤立修订（版本超过当前 revision {top_rev}）: {rid} {f.name}")
        latest_parsed = None
        for rev in range(1, top_rev + 1):
            rev_file = rev_dir / f"{rev}.json"
            if not rev_file.exists():
                errors.append(f"修订缺失: {rid} rev {rev}")
                continue
            try:
                rv = json.loads(rev_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f"修订损坏: {rid} rev {rev}: {e}")
                continue
            if rv.get("revision") != rev:
                errors.append(
                    f"修订版本号不连续: {rid} 期望 rev {rev}，文件内为 {rv.get('revision')}")
            if rv.get("id") != rid:
                errors.append(f"修订 id 不匹配: {rid} rev {rev}")
            latest_parsed = rv
        # 最新修订 ↔ 当前记录一致（排除比较用的辅助字段）
        if latest_parsed is not None:
            _EXTRA = {"revision", "revisedAt", "revisionReason"}
            a = {k: v for k, v in latest_parsed.items() if k not in _EXTRA}
            b = {k: v for k, v in r.items() if k not in _EXTRA}
            if a != b:
                errors.append(
                    f"最新修订与当前记录内容不一致: {rid} "
                    f"(rev {latest_parsed.get('revision')} vs current)")

    # 孤立修订目录
    if revisions_root.exists():
        for d in revisions_root.glob("obs_*"):
            if d.is_dir() and d.name not in records:
                errors.append(f"孤立修订目录（无当前记录）: {d.name}")

    # 索引双向校验（R1）
    if index_items is not None:
        idx_by_id = {}
        for it in index_items:
            rid = it.get("id")
            if rid in idx_by_id:
                errors.append(f"索引重复条目: {rid}")
            idx_by_id[rid] = it
        for rid, r in records.items():
            it = idx_by_id.get(rid)
            if it is None:
                errors.append(f"索引缺失记录: {rid}")
                continue
            for field in ("date", "platform", "sourceId", "kind", "status",
                          "title", "permalink"):
                if it.get(field) != r.get(field):
                    errors.append(
                        f"索引字段不一致: {rid}.{field} "
                        f"索引={it.get(field)!r} 归档={r.get(field)!r}")
        for rid in idx_by_id:
            if rid not in records:
                errors.append(f"索引悬空（引用不存在的记录）: {rid}")
    return errors


# ---------------------------------------------------------------------------
# 公共归档管线（R2：两入口共用——预检全部输入 → 计划 → 一次性应用）
# ---------------------------------------------------------------------------

def _is_valid_date_name(stem: str) -> bool:
    from datetime import datetime as _dtm
    try:
        _dtm.strptime(stem, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_diff_entry(data: dict, path, registry: dict) -> str | None:
    """校验单个 diff 文件的输入（R2 预检）。返回业务日期或抛 ArchiveError。

    检查：JSON 结构、changes 类型、来源映射、同日身份冲突。零写入。
    """
    if not isinstance(data, dict):
        raise ArchiveError(f"diff 结构损坏（非对象）: {path}")
    date = data.get("date") or getattr(path, "stem", "")
    if not isinstance(date, str) or not _is_valid_date_name(date) or date != Path(path).stem:
        raise ArchiveError(f"diff 日期非法或与文件名不一致: {path}")
    if not isinstance(data.get("changes", []), list):
        raise ArchiveError(f"diff 结构损坏（changes 非列表）: {path}")
    seen_source_ids: dict[str, dict] = {}
    for c in data.get("changes", []):
        if not isinstance(c, dict):
            raise ArchiveError(f"diff 条目非对象: {path}")
        status = c.get("status")
        if status not in ("changed", "unchanged", "first_fetch", "fetch_failed"):
            raise ArchiveError(
                f"diff 条目 status 非法: {path} {status!r}")
        if status not in ("changed", "unchanged"):
            continue  # first_fetch / fetch_failed 不产生变化条目
        sid = resolve_source_id(registry, c.get("platform", ""),
                                c.get("source_type", ""), c.get("url"))
        if sid in seen_source_ids:
            prev = seen_source_ids[sid]
            raise ArchiveError(
                f"同日同 source_id 多条输入，拒绝静默覆盖: {path} "
                f"{sid}（{prev.get('platform')}|{prev.get('source_type')} 与 "
                f"{c.get('platform')}|{c.get('source_type')}）——请检查 registry 映射")
        seen_source_ids[sid] = c
    return date


def load_and_validate_diff(path, registry: dict) -> tuple[dict, str]:
    """读取 + 校验单个 diff（R2：损坏显式失败，不静默跳过）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ArchiveError(f"diff 文件损坏（合法日期名，必须处理）: {path}: {e}")
    date = validate_diff_entry(data, path, registry)
    return data, date


def plan_records(data: dict, date: str, path, registry: dict) -> list:
    """把单个 diff 的 changed/unchanged 转成归档操作计划（不写入）。

    依赖调用方注入 filter_and_pair（避免 record_archive 依赖 diff_clean
    造成循环）。entries_prefiltered=True 时跳过降噪直接使用。
    """
    ops = []
    for c in data.get("changes", []):
        if not isinstance(c, dict):
            raise ArchiveError(f"diff 条目非对象: {path}")
        status = c.get("status")
        if status == "unchanged":
            sid = resolve_source_id(registry, c.get("platform", ""),
                                    c.get("source_type", ""), c.get("url"))
            ops.append({"op": "withdraw", "id": make_record_id(sid, date)})
        elif status == "changed":
            entry = _PREFILTER(c) if _PREFILTER else c
            sid = resolve_source_id(registry, entry.get("platform", ""),
                                    entry.get("source_type", ""), entry.get("url"))
            ops.append({"op": "merge", "record": build_record(
                entry, date, sid, registry,
                provenance={"diff_file": str(path)})})
    return ops


_PREFILTER = None  # 由入口注入 diff_clean.filter_and_pair


def set_prefilter(fn) -> None:
    global _PREFILTER
    _PREFILTER = fn


def _apply_plan(ops: list, records_root: Path, revisions_root: Path) -> dict:
    """应用操作计划（R2：全部预检通过后才调用）。"""
    stats = {"created": 0, "updated": 0, "unchanged": 0, "withdrawn": 0}
    for op in ops:
        if op["op"] == "withdraw":
            r = withdraw_record(records_root, revisions_root, op["id"])
        else:
            r = merge_record(records_root, revisions_root, op["record"])
        stats[r["action"]] = stats.get(r["action"], 0) + 1
    return stats


def plan_and_apply(diff_dir: Path, registry: dict, records_root: Path,
                   revisions_root: Path) -> dict:
    """R2 主流程：预检全部输入 → 形成全部计划 → 一次性应用。

    任何输入损坏/未映射/同日冲突 → 写入任何内容前抛 ArchiveError，
    归档保持字节不变（失败可幂等重跑）。
    """
    files = sorted(Path(diff_dir).glob("*.json"))
    plans = []
    skipped_nondate = 0
    for f in files:  # 阶段 1：全部读取+校验+计划（零写入）
        if not _is_valid_date_name(f.stem):
            skipped_nondate += 1
            continue
        data, date = load_and_validate_diff(f, registry)
        plans.append(plan_records(data, date, f, registry))
    totals = apply_plan([op for ops in plans for op in ops], records_root, revisions_root)
    return {"processed": len(plans), "skipped_nondate": skipped_nondate,
            **totals}


def _recover_archive(records_root: Path, revisions_root: Path) -> None:
    ids = {p.stem for p in records_root.glob("obs_*.json")}
    ids.update(p.name for p in revisions_root.glob("obs_*") if p.is_dir())
    for rid in sorted(ids):
        restore_current_from_revisions(records_root, revisions_root, rid)
    errors = validate_archive(records_root, revisions_root)
    if errors:
        raise ArchiveError("归档校验失败: " + "; ".join(errors))


def apply_plan(ops: list, records_root: Path, revisions_root: Path) -> dict:
    """先在隔离副本验证整个批次和已有归档，再写入真实归档。

    输入/归档错误零写入；实际磁盘写入中断由修订链恢复，不承诺批次事务。
    """
    import shutil
    import tempfile
    import copy
    with tempfile.TemporaryDirectory(prefix="archive-preflight-") as tmp:
        root = Path(tmp)
        records, revisions = root / "records", root / "revisions"
        for src, dst in ((records_root, records), (revisions_root, revisions)):
            if src.exists():
                shutil.copytree(src, dst)
        _recover_archive(records, revisions)
        _apply_plan(copy.deepcopy(ops), records, revisions)
        errors = validate_archive(records, revisions)
        if errors:
            raise ArchiveError("计划校验失败: " + "; ".join(errors))
    _recover_archive(records_root, revisions_root)
    return _apply_plan(ops, records_root, revisions_root)
