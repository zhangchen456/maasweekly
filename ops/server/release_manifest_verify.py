#!/usr/bin/env python3
"""release_manifest_verify.py：服务器侧独立校验器（Task 06 M4）。

maasweekly-activate 调用；与 pipeline/scripts/release_manifest.py 的
verify_manifest 同一校验规则（schema/路径/双向集合/hash/symlink），但
零仓库依赖——单独分发到服务器 /usr/local/sbin/。

额外支持 --compare-identity <a> <b>（同 ID 幂等判定）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "production-release-v1"
RID_RE = re.compile(r"^rl_[0-9a-f]{10}_[0-9a-f]{12}$")
DS_RE = re.compile(r"^ds_[0-9a-f]{64}$")
BAD_PATH_RE = re.compile(r"(^\.\./|/\.\./|^\./|/\./|//|^/|[\x00-\x1f]|/$)")


def verify(root: Path) -> list[str]:
    mp = root / "metadata" / "release-manifest.json"
    if not mp.exists():
        return ["manifest 不存在"]
    try:
        m = json.loads(mp.read_text())
    except json.JSONDecodeError as e:
        return [f"manifest 损坏: {e}"]
    errors: list[str] = []
    if m.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion 非法: {m.get('schemaVersion')!r}")
    if not RID_RE.match(str(m.get("releaseId") or "")):
        errors.append(f"releaseId 格式非法")
    if not DS_RE.match(str(m.get("datasetVersion") or "")):
        errors.append("datasetVersion 格式非法")
    if not isinstance(m.get("gitCommitTimestamp"), int) or m.get("gitCommitTimestamp", 0) <= 0:
        errors.append("gitCommitTimestamp 非法")
    if not re.match(r"^[0-9a-f]{40}$", str(m.get("gitCommit") or "")):
        errors.append("gitCommit 格式非法")
    # releaseId 与目录名一致
    if root.name != m.get("releaseId"):
        errors.append(f"目录名与 releaseId 不一致: {root.name}")
    listed: dict[str, dict] = {}
    for f in m.get("files") or []:
        rel = f.get("path")
        if not isinstance(rel, str) or BAD_PATH_RE.search(rel):
            errors.append(f"files 路径非法: {rel!r}")
            continue
        if rel in listed:
            errors.append(f"files 路径重复: {rel}")
        listed[rel] = f
    actual = set()
    for p in root.rglob("*"):
        if p.is_symlink():
            errors.append(f"目录含符号链接: {p.relative_to(root)}")
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith("metadata/"):
            continue
        actual.add(rel)
    for extra in sorted(actual - set(listed)):
        errors.append(f"目录存在未列文件: {extra}")
    for missing in sorted(set(listed) - actual):
        errors.append(f"manifest 列出但缺失: {missing}")
    for rel, f in listed.items():
        p = root / rel
        if not p.exists():
            continue
        data = p.read_bytes()
        if len(data) != f.get("bytes"):
            errors.append(f"bytes 不符: {rel}")
        if hashlib.sha256(data).hexdigest() != f.get("sha256"):
            errors.append(f"sha256 不符: {rel}")
    return errors


def compare_identity(a: Path, b: Path) -> list[str]:
    ma = json.loads((a / "metadata" / "release-manifest.json").read_text())
    mb = json.loads((b / "metadata" / "release-manifest.json").read_text())
    errors = []
    if ma.get("releaseId") != mb.get("releaseId"):
        errors.append("releaseId 不一致")
    if ma.get("gitCommit") != mb.get("gitCommit"):
        errors.append("gitCommit 不一致")
    ia = {f["path"]: f["sha256"] for f in ma.get("files", []) if f.get("scope") == "content"}
    ib = {f["path"]: f["sha256"] for f in mb.get("files", []) if f.get("scope") == "content"}
    if ia != ib:
        errors.append("content 文件集不一致")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path)
    ap.add_argument("--compare-identity", nargs=2, type=Path, metavar=("A", "B"))
    args = ap.parse_args()
    if args.compare_identity:
        errs = compare_identity(*args.compare_identity)
        if errs:
            print(f"✗ 身份不一致: {'; '.join(errs)}", file=sys.stderr)
            return 1
        print("✓ 身份一致")
        return 0
    if not args.root:
        ap.error("--root 或 --compare-identity 必选")
    errs = verify(args.root)
    if errs:
        print(f"✗ 校验失败（{len(errs)} 项）:", file=sys.stderr)
        for e in errs[:10]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("✓ 校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
