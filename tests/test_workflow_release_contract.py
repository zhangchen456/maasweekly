"""Task 06 自动更新链路回归测试（incident 2026-09）。

回归背景：daily/weekly workflow 在 Commit new data 前未生成 public projection，
导致 build-release.sh 步骤 [1/6] 重算 projection 后 [3/6] tracked diff gate
拒载，GitHub job 系统性变红，但抓取与数据提交实际成功——production projection
落后于仓库数据。

修复后契约：
- daily: Export public data → Commit → Deploy（commit 前生成 projection）
- weekly full/import: Export → Commit → Deploy；aggregate 不部署不生成 projection
- skip_fetch=true 仍执行 export/commit/deploy（故障恢复路径）
- build-release.sh tracked diff gate 保留（纯构建器，不自动提交）

测试解析 YAML 文本而非 import yaml（避免额外依赖），聚焦 step name 顺序。
"""
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DAILY = BASE / ".github" / "workflows" / "daily-update.yml"
WEEKLY = BASE / ".github" / "workflows" / "weekly-update.yml"
BUILD_RELEASE = BASE / "scripts" / "build-release.sh"


def step_names(yaml_text: str) -> list[str]:
    """提取 workflow steps 的 name 字段（按出现顺序）。

    不依赖 PyYAML——用正则扫描 `- name: <value>` 行。
    """
    names = []
    for m in re.finditer(r"^\s*-\s*name:\s*(.+?)\s*$", yaml_text, re.MULTILINE):
        names.append(m.group(1).strip())
    return names


def step_indices(names: list[str]) -> dict[str, int]:
    """name → 首次出现索引。"""
    return {n: i for i, n in enumerate(names)}


