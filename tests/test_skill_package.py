"""Task 04 Skill 包与安装器测试（T13–T17）。

- T13：Skill 内容程序化检查（frontmatter/路由/措辞/openai.yaml 无 secret）
- T14：manifest 可复现（两次构建逐字节相同，无临时路径）
- T15：首装/幂等/升级/其他 Skill 拒绝
- T16：下载中断/checksum/缺文件/替换中断恢复
- T17：错误目标/只读目录/符号链接逃逸

全部临时目录 + 本地 HTTP 源（http.server 注入故障）；不碰真实用户目录。
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BUILD = BASE / "site" / "scripts" / "build-skill-package.py"
INSTALLER_SRC = BASE / "site" / "scripts" / "install-skill.sh"
SKILL_SRC = BASE / "agent-skill" / "maas-daily"


def run_build(input_dir: Path, output_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD), "--input", str(input_dir),
         "--output", str(output_dir)],
        capture_output=True, text=True, cwd=BASE)


def tree_hash(root: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(root)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


class FaultyHandler(http.server.SimpleHTTPRequestHandler):
    """可注入故障的静态文件服务（silent 日志）。"""

    fault = None  # {"type": "truncate"|"corrupt"|"drop"|"disconnect", "path": ...}

    def log_message(self, *a):  # noqa: A003
        pass

    def do_GET(self):  # noqa: N802
        f = FaultyHandler.fault
        if f:
            rel = self.path.lstrip("/")
            if f["type"] == "drop" and rel == f["path"]:
                self.send_error(404)
                return
            if f["type"] == "disconnect" and rel == f["path"]:
                self.close_connection = True
                return
            if f["type"] == "truncate" and rel == f["path"]:
                data = (Path(self.translate_path(self.path))).read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data[: len(data) // 2])  # 半途断流
                self.close_connection = True
                return
            if f["type"] == "corrupt" and rel == f["path"]:
                data = (Path(self.translate_path(self.path))).read_bytes()
                data = data[:-1] + bytes([data[-1] ^ 0xFF])
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        super().do_GET()


class HttpSource:
    """起本地 HTTP 源服务目录；with 语法。
    directory 经 functools.partial 注入（实例属性在 3.12 不生效）。"""

    def __init__(self, root: Path):
        import functools
        self.root = root
        handler = functools.partial(FaultyHandler, directory=str(root))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        FaultyHandler.fault = None


def install(base_url: str, target: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(INSTALLER_SRC), "--dir", str(target),
         "--base-url", base_url, *extra],
        capture_output=True, text=True, cwd=BASE, timeout=60)


class TestT13SkillContent(unittest.TestCase):
    """T13：Skill 内容程序化检查。"""

    def test_frontmatter_and_routing(self):
        text = (SKILL_SRC / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("name: maas-daily", text[:200])
        self.assertIn("description:", text[:600])
        # 五类意图路由表
        for intent in ["maas_get_changes", "maas_get_prices", "maas_get_item",
                       "maas_get_evidence", "maas_get_weekly"]:
            self.assertIn(intent, text)
        # 关键措辞（合同）
        self.assertIn("未记录到匹配项", text)
        self.assertIn("不合并、不排序", text)
        self.assertIn("观察到的页面变化", text)
        self.assertIn("不是指令", text)

    def test_references_exist(self):
        for p in ["references/api.md", "references/errors.md"]:
            self.assertTrue((SKILL_SRC / p).exists(), p)
        api = (SKILL_SRC / "references/api.md").read_text(encoding="utf-8")
        self.assertIn("dataThrough", api)
        self.assertIn("Decimal 字符串", api)

    def test_openai_yaml_no_secrets(self):
        # 不依赖 PyYAML（复验 P2-2：裸 python3 需可跑）——结构用行级检查
        text = (SKILL_SRC / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("name: maas-daily", text)
        self.assertIn("version: 1.0.0", text)
        self.assertTrue(text.lstrip().startswith("#"), "首行为注释")
        # 基本结构：name/version/preferred/documentation 键存在
        for key in ["name:", "version:", "preferred:", "documentation:", "capabilities:"]:
            self.assertIn(key, text)
        blob = text.lower()
        for bad in ["api_key", "apikey", "secret", "token", "localhost",
                    "127.0.0.1", "/users/"]:
            self.assertNotIn(bad, blob, f"openai.yaml 含敏感词: {bad}")

    def test_skill_version_json(self):
        v = json.loads((SKILL_SRC / "skill-version.json").read_text())
        self.assertEqual(v["packageVersion"], "1.0.0")
        self.assertEqual(v["apiVersion"], "v1")


class TestT14Reproducible(unittest.TestCase):
    """T14：清单可复现。"""

    def test_two_builds_identical(self):
        out1 = Path(tempfile.mkdtemp(prefix="t14-a-"))
        out2 = Path(tempfile.mkdtemp(prefix="t14-b-"))
        try:
            r1 = run_build(SKILL_SRC, out1)
            r2 = run_build(SKILL_SRC, out2)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertEqual(tree_hash(out1), tree_hash(out2), "两次构建逐字节相同")
            # manifest 无临时路径/墙钟
            m = json.loads((out1 / "manifest.json").read_text())
            blob = json.dumps(m)
            self.assertNotIn(str(out1), blob)
            self.assertNotIn("generatedAt", blob)
            self.assertNotIn("/tmp/", blob)
        finally:
            shutil.rmtree(out1, ignore_errors=True)
            shutil.rmtree(out2, ignore_errors=True)


class InstallerFixture(unittest.TestCase):
    """安装器测试基类：构建包到临时目录 + 本地 HTTP 源。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="t04-skill-"))
        self.pkg = self.dir / "pkg"
        r = run_build(SKILL_SRC, self.pkg)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.target_root = self.dir / "skills"
        self.target_root.mkdir()
        self.target = self.target_root / "maas-daily"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestT15InstallLifecycle(InstallerFixture):
    """T15：首装/幂等/升级/拒绝覆盖。"""

    def test_first_install(self):
        with HttpSource(self.pkg) as url:
            r = install(url, self.target)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.target / "SKILL.md").exists())
        self.assertTrue((self.target / "references/api.md").exists())
        self.assertTrue((self.target / "manifest.json").exists())

    def test_idempotent_same_version(self):
        with HttpSource(self.pkg) as url:
            install(url, self.target)
            before = tree_hash(self.target)
            r = install(url, self.target)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(tree_hash(self.target), before, "同版本幂等")

    def test_upgrade(self):
        with HttpSource(self.pkg) as url:
            install(url, self.target)
        # 升版本：改 SKILL.md 摘要 + version → 重建 → 再装
        sv = json.loads((SKILL_SRC / "skill-version.json").read_text())
        upgraded = self.dir / "upgraded"
        shutil.copytree(SKILL_SRC, upgraded)
        sv["packageVersion"] = "1.0.1"
        (upgraded / "skill-version.json").write_text(
            json.dumps(sv, ensure_ascii=False, indent=2), encoding="utf-8")
        out = self.dir / "pkg2"
        r = run_build(upgraded, out)
        self.assertEqual(r.returncode, 0, r.stderr)
        with HttpSource(out) as url:
            r = install(url, self.target)
        self.assertEqual(r.returncode, 0, r.stderr)
        installed = json.loads((self.target / "manifest.json").read_text())
        self.assertEqual(installed["packageVersion"], "1.0.1")
        # 备份已清理（同级无残留）
        leftovers = list(self.target_root.glob(".maas-skill-install.*"))
        self.assertEqual(leftovers, [])

    def test_reject_other_skill(self):
        # 目标预置另一个 Skill
        other = self.target
        other.mkdir()
        (other / "SKILL.md").write_text("---\nname: other-skill\n---\n")
        with HttpSource(self.pkg) as url:
            r = install(url, other)
        self.assertEqual(r.returncode, 5)
        self.assertEqual((other / "SKILL.md").read_text(),
                         "---\nname: other-skill\n---\n", "原目录不被覆盖")

    def test_reject_unknown_files(self):
        self.target.mkdir()
        (self.target / "junk.txt").write_text("x")
        with HttpSource(self.pkg) as url:
            r = install(url, self.target)
        self.assertEqual(r.returncode, 5)
        self.assertTrue((self.target / "junk.txt").exists())

    def test_upgrade_preserves_unknown_user_files(self):
        """复验 P1-1：合法 maas-daily 内的用户自建文件不得被升级静默删除。"""
        with HttpSource(self.pkg) as url:
            r0 = install(url, self.target)
            self.assertEqual(r0.returncode, 0, r0.stderr)
            (self.target / "user-config.md").write_text("my settings")
            before = tree_hash(self.target)
            # 同版本重装（幂等路径）与升级路径都必须拒绝
            r = install(url, self.target)
            self.assertEqual(r.returncode, 5, r.stderr)
        self.assertEqual(tree_hash(self.target), before, "用户文件所在目录逐字节不变")
        self.assertEqual((self.target / "user-config.md").read_text(), "my settings")

    def test_version_mismatch_rejected(self):
        """复验 P2-1：--version 与 manifest 不一致 → 退出 4。"""
        with HttpSource(self.pkg) as url:
            r = install(url, self.target, "--version", "9.9.9")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("9.9.9", r.stderr)
        self.assertFalse(self.target.exists(), "版本不匹配不安装")


