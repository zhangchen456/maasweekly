#!/usr/bin/env python3
"""release_manifest.py：生产 release manifest 构建/校验/比对（Task 06 M3）。

被 scripts/build-release.sh（bash 编排）调用，也是 tests/test_release_build.py
的直接被测对象。全部校验规则集中于此——服务器激活脚本复用 verify（同一逻辑）。

用法：
  build   --root <dir> --rid <id> --git-commit <sha> --git-ts <epoch>
          [--dataset-version <ds>] [--built-at <iso>]
  verify  [--root <dir>] [--manifest <file>]  # 全量：schema+路径+双向集合+hash
  compare --a <manifest> --b <manifest>       # T01：content-scope 身份比对

scope 语义（D3 确定性双层）：
- content：site/ + data/ + agent-api/{dist,package.json,package-lock.json}——
  参与身份比对（T01 同 commit 重复构建必须全等）
- runtime：agent-api/node_modules/——完整性校验（T02）但不参与身份比对
  （lockfile integrity 锁定包内容，非内容差异由 scope 隔离）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "production-release-v1"
RID_RE = re.compile(r"^rl_[0-9a-f]{10}_[0-9a-f]{12}$")
DS_RE = re.compile(r"^ds_[0-9a-f]{64}$")
# 路径规则：相对、无 ../ ./ 前导/、无双斜杠、无控制字符、非目录形式结尾
BAD_PATH_RE = re.compile(r"(^\.\./|/\.\./|^\./|/\./|//|^/|[\x00-\x1f]|/$)")

CONTENT_PREFIXES = ("site/", "data/")
RUNTIME_PREFIXES = ("agent-api/node_modules/",)


class ManifestError(Exception):
    """manifest 构建/校验失败（错误信息只含相对路径与规则名）。"""


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _scope_of(rel: str) -> str:
    if rel.startswith(RUNTIME_PREFIXES):
        return "runtime"
    return "content"


def build_manifest(root: Path, *, rid: str, git_commit: str, git_ts: int,
                   dataset_version: str, data_through: str,
                   built_at: str, tests_skipped: bool = False) -> dict:
    """遍历 release 目录生成 manifest。非法路径/symlink → 抛错。"""
    if not RID_RE.match(rid):
        raise ManifestError(f"release ID 格式非法: {rid}")
    files = []
    seen = set()
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            # npm .bin 符号链接是合法运行时结构——记录目标（必须是包内
            # 相对路径，禁止逃逸），不参与 hash（链接内容由目标文件保证）
            rel = p.relative_to(root).as_posix()
            if rel.startswith("agent-api/node_modules/.bin/"):
                # npm .bin 链接目标是包内相对路径（../<pkg>/...）——resolve 后
                # 必须仍在 node_modules 内（绝对路径目标同样按 resolve 判定）
                target = os.path.realpath(p)
                if "/node_modules/" not in target or \
                        not target.startswith(str(root)):
                    raise ManifestError(f"npm bin 链接逃逸: {rel}")
                continue
            raise ManifestError(f"release 含符号链接: {rel}")
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        # metadata/ 是 manifest 自身的产物（verify 排除，不属发布内容）
        if rel.startswith("metadata/"):
            continue
        if BAD_PATH_RE.search(rel):
            raise ManifestError(f"路径非法: {rel}")
        if rel in seen:
            raise ManifestError(f"路径重复: {rel}")
        seen.add(rel)
        files.append({
            "path": rel,
            "bytes": p.stat().st_size,
            "sha256": _sha256(p),
            "scope": _scope_of(rel),
        })
    # contracts 从产物读取（不手写）
    contracts = _read_contracts(root)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "releaseId": rid,
        "gitCommit": git_commit,
        "gitCommitTimestamp": git_ts,
        "datasetVersion": dataset_version,
        "dataThrough": data_through,
        "builtAt": built_at,
        "testsSkipped": tests_skipped,  # true = 开发调试产物，禁止激活
        "identityScope": "content",
        "tools": _read_tool_versions(),
        "contracts": contracts,
        "files": files,
        "totals": {
            "files": len(files),
            "bytes": sum(f["bytes"] for f in files),
        },
    }


def _read_contracts(root: Path) -> dict:
    """合同版本从产物读取：OpenAPI/skill 包/公开数据 schema。"""
    contracts = {}
    openapi = root / "site" / "openapi-v1.json"
    if openapi.exists():
        try:
            contracts["rest"] = json.loads(openapi.read_text())["info"]["version"]
        except (json.JSONDecodeError, KeyError):
            pass
    skill = root / "site" / "maas-skill" / "manifest.json"
    if skill.exists():
        try:
            contracts["skill"] = json.loads(skill.read_text())["packageVersion"]
        except (json.JSONDecodeError, KeyError):
            pass
    dm = root / "data" / "manifest.json"
    if dm.exists():
        try:
            contracts["publicData"] = json.loads(dm.read_text())["schemaVersion"]
        except (json.JSONDecodeError, KeyError):
            pass
    return contracts


def _read_tool_versions() -> dict:
    import platform
    return {"python": platform.python_version()}


def verify_manifest(root: Path | None = None,
                    manifest_path: Path | None = None) -> list[str]:
    """全量校验（激活前/离线验证共用）。返回错误清单（空=通过）。

    校验：schema 字段类型与格式、release ID/datasetVersion 格式、
    路径规则（非法/重复）、目录实际文件集与 files 双向恰等（防未列文件
    与列了缺失）、逐文件 bytes+sha256 复算、symlink 拒绝。
    """
    if manifest_path is None:
        manifest_path = (root or Path(".")) / "metadata" / "release-manifest.json"
    if not manifest_path.exists():
        return [f"manifest 不存在: {manifest_path.name}"]
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"manifest 损坏: {e}"]
    errors: list[str] = []

    if m.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion 非法: {m.get('schemaVersion')!r}")
    rid = m.get("releaseId")
    if not isinstance(rid, str) or not RID_RE.match(rid):
        errors.append(f"releaseId 格式非法: {rid!r}")
    if not DS_RE.match(str(m.get("datasetVersion") or "")):
        errors.append("datasetVersion 格式非法")
    if not isinstance(m.get("gitCommitTimestamp"), int) or m.get("gitCommitTimestamp", 0) <= 0:
        errors.append("gitCommitTimestamp 非法（旧提交拒绝的排序键）")
    if not re.match(r"^[0-9a-f]{40}$", str(m.get("gitCommit") or "")):
        errors.append("gitCommit 格式非法")

    files = m.get("files") or []
    listed: dict[str, dict] = {}
    for f in files:
        rel = f.get("path")
        if not isinstance(rel, str) or BAD_PATH_RE.search(rel):
            errors.append(f"files 路径非法: {rel!r}")
            continue
        if rel in listed:
            errors.append(f"files 路径重复: {rel}")
            continue
        if f.get("scope") not in ("content", "runtime"):
            errors.append(f"files scope 非法: {rel}")
        listed[rel] = f

    if root is not None and root.exists():
        # 双向集合恰等 + symlink + hash 复算
        actual = set()
        for p in root.rglob("*"):
            if p.is_symlink():
                errors.append(f"目录含符号链接: {p.relative_to(root)}")
                continue
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if rel.startswith("metadata/"):
                continue  # manifest 自身产物，不属发布内容
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


def compare_identity(a_path: Path, b_path: Path) -> list[str]:
    """T01：两个 manifest 的 content-scope 文件身份比对（空=一致）。"""
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())
    errors = []
    if a.get("releaseId") != b.get("releaseId"):
        errors.append(f"releaseId 不一致: {a.get('releaseId')} vs {b.get('releaseId')}")
    if a.get("gitCommit") != b.get("gitCommit"):
        errors.append("gitCommit 不一致")
    if a.get("datasetVersion") != b.get("datasetVersion"):
        errors.append("datasetVersion 不一致")
    ia = {f["path"]: f["sha256"] for f in a.get("files", []) if f.get("scope") == "content"}
    ib = {f["path"]: f["sha256"] for f in b.get("files", []) if f.get("scope") == "content"}
    for k in sorted(set(ia) - set(ib)):
        errors.append(f"仅 A 有: {k}")
    for k in sorted(set(ib) - set(ia)):
        errors.append(f"仅 B 有: {k}")
    for k in sorted(set(ia) & set(ib)):
        if ia[k] != ib[k]:
            errors.append(f"hash 不一致: {k}")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--root", type=Path, required=True)
    b.add_argument("--rid", required=True)
    b.add_argument("--git-commit", required=True)
    b.add_argument("--git-ts", type=int, required=True)
    b.add_argument("--dataset-version", required=True)
    b.add_argument("--data-through", required=True)
    b.add_argument("--built-at", required=True)
    b.add_argument("--skip-tests-marked", action="store_true",
                   help="标记开发调试 release（testsSkipped=true，激活器拒绝）")

    v = sub.add_parser("verify")
    v.add_argument("--root", type=Path, required=True)

    c = sub.add_parser("compare")
    c.add_argument("--a", type=Path, required=True)
    c.add_argument("--b", type=Path, required=True)

    args = ap.parse_args(argv)
    try:
        if args.cmd == "build":
            m = build_manifest(
                args.root, rid=args.rid, git_commit=args.git_commit,
                git_ts=args.git_ts, dataset_version=args.dataset_version,
                data_through=args.data_through, built_at=args.built_at,
                tests_skipped=args.skip_tests_marked)
            meta = args.root / "metadata"
            meta.mkdir(exist_ok=True)
            (meta / "release-manifest.json").write_text(
                json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # checksums.sha256：全部文件（含 runtime，完整性清单）
            lines = [f"{f['sha256']}  {f['path']}" for f in m["files"]]
            (meta / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
            # versions.json：人读汇总
            (meta / "versions.json").write_text(
                json.dumps({k: m[k] for k in
                            ("releaseId", "gitCommit", "gitCommitTimestamp",
                             "datasetVersion", "dataThrough", "contracts", "builtAt")},
                           ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"✓ manifest: {m['releaseId']}（{m['totals']['files']} 文件，"
                  f"{m['totals']['bytes']} 字节）")
            return 0
        if args.cmd == "verify":
            errs = verify_manifest(args.root)
            if errs:
                print(f"✗ release 校验失败（{len(errs)} 项）:", file=sys.stderr)
                for e in errs[:10]:
                    print(f"  - {e}", file=sys.stderr)
                return 1
            print("✓ release 校验通过")
            return 0
        if args.cmd == "compare":
            errs = compare_identity(args.a, args.b)
            if errs:
                print(f"✗ 身份不一致（{len(errs)} 项）:", file=sys.stderr)
                for e in errs[:10]:
                    print(f"  - {e}", file=sys.stderr)
                return 1
            print("✓ content 身份一致")
            return 0
    except ManifestError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