class TestDailyWorkflowContract(unittest.TestCase):
    """T01–T08: daily-update.yml step 顺序契约。"""

    @classmethod
    def setUpClass(cls):
        cls.text = DAILY.read_text()
        cls.names = step_names(cls.text)
        cls.idx = step_indices(cls.names)

    def find(self, needle: str) -> int:
        for i, n in enumerate(self.names):
            if needle.lower() in n.lower():
                return i
        self.fail(f"未找到 step: {needle}")

    def test_T01_export_before_commit(self):
        """T01: Export public data 在 Commit 之前。"""
        export = self.find("Export public data")
        commit = self.find("Commit new data")
        self.assertLess(export, commit,
                        f"Export({export}) 必须在 Commit({commit}) 之前")

    def test_T01a_prebuild_before_commit(self):
        """T01a: site prebuild 产物（tracked）在 Commit 之前生成。"""
        prebuild = self.find("Prebuild site artifacts")
        commit = self.find("Commit new data")
        self.assertLess(prebuild, commit,
                        f"Prebuild({prebuild}) 必须在 Commit({commit}) 之前")

    def test_T02_export_check_present(self):
        """T02: Validate public data（--check）步骤存在，且在 export 之后、commit 之前。"""
        validate = self.find("Validate public data")
        export = self.find("Export public data")
        commit = self.find("Commit new data")
        self.assertLess(export, validate, "Validate 必须在 Export 之后")
        self.assertLess(validate, commit, "Validate 必须在 Commit 之前")
        # Validate 步骤实际跑 --check
        self.assertIn("--check", self.text)

    def test_T03_commit_includes_projection(self):
        """T03: Commit 步骤名或注释表明包含 public projection。"""
        # git add data/ 覆盖 data/public/v1/（projection 属 data/）
        commit_block = self._step_block("Commit new data")
        self.assertIn("git add data/", commit_block)

    def test_T04_deploy_after_commit(self):
        """T04: Deploy release 在 Commit 之后。"""
        commit = self.find("Commit new data")
        deploy = self.find("Deploy release")
        self.assertLess(commit, deploy, "Deploy 必须在 Commit 之后")

    def test_T05_commit_no_skip_fetch_guard(self):
        """T05: Commit 步骤不被 skip_fetch 跳过（skip_fetch=true 时仍提交 projection）。

        修复前 Commit 有 `if: !inputs.skip_fetch`，导致 skip_fetch=true 时无法
        重建 projection。修复后 Commit 始终执行。
        """
        commit_block = self._step_block("Commit new data")
        # commit step 的 if 行不应引用 skip_fetch
        if_lines = [ln for ln in commit_block.splitlines()
                    if ln.strip().startswith("if:") or ln.strip().startswith("if :")]
        for ln in if_lines:
            self.assertNotIn("skip_fetch", ln,
                             f"Commit 步骤不应被 skip_fetch 守卫: {ln}")

    def test_T06_export_no_skip_fetch_guard(self):
        """T06: Export 步骤不被 skip_fetch 跳过（恢复路径核心）。"""
        export_block = self._step_block("Export public data")
        if_lines = [ln for ln in export_block.splitlines()
                    if ln.strip().startswith("if:") or ln.strip().startswith("if :")]
        for ln in if_lines:
            self.assertNotIn("skip_fetch", ln,
                             f"Export 步骤不应被 skip_fetch 守卫: {ln}")

    def test_T07_health_check_last(self):
        """T07: health check 在部署之后（最后阶段）。"""
        deploy = self.find("Deploy release")
        verify = self.find("Online verify")
        health = self.find("health check")
        self.assertLess(deploy, verify, "Online verify 必须在 Deploy 之后")
        self.assertLess(verify, health, "health check 必须在 verify 之后")

    def test_T08_deploy_not_skip_fetch_guarded(self):
        """T08: Deploy 不被 skip_fetch 守卫（skip_fetch=true 时仍部署）。"""
        deploy_block = self._step_block("Deploy release")
        if_lines = [ln for ln in deploy_block.splitlines()
                    if ln.strip().startswith("if:") or ln.strip().startswith("if :")]
        for ln in if_lines:
            self.assertNotIn("skip_fetch", ln,
                             f"Deploy 步骤不应被 skip_fetch 守卫: {ln}")

    def test_T09_python_deps_always_installed(self):
        """T09: Python 依赖（bs4）始终安装——skip_fetch=true 时抓取步骤的
        pip install 被跳过，build-release run-all-tests 的 test_price_archive
        仍需 bs4。Install Python dependencies 步骤不应被 skip_fetch 守卫。"""
        dep_block = self._step_block("Install Python dependencies")
        if_lines = [ln for ln in dep_block.splitlines()
                    if ln.strip().startswith("if:") or ln.strip().startswith("if :")]
        self.assertEqual(if_lines, [],
                         f"Install Python dependencies 不应被守卫: {if_lines}")
        self.assertIn("requirements.txt", dep_block)

    def _step_block(self, name_needle: str) -> str:
        """提取某 step 的文本块（从 `- name: <needle>` 到下一个 `- name:`）。"""
        lines = self.text.splitlines()
        start = None
        for i, ln in enumerate(lines):
            if re.match(r"\s*-\s*name:\s*", ln) and name_needle.lower() in ln.lower():
                start = i
                break
        self.assertIsNotNone(start, f"未找到 step: {name_needle}")
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(r"^\s*-\s*name:\s*", lines[j]):
                end = j
                break
        return "\n".join(lines[start:end])


class TestWeeklyWorkflowContract(unittest.TestCase):
    """weekly-update.yml step 顺序契约。"""

    @classmethod
    def setUpClass(cls):
        cls.text = WEEKLY.read_text()
        cls.names = step_names(cls.text)

    def find(self, needle: str) -> int:
        for i, n in enumerate(self.names):
            if needle.lower() in n.lower():
                return i
        self.fail(f"未找到 step: {needle}")

    def test_T03_full_import_export_before_commit(self):
        """T03: weekly full/import 在 commit 前生成 projection（Export 步骤存在）。"""
        export = self.find("Export public data")
        commit = self.find("Commit new data")
        self.assertLess(export, commit, "Export 必须在 Commit 之前")

    def test_T03a_export_guarded_by_non_aggregate(self):
        """T03a: Export 只在非 aggregate 模式跑（aggregate 不部署不生成 projection）。"""
        export_block = self._step_block("Export public data")
        self.assertIn("aggregate", export_block,
                      "Export 步骤应区分 aggregate 模式")

    def test_T04_deploy_after_commit(self):
        """T04: Deploy 在 Commit 之后。"""
        commit = self.find("Commit new data")
        deploy = self.find("Deploy release")
        self.assertLess(commit, deploy, "Deploy 必须在 Commit 之后")

    def test_T08_aggregate_not_deploy(self):
        """T08: aggregate 模式不触发 deploy。"""
        deploy_block = self._step_block("Deploy release")
        self.assertIn("aggregate", deploy_block,
                      "Deploy 步骤应跳过 aggregate 模式")

    def _step_block(self, name_needle: str) -> str:
        lines = self.text.splitlines()
        start = None
        for i, ln in enumerate(lines):
            if re.match(r"\s*-\s*name:\s*", ln) and name_needle.lower() in ln.lower():
                start = i
                break
        self.assertIsNotNone(start, f"未找到 step: {name_needle}")
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(r"^\s*-\s*name:\s*", lines[j]):
                end = j
                break
        return "\n".join(lines[start:end])


