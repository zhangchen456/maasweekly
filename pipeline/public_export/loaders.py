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
        self.daily_changes: dict = {}             # site/src/data/daily_changes.json
        self.source_registry: list[dict] = []
        self.provider_map: dict = {}


def load_all(input_root: Path, provider_map_path: Path) -> LoadedInputs:
    """从仓库正式归档加载全部输入（input_root = 仓库根）。"""
    li = LoadedInputs()
    root = input_root

    li.provider_map = load_provider_map(provider_map_path)
    li.source_registry = load_source_registry(
        _safe_path(root, "pipeline/config/source_registry.json"))

    # Task 01：records + record-revisions（目录允许不存在：空归档）
    rec_dir = _safe_path(root, "data/records")
    if rec_dir.exists():
        for f in sorted(rec_dir.glob("obs_*.json")):
            li.records.append(read_json(f))
    rev_root = _safe_path(root, "data/record-revisions")
    if rev_root.exists():
        for d in sorted(rev_root.iterdir()):
            if not d.is_dir():
                continue
            revs = []
            for rf in sorted(d.glob("*.json"), key=lambda p: int(p.stem)
                             if p.stem.isdigit() else 0):
                revs.append(read_json(rf))
            if revs:
                li.record_revisions[revs[0]["id"]] = revs

    # Task 02：price-records + price-record-revisions
    pr_dir = _safe_path(root, "data/price-records")
    if pr_dir.exists():
        for f in sorted(pr_dir.glob("price_*.json")):
            li.price_records.append(read_json(f))
    prev_root = _safe_path(root, "data/price-record-revisions")
    if prev_root.exists():
        for d in sorted(prev_root.iterdir()):
            if not d.is_dir():
                continue
            revs = []
            for rf in sorted(d.glob("*.json"), key=lambda p: int(p.stem)
                             if p.stem.isdigit() else 0):
                revs.append(read_json(rf))
            if revs:
                li.price_revisions[revs[0]["id"]] = revs

    # Task 02：fact versions（全量——evidence 反查需要）
    pfv_dir = _safe_path(root, "data/price-facts/versions")
    if pfv_dir.exists():
        for f in sorted(pfv_dir.glob("pfv_*.json")):
            v = read_json(f)
            li.fact_versions[v["version_id"]] = v

    # Task 02：evidence
    ev_dir = _safe_path(root, "data/price-evidence")
    if ev_dir.exists():
        for f in sorted(ev_dir.glob("ev_*.json")):
            ev = read_json(f)
            li.evidence[ev["id"]] = ev

    # Task 02：current
    li.current = read_json(_safe_path(root, "data/price-facts/current.json"))

    # 正式周报：md frontmatter + structured json 一一对应（门禁）
    weekly_md_dir = _safe_path(root, "site/src/content/weekly")
    structured_dir = _safe_path(root, "site/src/content/weekly-structured")
    for mf in sorted(weekly_md_dir.glob("*.md")):
        wid = mf.stem
        sf = structured_dir / f"{wid}.json"
        if not sf.exists():
            raise ExportError(f"正式周报缺结构化投影: {wid}（先跑 extract-structured.py）")
        structured = read_json(sf)
        if structured.get("date") != wid:
            raise ExportError(f"周报结构化 id 不一致: {wid} vs {structured.get('date')}")
        li.weekly.append({
            "id": wid,
            "frontmatter": _parse_frontmatter(mf.read_text(encoding="utf-8")),
            "structured": structured,
        })

    # 来源状态流（滚动窗口；窗口外推导为 unknown）
    li.daily_changes = read_json(
        _safe_path(root, "site/src/data/daily_changes.json"))
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
