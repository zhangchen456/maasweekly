"""Task 06 release builder 测试（T01–T03，不跑全量构建）。

- T01：同 fixture 两次 manifest build → content 身份全等；无本机路径
- T02：路径逃逸/重复/未列文件/篡改/symlink → verify 拒
- T03：脏树/HEAD 不符/未知 commit → build-release.sh --preflight-only 拒
（T03 在临时 git fixture 里跑真实脚本。）
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "pipeline" / "scripts"))
import release_manifest as rm  # noqa: E402

SCRIPT = BASE / "scripts" / "build-release.sh"


def make_release_tree(root: Path) -> dict:
    """最小合法 release 树（site/data/agent-api）。"""
    (root / "site" / "agent").mkdir(parents=True)
    (root / "site" / "_astro").mkdir(parents=True)
    (root / "site" / "index.html").write_text("<html>ok</html>")
    (root / "site" / "agent" / "index.html").write_text("<html>agent</html>")
    (root / "site" / "_astro" / "a.js").write_text("console.log(1)")
    (root / "data").mkdir()
    ds = "ds_" + "a" * 64
    (root / "data" / "manifest.json").write_text(json.dumps({
        "schemaVersion": "1.0", "datasetVersion": ds,
        "dataThrough": "2026-09-16", "coverage": {}, "files": [],
    }))
    (root / "data" / "releases" / ds).mkdir(parents=True)
    (root / "data" / "releases" / ds / "status.json").write_text("[]")
    (root / "agent-api").mkdir()
    (root / "agent-api" / "dist").mkdir()
    (root / "agent-api" / "dist" / "server.js").write_text("// stub")
    (root / "agent-api" / "package.json").write_text('{"name":"x"}')
    (root / "agent-api" / "node_modules" / "pkg").mkdir(parents=True)
    (root / "agent-api" / "node_modules" / "pkg" / "index.js").write_text("// pkg")
    return {"ds": ds}


def build(root: Path) -> dict:
    return rm.build_manifest(
        root, rid="rl_" + "a" * 10 + "_" + "b" * 12,
        git_commit="c" * 40, git_ts=1789000000,
        dataset_version="ds_" + "a" * 64, data_through="2026-09-16",
        built_at="2026-09-17T00:00:00Z")


class TestT01Deterministic(unittest.TestCase):
    """T01：同输入两次构建 → content 身份一致。"""

    def test_two_builds_identical(self):
        d1 = Path(tempfile.mkdtemp(prefix="t06-a-"))
        d2 = Path(tempfile.mkdtemp(prefix="t06-b-"))
        try:
            make_release_tree(d1)
            make_release_tree(d2)
            m1 = build(d1)
            m2 = build(d2)
            self.assertEqual(m1["releaseId"], m2["releaseId"])
            # content-scope hash 集合全等
            c1 = {f["path"]: f["sha256"] for f in m1["files"] if f["scope"] == "content"}
            c2 = {f["path"]: f["sha256"] for f in m2["files"] if f["scope"] == "content"}
            self.assertEqual(c1, c2)
            # manifest 无本机路径
            blob = json.dumps(m1)
            self.assertNotIn(str(d1), blob)
            self.assertNotIn("/Users/", blob)
            self.assertNotIn("/tmp/", blob)
            # node_modules 是 runtime scope
            nm = [f for f in m1["files"] if f["path"].startswith("agent-api/node_modules")]
            self.assertTrue(nm and all(f["scope"] == "runtime" for f in nm))
        finally:
            shutil.rmtree(d1, ignore_errors=True)
            shutil.rmtree(d2, ignore_errors=True)

    def test_rid_format(self):
        # 非法 RID（shell 元字符/长度不符）被拒
        d = Path(tempfile.mkdtemp(prefix="t06-r-"))
        try:
            make_release_tree(d)
            for bad in ["rl_$(evil)_abc", "rl_EVIL_evil12345678", "../x",
                        "rl_aaaaaaaaaa_bbbbbbbbbbbb;ls", ""]:
                with self.assertRaises(rm.ManifestError, msg=bad):
                    rm.build_manifest(d, rid=bad, git_commit="c" * 40,
                                      git_ts=1, dataset_version="ds_" + "a" * 64,
                                      data_through="x", built_at="x")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestT02VerifyRejects(unittest.TestCase):
    """T02：manifest/目录违规 → verify 拒。"""

    def _mk(self):
        d = Path(tempfile.mkdtemp(prefix="t06-v-"))
        make_release_tree(d)
        m = build(d)
        # 落盘 manifest（verify 从文件读）
        meta = d / "metadata"
        meta.mkdir(exist_ok=True)
        (meta / "release-manifest.json").write_text(json.dumps(m))
        return d, m

    def _errs(self, d):
        return rm.verify_manifest(d)

    def test_clean_passes(self):
        d, _ = self._mk()
        try:
            self.assertEqual(self._errs(d), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_unlisted_file_rejected(self):
        d, _ = self._mk()
        try:
            (d / "site" / "rogue.html").write_text("x")
            errs = self._errs(d)
            self.assertTrue(any("未列文件" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_missing_file_rejected(self):
        d, _ = self._mk()
        try:
            (d / "site" / "_astro" / "a.js").unlink()
            errs = self._errs(d)
            self.assertTrue(any("列出但缺失" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_tampered_content_rejected(self):
        d, _ = self._mk()
        try:
            (d / "site" / "index.html").write_text("TAMPERED")
            errs = self._errs(d)
            self.assertTrue(any("sha256 不符" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_symlink_rejected(self):
        d, _ = self._mk()
        try:
            (d / "site" / "evil.js").symlink_to("/etc/passwd")
            errs = self._errs(d)
            self.assertTrue(any("符号链接" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_path_escape_in_manifest_rejected(self):
        d, m = self._mk()
        try:
            m["files"].append({"path": "../escape.txt", "bytes": 1,
                               "sha256": "0" * 64, "scope": "content"})
            (d / "metadata" / "release-manifest.json").write_text(json.dumps(m))
            errs = self._errs(d)
            self.assertTrue(any("路径非法" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_duplicate_entries_rejected(self):
        d, m = self._mk()
        try:
            m["files"].append(dict(m["files"][0]))
            (d / "metadata" / "release-manifest.json").write_text(json.dumps(m))
            errs = self._errs(d)
            self.assertTrue(any("重复" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_bad_git_ts_rejected(self):
        d, m = self._mk()
        try:
            m["gitCommitTimestamp"] = "not-int"
            (d / "metadata" / "release-manifest.json").write_text(json.dumps(m))
            errs = self._errs(d)
            self.assertTrue(any("gitCommitTimestamp" in e for e in errs))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestT03Preflight(unittest.TestCase):
    """T03：build-release.sh --preflight-only 的拒绝分支（真实脚本 + 临时 git repo）。"""

    def _repo(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="t06-p-"))
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        (d / "file.txt").write_text("x")
        subprocess.run(["git", "-C", str(d), "add", "."], check=True)
        subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", "init",
                        "--author=test <t@t>", "--date=2026-09-17T00:00:00"],
                       check=True, env={"GIT_AUTHOR_NAME": "t",
                                        "GIT_COMMITTER_NAME": "t",
                                        "PATH": "/usr/bin:/bin:/usr/local/bin"})
        return d

    def test_preflight_clean_tree(self):
        d = self._repo()
        try:
            r = subprocess.run(["bash", str(SCRIPT), "--preflight-only"],
                               capture_output=True, text=True, cwd=d,
                               env={**__import__("os").environ,
                                    "MAAS_RELEASE_REPO": str(d)})
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_preflight_dirty_tree_rejected(self):
        d = self._repo()
        try:
            (d / "uncommitted.txt").write_text("x")
            r = subprocess.run(["bash", str(SCRIPT), "--preflight-only"],
                               capture_output=True, text=True, cwd=d,
                               env={**__import__("os").environ,
                                    "MAAS_RELEASE_REPO": str(d)})
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("工作区脏", r.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_preflight_unknown_commit_rejected(self):
        d = self._repo()
        try:
            r = subprocess.run(
                ["bash", str(SCRIPT), "--preflight-only", "--commit", "deadbeef"],
                capture_output=True, text=True, cwd=d)
            self.assertNotEqual(r.returncode, 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