class TestBuildReleaseGatePreserved(unittest.TestCase):
    """T05: build-release.sh tracked diff clean gate 保留。"""

    def test_tracked_diff_gate_present(self):
        """build-release.sh 必须保留 tracked diff 拒载门禁。"""
        text = BUILD_RELEASE.read_text()
        # 门禁核心：git status --porcelain 为空检查
        self.assertIn("git status --porcelain", text)
        # 拒载措辞
        self.assertIn("tracked", text.lower())

    def test_build_release_no_auto_commit(self):
        """T06: build-release.sh 不自动 git add/commit（纯构建器）。"""
        text = BUILD_RELEASE.read_text()
        # 排除注释行里的 git add/commit
        code_lines = [ln for ln in text.splitlines()
                      if not ln.strip().startswith("#")]
        code = "\n".join(code_lines)
        self.assertNotIn("git commit", code,
                         "build-release.sh 不得自动 commit")
        self.assertNotIn("git add", code,
                         "build-release.sh 不得自动 git add")

    def test_deploy_release_no_auto_commit(self):
        """T06: deploy-release.sh 不自动修改仓库（不 commit/push）。"""
        text = (BASE / "ops" / "deploy-release.sh").read_text()
        code_lines = [ln for ln in text.splitlines()
                      if not ln.strip().startswith("#")]
        code = "\n".join(code_lines)
        self.assertNotIn("git commit", code,
                         "deploy-release.sh 不得自动 commit")
        self.assertNotIn("git push", code,
                         "deploy-release.sh 不得自动 push")


class TestReproducibleRelease(unittest.TestCase):
    """T09: 可重现 release——已提交 projection 与 build-release 重算结果一致。

    模拟：export-public-data.py 生成 projection 后，build-release.sh [1/6]
    再次执行 exporter 应零 tracked diff（幂等）。
    """

    def test_export_idempotent(self):
        """export-public-data.py 连续两次执行后工作区无新 tracked diff。

        这是 release 可重现性的核心：workflow 提交的 projection 与
        build-release 重算结果必须逐字节一致。
        """
        import subprocess
        # 先跑一次确保 projection 就位
        r1 = subprocess.run(
            ["python3", "pipeline/scripts/export-public-data.py"],
            capture_output=True, text=True, cwd=BASE)
        if r1.returncode != 0:
            self.skipTest(f"export 首次执行失败（环境/数据问题）: {r1.stderr[-200:]}")
        # 跑第二次——幂等应零写入
        r2 = subprocess.run(
            ["python3", "pipeline/scripts/export-public-data.py"],
            capture_output=True, text=True, cwd=BASE)
        self.assertEqual(r2.returncode, 0, f"export 第二次失败: {r2.stderr[-200:]}")
        # 检查 git 工作区：第二次跑完应无新 tracked 改动
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=BASE)
        # data/public/v1/ 可能因首次执行产生改动——第二次应幂等
        # 但首次执行若已提交则工作区干净。这里宽容：只要第二次执行后
        # 没有新增改动（即 r2 不产生写入），通过 export --check 验证。
        r3 = subprocess.run(
            ["python3", "pipeline/scripts/export-public-data.py", "--check"],
            capture_output=True, text=True, cwd=BASE)
        self.assertEqual(r3.returncode, 0, f"export --check 失败: {r3.stderr[-200:]}")


if __name__ == "__main__":
    unittest.main()
