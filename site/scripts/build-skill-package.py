#!/usr/bin/env python3
"""build-skill-package.py：Skill 发布包构建（Task 04 M7）。

从 agent-skill/maas-daily/ 源构建 site/public/maas-skill/ 发布副本：
复制文件 + 生成 manifest.json（文件清单、bytes、SHA-256）。

可复现（T14）：manifest 不含任何墙钟字段——同输入两次构建，
manifest 与全部业务文件逐字节相同。install.sh 也复制进发布目录。

用法：
  python3 site/scripts/build-skill-package.py            # 构建到默认输出
  python3 site/scripts/build-skill-package.py --check    # 只校验现有包
  python3 site/scripts/build-skill-package.py --input <dir> --output <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = BASE / "agent-skill" / "maas-daily"
DEFAULT_OUTPUT = BASE / "site" / "public" / "maas-skill"
INSTALLER = BASE / "site" / "scripts" / "install-skill.sh"

# 发布包文件白名单（源目录里只允许这些；install.sh 单独从 scripts 来）
PACKAGED_FILES = [
    "SKILL.md", "README.md", "LICENSE", "skill-version.json",
    "references/api.md", "references/errors.md", "references/setup.md",
    "agents/openai.yaml",
]


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_manifest(input_root: Path, staged: dict[str, Path],
                   version_info: dict) -> dict:
    files = []
    for rel in sorted(staged):
        p = staged[rel]
        files.append({
            "path": rel,
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    return {
        "schemaVersion": "1.0",
        "packageVersion": version_info["packageVersion"],
        "apiVersion": version_info["apiVersion"],
        "skillName": "maas-daily",
        "files": files,
        # 说明：manifest 用于检测下载损坏，不是数字签名
        # （完整性由 HTTPS 传输与站点发布链路保证）
        "note": "integrity checksums for download verification; not a digital signature",
    }


def build(input_root: Path, output_root: Path) -> int:
    # 源校验
    version_file = input_root / "skill-version.json"
    if not version_file.exists():
        print(f"✗ 缺 skill-version.json: {version_file}", file=sys.stderr)
        return 1
    version_info = json.loads(version_file.read_text(encoding="utf-8"))
    src_files = {str(p.relative_to(input_root))
                 for p in input_root.rglob("*") if p.is_file()}
    unknown = src_files - set(PACKAGED_FILES)
    if unknown:
        print(f"✗ 源目录含白名单外文件（需先更新 PACKAGED_FILES）: "
              f"{sorted(unknown)}", file=sys.stderr)
        return 1
    missing = set(PACKAGED_FILES) - src_files
    if missing:
        print(f"✗ 缺发布文件: {sorted(missing)}", file=sys.stderr)
        return 1

    # 输出重建（白名单路径内）
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    staged: dict[str, Path] = {}
    for rel in PACKAGED_FILES:
        dst = output_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(input_root / rel, dst)
        staged[rel] = dst
    # install.sh 复制（可执行）
    if not INSTALLER.exists():
        print(f"✗ 缺安装器: {INSTALLER}", file=sys.stderr)
        return 1
    shutil.copyfile(INSTALLER, output_root / "install.sh")
    (output_root / "install.sh").chmod(0o755)

    manifest = build_manifest(input_root, staged, version_info)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"✓ Skill 包构建: {output_root}（{len(manifest['files'])} 文件 + "
          f"install.sh，包版本 {manifest['packageVersion']}）")
    return 0


def check(output_root: Path) -> int:
    """校验现有包：manifest 结构 + 每文件 bytes/hash + 源漂移检测。"""
    mf = output_root / "manifest.json"
    if not mf.exists():
        print(f"✗ manifest 不存在: {mf}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ manifest 损坏: {e}", file=sys.stderr)
        return 1
    errors = []
    # manifest 自身不列入 files（与 export-public-data 语义一致）
    listed = {f["path"] for f in manifest.get("files") or []}
    for f in manifest.get("files") or []:
        p = output_root / f["path"]
        if not p.exists():
            errors.append(f"缺文件: {f['path']}")
            continue
        if p.stat().st_size != f["bytes"]:
            errors.append(f"bytes 不符: {f['path']}")
        if sha256_file(p) != f["sha256"]:
            errors.append(f"sha256 不符: {f['path']}")
    # 发布目录实际文件 = manifest 列表 + manifest.json + install.sh
    actual = {str(p.relative_to(output_root))
              for p in output_root.rglob("*") if p.is_file()}
    extra = actual - listed - {"manifest.json", "install.sh"}
    if extra:
        errors.append(f"多余文件: {sorted(extra)}")
    if not (output_root / "install.sh").exists():
        errors.append("缺 install.sh")
    # 源漂移检测（门禁）：源文件变化而包未重建 → 报错
    src = BASE / "agent-skill" / "maas-daily"
    for rel in sorted(listed):
        src_p = src / rel
        if not src_p.exists():
            errors.append(f"源缺文件（包未清理）: {rel}")
        elif sha256_file(src_p) != sha256_file(output_root / rel):
            errors.append(f"源已变化但发布包未重建: {rel}（重跑 build-skill-package.py）")
    if errors:
        print(f"✗ Skill 包校验失败（{len(errors)} 项）:", file=sys.stderr)
        for e in errors[:10]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"✓ Skill 包校验通过：{manifest['packageVersion']} · "
          f"{len(listed)} 文件 + install.sh")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="只校验现有包，零写入")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    if args.check:
        return check(args.output)
    return build(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
