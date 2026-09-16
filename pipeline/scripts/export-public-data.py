#!/usr/bin/env python3
"""export-public-data.py：公开数据投影唯一入口（Task 03 M3）。

从已校验的 Task 01/02 归档与正式周报构建完整 release：
加载 → 投影 → 全量校验（内存）→ 临时目录写盘 → hash 复核 → 原子发布。

用法：
  python3 pipeline/scripts/export-public-data.py                # 构建并发布到 data/public/v1/
  python3 pipeline/scripts/export-public-data.py --check       # 只校验现有 release，零写入
  python3 pipeline/scripts/export-public-data.py --dry-run     # 完整构建到临时目录，正式目录逐字节不变
  python3 pipeline/scripts/export-public-data.py --output-dir /tmp/public-v1   # 隔离输出
  python3 pipeline/scripts/export-public-data.py --input-root <dir>            # 测试注入输入（默认仓库根）

契约（任务书 §4/§5）：
- datasetVersion 同输入稳定；同版本重建 → 校验后零写入（幂等）
- 保留：当前版本 + 7 自然日内 manifest 记录的 + 至少上一版；只清理
  data/public/v1/releases/ 白名单路径，绝不触碰 Task 01/02 原始归档
- 输入损坏/未知身份/引用悬空 → 非零退出，正式目录零写入
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "pipeline"))

from public_export import canonical, loaders, projector, validator  # noqa: E402
from public_export.loaders import ExportError  # noqa: E402

REPO_ROOT = BASE
DEFAULT_OUTPUT = BASE / "data" / "public" / "v1"
PROVIDER_MAP = BASE / "pipeline" / "config" / "public_providers.json"
BUSINESS_FILES = ("changes.json", "items.json", "prices.json",
                  "evidence.json", "weekly.json", "status.json")
RETENTION_DAYS = 7


def build_release(input_root: Path) -> dict:
    """加载 → 投影 → 校验 → 返回 {collections, datasetVersion, dataThrough}。"""
    li = loaders.load_all(input_root, PROVIDER_MAP)
    pm = li.provider_map
    si = projector.SourceStatusIndex(li.daily_changes, li.source_registry)
    ps = projector.build_price_source_status(li.current)
    le = projector.build_latest_event_by_fact(li.price_records)

    changes = canonical.changes_sorted(
        [projector.project_source_change(r, si, pm) for r in li.records]
        + [projector.project_price_change(r, li.fact_versions, li.evidence,
                                          pm, ps) for r in li.price_records])
    items = canonical.by_id_sorted([
        projector.project_item(c, li.record_revisions.get(c["id"])
                               or li.price_revisions.get(c["id"]))
        for c in changes])
    prices = sorted(
        (projector.project_price_fact(li.fact_versions[e["version_id"]], pm, ps, le)
         for e in (li.current.get("facts") or {}).values()),
        key=canonical.prices_sort_key)
    rev = projector.build_evidence_reverse_index(li.fact_versions)
    reachable = {e["version_id"] for e in (li.current.get("facts") or {}).values()} | \
        {v for r in li.price_records
         for v in (r.get("beforeVersionId"), r.get("afterVersionId")) if v}
    evidence = canonical.by_id_sorted([
        projector.project_evidence(
            ev, pm,
            [f for f in (rev[eid]["fact_ids"] if eid in rev else [])
             if f in reachable],
            rev[eid]["observed"] if eid in rev else None)
        for eid, ev in li.evidence.items()])
    weekly = canonical.by_id_sorted(
        [projector.project_weekly(w) for w in li.weekly])
    status = projector.project_status(li, changes, prices, weekly, si)

    errs = validator.validate_entities(changes, prices, evidence, weekly, status)
    errs += validator.validate_references(changes, prices, evidence)
    if errs:
        raise ExportError("投影校验失败（" + str(len(errs)) + " 项）: "
                          + "; ".join(errs[:10]))

    data_through = canonical.compute_data_through(changes, prices, weekly)
    version = canonical.compute_dataset_version(
        {"changes": changes, "items": items, "prices": prices,
         "evidence": evidence, "weekly": weekly, "status": status},
        data_through)
    return {"changes": changes, "items": items, "prices": prices,
            "evidence": evidence, "weekly": weekly, "status": status,
            "datasetVersion": version, "dataThrough": data_through}


def coverage_of(rel: dict) -> dict:
    changes = rel["changes"]
    dates = sorted(c["observationDate"] for c in changes) or ["-"]
    return {
        "changes": {"from": dates[0], "to": dates[-1], "count": len(changes)},
        "prices": {"facts": len(rel["prices"])},
        "evidence": {"count": len(rel["evidence"])},
        "weekly": {"count": len(rel["weekly"]),
                   "latestId": rel["weekly"][-1]["id"] if rel["weekly"] else None},
    }


def write_release(rel: dict, out_dir: Path, version: str) -> list[dict]:
    """业务文件 + per-release manifest 写入目录。

    每个 release 自带 manifest.json（验收 P1-1：cursor 读历史版本时
    服务端按与当前版本相同的 hash/bytes/路径校验加载，元数据不丢失）。
    release manifest 的 generatedAt 不影响幂等——datasetVersion 不含
    该字段，重建时目录已存在即零写入。
    """
    files_meta: list[dict] = []
    for name in BUSINESS_FILES:
        key = name[:-5]  # changes.json → changes
        payload = rel[key]
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        data = text.encode("utf-8")
        (out_dir / name).write_bytes(data)
        files_meta.append({
            "path": f"releases/{version}/{name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })
    release_manifest = {
        "schemaVersion": "1.0",
        "datasetVersion": version,
        "generatedAt": _now_iso(),
        "dataThrough": rel["dataThrough"],
        "coverage": coverage_of(rel),
        "files": files_meta,
        "retainedVersions": [],  # 顶层指针字段；release 内恒空
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(release_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return files_meta


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def publish(output_root: Path, rel: dict) -> int:
    """两阶段发布：临时目录 → 校验 → 原子 rename → manifest。"""
    version = rel["datasetVersion"]
    releases_root = output_root / "releases"
    target = releases_root / version
    manifest_file = output_root / "manifest.json"

    # 幂等：目标已存在 → 校验字节一致后零写入
    if target.exists():
        existing = {f.name: f.read_bytes() for f in
                    sorted(target.glob("*.json")) if f.name != "manifest.json"}
        same = all(
            existing.get(name) ==
            (json.dumps(rel[name[:-5]], ensure_ascii=False, indent=2) + "\n").encode()
            for name in BUSINESS_FILES)
        # per-release manifest 缺失（P1-1 升级前的旧形态）→ 视为需重写
        has_release_manifest = (target / "manifest.json").exists()
        if same and has_release_manifest and manifest_file.exists():
            print(f"datasetVersion {version} 已发布且内容一致，零写入（幂等）")
            return 0
        if same and not has_release_manifest:
            print(f"release 缺 per-release manifest（P1-1 升级），重写目录")
        elif not same:
            raise ExportError(
                f"release 已存在但内容不同（不可变契约破坏）: {target}")

    releases_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".tmp-export-", dir=output_root))
    try:
        files_meta = write_release(rel, tmp, version)
        # hash/bytes 复核（写后重读）
        errs = _recheck_files(tmp, files_meta, version)
        if errs:
            raise ExportError("临时目录 hash 复核失败: " + "; ".join(errs))
        # 原子发布
        if target.exists():
            shutil.rmtree(target)  # 不可变契约已保证内容一致才走到这
        os.rename(tmp, target)
        tmp = None
    finally:
        if tmp is not None and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    # manifest
    prev_retained: list[dict] = []
    if manifest_file.exists():
        try:
            prev = json.loads(manifest_file.read_text(encoding="utf-8"))
            prev_retained = prev.get("retainedVersions") or []
        except json.JSONDecodeError:
            pass
    now = _now_iso()
    retained = [{"datasetVersion": version, "generatedAt": now}] + [
        r for r in prev_retained if r["datasetVersion"] != version]
    retained = _apply_retention(retained, version, now)
    manifest = {
        "schemaVersion": "1.0",
        "datasetVersion": version,
        "generatedAt": now,
        "dataThrough": rel["dataThrough"],
        "coverage": coverage_of(rel),
        "files": files_meta,
        "retainedVersions": retained,
    }
    _atomic_write_json(manifest_file, manifest)
    _cleanup_releases(releases_root, retained)
    return 0


def _recheck_files(directory: Path, files_meta: list[dict], version: str) -> list[str]:
    errs = []
    for fm in files_meta:
        name = Path(fm["path"]).name
        data = (directory / name).read_bytes()
        if len(data) != fm["bytes"] or \
                hashlib.sha256(data).hexdigest() != fm["sha256"]:
            errs.append(f"{version}/{name}")
    return errs


def _apply_retention(retained: list[dict], current: str, now_iso: str) -> list[dict]:
    """当前 + 7 自然日内 + 至少上一版。"""
    now = datetime.fromisoformat(now_iso)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    out = [retained[0]]
    recent = [r for r in retained[1:]
              if datetime.fromisoformat(r["generatedAt"]) >= cutoff]
    out.extend(recent)
    if len(out) < 2 and len(retained) >= 2:
        out.append(retained[1])
    return out


def _cleanup_releases(releases_root: Path, retained: list[dict]) -> None:
    """只删 releases/ 下不在保留集的目录（白名单路径，绝不触碰归档）。"""
    keep = {r["datasetVersion"] for r in retained}
    if not releases_root.exists():
        return
    for d in releases_root.iterdir():
        if d.is_dir() and d.name.startswith("ds_") and d.name not in keep:
            shutil.rmtree(d)


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def run_check(output_root: Path) -> int:
    """--check：校验现有 manifest 与全部文件，零写入。"""
    manifest_file = output_root / "manifest.json"
    if not manifest_file.exists():
        print(f"✗ manifest 不存在: {manifest_file}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ manifest 损坏: {e}", file=sys.stderr)
        return 1
    errs = validator.validate_release_files(output_root, manifest)
    if errs:
        print(f"✗ 公开数据校验失败（{len(errs)} 项）:", file=sys.stderr)
        for e in errs[:10]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    n = len(manifest.get("files") or [])
    print(f"✓ 公开数据校验通过：{manifest['datasetVersion']} · "
          f"{n} 文件 · dataThrough {manifest.get('dataThrough')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="只校验，零写入")
    ap.add_argument("--dry-run", action="store_true",
                    help="完整构建到临时目录，正式目录逐字节不变")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                    help="输出根（默认 data/public/v1）")
    ap.add_argument("--input-root", type=Path, default=REPO_ROOT,
                    help="输入根（默认仓库根；测试注入用）")
    args = ap.parse_args(argv)

    if args.check:
        return run_check(args.output_dir)

    try:
        rel = build_release(args.input_root)
    except ExportError as e:
        print(f"✗ 构建失败（正式目录零写入）: {e}", file=sys.stderr)
        return 1

    counts = (f"changes={len(rel['changes'])} items={len(rel['items'])} "
              f"prices={len(rel['prices'])} evidence={len(rel['evidence'])} "
              f"weekly={len(rel['weekly'])}")
    if args.dry_run:
        print(f"[dry-run] datasetVersion={rel['datasetVersion']}")
        print(f"[dry-run] dataThrough={rel['dataThrough']}")
        print(f"[dry-run] {counts}")
        print("[dry-run] 正式目录零写入")
        return 0

    rc = publish(args.output_dir, rel)
    if rc == 0:
        print(f"✓ 发布 {rel['datasetVersion']}（{counts}）dataThrough={rel['dataThrough']}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