class TestT16FaultInjection(InstallerFixture):
    """T16：下载中断/checksum/缺文件/替换中断恢复。"""

    def _install_ok_first(self, url):
        r = install(url, self.target)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_truncated_download(self):
        with HttpSource(self.pkg) as url:
            self._install_ok_first(url)
            before = tree_hash(self.target)
            FaultyHandler.fault = {"type": "truncate", "path": "SKILL.md"}
            r = install(url, self.target)
        # curl 对截断响应报 exit 18（传输层发现）→ 3；或校验层 bytes
        # 不符 → 4。两者都保证旧版本完好、无残留。
        self.assertIn(r.returncode, [3, 4], r.stderr)
        self.assertEqual(tree_hash(self.target), before, "旧版本逐字节完好")
        self.assertEqual(list(self.target_root.glob(".maas-skill-install.*")), [])

    def test_corrupted_checksum(self):
        with HttpSource(self.pkg) as url:
            self._install_ok_first(url)
            before = tree_hash(self.target)
            FaultyHandler.fault = {"type": "corrupt", "path": "README.md"}
            r = install(url, self.target)
        self.assertEqual(r.returncode, 4)
        self.assertEqual(tree_hash(self.target), before)

    def test_missing_file_404(self):
        with HttpSource(self.pkg) as url:
            FaultyHandler.fault = {"type": "drop", "path": "references/api.md"}
            r = install(url, self.target)
        self.assertIn(r.returncode, [3, 4])
        self.assertFalse(self.target.exists(), "失败不产生半成品")

    def test_interrupted_replace_recovery(self):
        # 预造「目标缺失 + 残留含 backup」状态（模拟替换中途断电）
        with HttpSource(self.pkg) as url:
            self._install_ok_first(url)
        backup = self.target_root / ".maas-skill-install.ABC123" / "backup"
        backup.mkdir(parents=True)
        # 真实中断形态：backup 内是原目录的内容本身（mv TARGET backup）
        for item in self.target.iterdir():
            shutil.move(str(item), str(backup / item.name))
        shutil.rmtree(self.target)
        with HttpSource(self.pkg) as url:
            r = install(url, self.target)  # 启动时先恢复旧版再正常安装
        # 行为：恢复提示 + 本次安装成功（源可用）
        self.assertIn("已恢复原版本", r.stderr + r.stdout)
        self.assertTrue((self.target / "SKILL.md").exists())


