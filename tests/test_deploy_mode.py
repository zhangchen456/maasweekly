"""Task 06 M7 P0：deploy-mode 运行时覆盖测试。

回归背景：原实现只读 tracked 文件 ops/deploy-mode——切换通道需修改该文件，
污染 clean worktree，build-release.sh preflight（git status --porcelain 必须为空）
会拒绝生产构建；且存在"忘记改回"风险。

修复后优先级：MAAS_DEPLOY_MODE 环境变量 > ops/deploy-mode 文件 > 默认 legacy。
仓库文件永久保持 legacy。
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LIB = BASE / "ops" / "lib-release.sh"


def run_deploy_mode(env_extra: dict[str, str] | None = None,
                   ops_file_content: str | None = None) -> tuple[int, str]:
    """在受控环境里 source lib-release.sh 并执行 deploy_mode。

    ops_file_content=None → 测试目录里没有 ops/deploy-mode（模拟文件缺失）。
    """
    with tempfile.TemporaryDirectory(prefix="t06-mode-") as td:
        td = Path(td)
        if ops_file_content is not None:
            (td / "deploy-mode").write_text(ops_file_content)
        # lib-release.sh 用 BASH_SOURCE 定位 OPS_DIR——复制一份到临时 ops/
        ops_dir = td / "ops"
        ops_dir.mkdir()
        lib = ops_dir / "lib-release.sh"
        # 只保留 deploy_mode 相关定义（避免 known_hosts 等无关 die 路径）
        lib.write_text(LIB.read_text())
        if ops_file_content is not None:
            (ops_dir / "deploy-mode").write_text(ops_file_content)
        env = {**os.environ, **(env_extra or {})}
        env.pop("MAAS_DEPLOY_MODE", None) if env_extra is None else None
        if env_extra is None:
            env.pop("MAAS_DEPLOY_MODE", None)
        p = subprocess.run(
            ["bash", "-c", f"source '{lib}' && deploy_mode"],
            capture_output=True, text=True, env=env)
        return p.returncode, (p.stdout + p.stderr).strip()


class TestDeployModeOverride(unittest.TestCase):
    def test_default_legacy_without_file(self):
        rc, out = run_deploy_mode()
        self.assertEqual((rc, out), (0, "legacy"))

    def test_file_legacy(self):
        rc, out = run_deploy_mode(ops_file_content="DEPLOY_MODE=legacy\n")
        self.assertEqual((rc, out), (0, "legacy"))

    def test_env_overrides_file(self):
        """P0 核心断言：MAAS_DEPLOY_MODE=release 覆盖文件值。"""
        rc, out = run_deploy_mode(
            env_extra={"MAAS_DEPLOY_MODE": "release"},
            ops_file_content="DEPLOY_MODE=legacy\n")
        self.assertEqual((rc, out), (0, "release"))

    def test_env_release_without_file(self):
        rc, out = run_deploy_mode(env_extra={"MAAS_DEPLOY_MODE": "release"})
        self.assertEqual((rc, out), (0, "release"))

    def test_invalid_env_rejected(self):
        rc, out = run_deploy_mode(env_extra={"MAAS_DEPLOY_MODE": "bogus"})
        self.assertNotEqual(rc, 0)
        self.assertIn("非法", out)

    def test_invalid_file_rejected(self):
        rc, out = run_deploy_mode(ops_file_content="DEPLOY_MODE=bogus\n")
        self.assertNotEqual(rc, 0)
        self.assertIn("非法", out)

    def test_repo_file_permanently_legacy(self):
        """仓库 tracked 文件永久保持 legacy（红线：不得翻转）。"""
        content = (BASE / "ops" / "deploy-mode").read_text()
        for line in content.splitlines():
            if line.startswith("DEPLOY_MODE="):
                self.assertEqual(line, "DEPLOY_MODE=legacy")
                return
        self.fail("ops/deploy-mode 缺 DEPLOY_MODE= 行")


if __name__ == "__main__":
    unittest.main()
