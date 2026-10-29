"""loaders：公开导出的输入加载（Task 03 M2）。

安全规则（任务书 §5）：
- 输入根固定为仓库正式归档（--input-root 仅供测试注入）
- 拒绝符号链接与目录穿越（所有路径 resolve 后必须仍在根内）
- 输入 JSON 损坏 → ExportError（exporter 非零退出，不在 loader 静默修复）

加载内容：Task 01 records + 修订、Task 02 price-records + 修订 +
fact versions + evidence + current、正式周报（md frontmatter +
structured）、daily_changes（来源状态流）、registry 与 provider 映射。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ExportError(Exception):
    """公开导出失败（输入损坏/未知身份/引用悬空）。"""


def _safe_path(root: Path, rel: str | Path) -> Path:
    """路径安全检查：resolve 后仍在 root 内且不经过符号链接。"""
    root = root.resolve()
    p = (root / rel)
    # 逐段检查符号链接（resolve 会穿透 symlink，必须显式拒绝）
    cur = root
    for part in Path(rel).parts:
        if part in ("..",):
            raise ExportError(f"路径穿越拒绝: {rel}")
        cur = cur / part
        if cur.is_symlink():
            raise ExportError(f"符号链接拒绝: {cur}")
    resolved = p.resolve()
    if not str(resolved).startswith(str(root) + "/") and resolved != root:
        raise ExportError(f"路径越界: {rel} → {resolved}")
    return p


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ExportError(f"JSON 损坏: {path}: {e}") from e


def load_provider_map(path: Path) -> dict:
    pm = read_json(path)
    for key in ("providers", "pricingProviderIdToProvider",
                "sourceToProvider", "pricingSourceKeyToSourceId"):
        if key not in pm:
            raise ExportError(f"provider 映射缺字段: {path}: {key}")
    return pm


def load_source_registry(path: Path) -> list[dict]:
    data = read_json(path)
    return data.get("sources") or []


class LoadedInputs:
    """全部输入的内存载体（exporter/projector 的唯一输入形态）。"""

    def __init__(self):
        self.records: list[dict] = []            # Task 01 obs_*
        self.record_revisions: dict[str, list[dict]] = {}  # id → 修订列表（升序）
        self.price_records: list[dict] = []      # Task 02 price_*
        self.price_revisions: dict[str, list[dict]] = {}
        self.fact_versions: dict[str, dict] = {}  # version_id → pfv
        self.evidence: dict[str, dict] = {}       # ev_id → ev
        self.current: dict = {}                   # price-facts/current.json
        self.weekly: list[dict] = []              # {id, frontmatter, structured}
        self.daily_changes: dict = {}             # standard source streams + independent summaries
        self.source_runtime: dict = {}            # committed fetch attempts, including unchanged
        self.source_registry: list[dict] = []
        self.provider_map: dict = {}
        self.public_evidence_index: dict | None = None


def load_all(input_root: Path, provider_map_path: Path, input_view=None) -> LoadedInputs:
    """从仓库正式归档加载全部输入（input_root = 仓库根）。"""
    li = LoadedInputs()
    root = input_root.resolve()
    from input_snapshot import load_view
    view = input_view if input_view is not None else load_view(root)
    def files(relative, pattern):
        if view: return view.glob(relative + '/' + pattern)
        return [(str(p.relative_to(root)), _safe_path(root, p.relative_to(root))) for p in sorted(_safe_path(root, relative).glob(pattern))]
    def input_path(relative):
        return view.path(relative) if view else _safe_path(root, relative)
    def json_inputs(relative, pattern):
        if view is not None and hasattr(view, 'iter_json'):
            return view.iter_json(relative, pattern)
        return ((logical, read_json(f)) for logical, f in files(relative, pattern))
    def input_json(relative):
        if view is not None and hasattr(view, 'read_json'):
            return view.read_json(relative)
        return read_json(input_path(relative))

    li.provider_map = load_provider_map(provider_map_path)
    li.source_registry = load_source_registry(
        _safe_path(root, "pipeline/config/source_registry.json"))

    for _, value in json_inputs('data/records', 'obs_*.json'): li.records.append(value)
    for logical, value in json_inputs('data/record-revisions', '*/*.json'):
        li.record_revisions.setdefault(value['id'], []).append(value)
    for revisions in li.record_revisions.values(): revisions.sort(key=lambda value: value['revision'])
    for _, value in json_inputs('data/price-records', 'price_*.json'): li.price_records.append(value)
    for logical, value in json_inputs('data/price-record-revisions', '*/*.json'):
        li.price_revisions.setdefault(value['id'], []).append(value)
    for revisions in li.price_revisions.values(): revisions.sort(key=lambda value: value['revision'])
    li.current = input_json('data/price-facts/current.json')
    compact = bool(getattr(view, 'compact_archives', False))
    reachable = {e['version_id'] for e in (li.current.get('facts') or {}).values()} | {
        v for record in li.price_records for v in (record.get('beforeVersionId'), record.get('afterVersionId')) if v}
    evidence_index = {} if compact else None
    for _, value in json_inputs('data/price-facts/versions', 'pfv_*.json'):
        vid = value['version_id']
        if not compact or vid in reachable:
            li.fact_versions[vid] = value
        if compact and value.get('evidence_id'):
            slot = evidence_index.setdefault(value['evidence_id'], {'fact_ids': [], 'observed': None})
            if vid in reachable:
                slot['fact_ids'].append(vid)
            # Preserve the existing exporter's observedAt semantics exactly,
            # including observations on facts not otherwise publicly reachable.
            stamp = value.get('observedAt')
            if stamp:
                old = slot['observed']
                slot['observed'] = [min(old[0], stamp), max(old[1], stamp)] if old else [stamp, stamp]
    if compact:
        for slot in evidence_index.values():
            slot['fact_ids'].sort()
        li.public_evidence_index = evidence_index
    for _, value in json_inputs('data/price-evidence', 'ev_*.json'):
        li.evidence[value['id']] = value

    # 正式周报：md frontmatter + structured json 一一对应（门禁）
    weekly_md_dir = _safe_path(root, "data/editorial/weekly")
    structured_dir = _safe_path(root, "data/derived/weekly-structured")
    weekly_files = ((logical, None) for logical in sorted(view.files) if Path(logical).match('data/editorial/weekly/*.md')) \
        if view is not None and hasattr(view, 'read_text') else files('data/editorial/weekly', '*.md')
    for logical, mf in weekly_files:
        wid = Path(logical).stem
        sf = f'data/derived/weekly-structured/{wid}.json'
        if (view is not None and sf not in view.files) or (view is None and not _safe_path(root, sf).exists()):
            raise ExportError(f"正式周报缺结构化投影: {wid}（先跑 extract-structured.py）")
        structured = input_json(sf)
        if structured.get("date") != wid:
            raise ExportError(f"周报结构化 id 不一致: {wid} vs {structured.get('date')}")
        li.weekly.append({
            "id": wid,
            "frontmatter": _parse_frontmatter(view.read_text(logical) if mf is None else mf.read_text(encoding='utf-8')),
            "structured": structured,
        })

    # Read both fallbacks and actual attempts from the same committed input view.
    from data_store import compose_daily, read
    li.daily_changes = compose_daily(root, view=view)
    li.source_runtime = read(root, "data/normalized/source-runtime.json", {}, view=view)
    return li


_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _parse_frontmatter(text: str) -> dict:
    m = _FRONT_RE.match(text)
    if not m:
        raise ExportError("周报缺 frontmatter")
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out