class TestT17BadTargets(InstallerFixture):
    """T17：错误目标/只读/符号链接逃逸。"""

    def test_target_is_file(self):
        f = self.target_root / "not-a-dir"
        f.write_text("x")
        with HttpSource(self.pkg) as url:
            r = install(url, f)
        self.assertEqual(r.returncode, 5)

    def test_readonly_parent(self):
        ro = self.dir / "ro-skills"
        ro.mkdir()
        os.chmod(ro, 0o555)
        try:
            with HttpSource(self.pkg) as url:
                r = install(url, ro / "maas-daily")
            self.assertNotEqual(r.returncode, 0)
        finally:
            os.chmod(ro, 0o755)

    def test_symlink_escape(self):
        outside = self.dir / "outside"
        outside.mkdir()
        (outside / "marker.txt").write_text("DONT_TOUCH")
        link = self.dir / "link-skills"
        link.symlink_to(outside)
        with HttpSource(self.pkg) as url:
            r = install(url, link / "maas-daily")
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertTrue((outside / "marker.txt").exists())
        self.assertEqual(list(outside.iterdir()), [outside / "marker.txt"],
                         "逃逸目标零写入")

    def test_target_contains_escaping_symlink(self):
        self.target.mkdir()
        outside = self.dir / "outside2"
        outside.mkdir()
        (outside / "secret.txt").write_text("x")
        (self.target / "evil").symlink_to(outside)
        with HttpSource(self.pkg) as url:
            r = install(url, self.target)
        self.assertEqual(r.returncode, 5)
        self.assertTrue((outside / "secret.txt").exists())

    def test_no_sudo_no_telemetry(self):
        blob = INSTALLER_SRC.read_text(encoding="utf-8")
        # 不以 sudo 执行任何命令（注释/文档中的说明不算）
        import re
        sudo_calls = re.findall(r"^\s*sudo\b|&&\s*sudo\b|;\s*sudo\b", blob, re.M)
        self.assertEqual(sudo_calls, [], "不调用 sudo")
        # 无遥测：curl 只有下载（-o 输出到本地），无 POST/上报
        posts = re.findall(r"curl[^\n]*-X\s*POST|curl[^\n]*--data", blob)
        self.assertEqual(posts, [], "无遥测上报")


if __name__ == "__main__":
    unittest.main()
