"""
T08-1A Gate B Preflight — Read-only Inventory Capability tests.

验证 maasweekly-deploy-shell 新增的 inventory 只读命令 + maasweekly-inventory helper
的安全边界与契约。

覆盖任务书 §4 的 18 项测试：
  1. inventory 被 allowlist 接受
  2. inventory xxx 被拒绝
  3. arbitrary command 仍被拒绝
  4. inventory script 不接受用户 command 参数
  5. 不使用 eval
  6. 不使用 arbitrary bash/sh passthrough
  7. PostgreSQL SQL 固定
  8. 不读取 umami.env 内容
  9. 不读取 pending state 内容
  10. 不输出 private key
  11. 不执行 mutation systemctl
  12. 不执行 nginx reload/restart
  13. 不 CREATE/ALTER/DROP database
  14. 不 useradd/usermod
  15. 不 mkdir/chmod/chown
  16. missing dependency → NOT_INSTALLED/UNKNOWN，不导致整体失败
  17. permission denied → UNKNOWN_PERMISSION_DENIED
  18. 原有 activate/rollback/status/rsync contract 不回归
"""

import os
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

DEPLOY_SHELL = BASE / "ops" / "server" / "maasweekly-deploy-shell"
INVENTORY = BASE / "ops" / "server" / "maasweekly-inventory"


class TestInventoryAllowlist(unittest.TestCase):
    """1. inventory 被 allowlist 接受；2. inventory xxx 被拒绝；3. arbitrary command 被拒绝"""

    @classmethod
    def setUpClass(cls):
        cls.blob = DEPLOY_SHELL.read_text(encoding="utf-8")

    def test_deploy_shell_exists(self):
        self.assertTrue(DEPLOY_SHELL.exists(), "maasweekly-deploy-shell 应存在")

    def test_inventory_accepted(self):
        """1. inventory（无参数）被 allowlist 接受"""
        blob = self.blob
        self.assertRegex(blob, r'inventory\s*\)',
                         "deploy-shell 应有 inventory 分支")

    def test_inventory_calls_helper(self):
        """inventory 调用固定 maasweekly-inventory helper"""
        blob = self.blob
        self.assertRegex(blob, r'INVENTORY=.*maasweekly-inventory',
                         "应定义 INVENTORY helper 路径")
        self.assertRegex(blob, r'exec sudo -n "\$INVENTORY"',
                         "inventory 应 exec sudo -n $INVENTORY")

    def test_inventory_with_args_rejected(self):
        """2. inventory xxx（带参数）被拒绝（走 * 分支）"""
        blob = self.blob
        # inventory 分支只匹配 "inventory"（无参数），"inventory xxx" 走 * 分支
        # case "inventory" 不匹配 "inventory xxx"
        # 验证 inventory 分支是精确匹配 "inventory )"（不是 "inventory\ *")
        self.assertRegex(blob, r'inventory\s*\)',
                         "inventory 分支应精确匹配（无参数）")
        # 不应有 inventory\ * 分支（inventory 带参数）
        self.assertNotRegex(blob, r'inventory\\\s\*',
                            "不应有 inventory <args> 分支（带参数应被拒绝）")

    def test_arbitrary_command_rejected(self):
        """3. arbitrary command 仍被拒绝（* 分支 reject）"""
        blob = self.blob
        self.assertRegex(blob, r'\*\s*\)\s*\n\s*reject.*不允许的命令',
                         "* 分支应 reject")


class TestInventoryHelperNoPassthrough(unittest.TestCase):
    """4. inventory script 不接受用户 command 参数；5. 不使用 eval；6. 不使用 bash/sh passthrough"""

    @classmethod
    def setUpClass(cls):
        cls.blob = INVENTORY.read_text(encoding="utf-8")

    def test_inventory_helper_exists(self):
        self.assertTrue(INVENTORY.exists(), "maasweekly-inventory 应存在")

    def test_no_user_command_args(self):
        """4. inventory script 不接受用户 command 参数（无 $1/$@/$* 传入 SQL/command）"""
        blob = self.blob
        # inventory helper 不应使用 $1/$2 等位置参数作为 command/SQL/path
        # 注意：$1 可能用于 MAAS_RELEASE_ROOT 注入（测试用），但不应用于 command/SQL
        # 检查不使用 $@ 或 $* passthrough
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r'\$\@|\$\*',
                                f"不应使用 $@/$* passthrough: {stripped}")

    def test_no_eval(self):
        """5. 不使用 eval"""
        blob = self.blob
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r'\beval\b',
                                f"不应使用 eval: {stripped}")

    def test_no_bash_sh_passthrough(self):
        """6. 不使用 arbitrary bash -c / sh -c passthrough"""
        blob = self.blob
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r'\b(bash|sh)\s+-c\b',
                                f"不应使用 bash -c / sh -c passthrough: {stripped}")

    def test_no_exec_user_input(self):
        """不 exec 用户输入"""
        blob = self.blob
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # exec 只允许用于固定命令（不接 $cmd 等用户输入）
            if re.match(r'^exec\s+', stripped):
                # exec 后面不应是用户输入变量
                self.assertNotRegex(stripped, r'exec\s+\$cmd|exec\s+\$1',
                                    f"exec 不应接用户输入: {stripped}")


class TestPostgreSQLSQLFixed(unittest.TestCase):
    """7. PostgreSQL SQL 固定（硬编码，不执行用户传入 SQL）"""

    def test_sql_hardcoded(self):
        """SQL 必须硬编码在脚本中，不使用用户传入参数"""
        blob = INVENTORY.read_text(encoding="utf-8")
        # 所有 psql -c 后面的 SQL 必须是硬编码字符串
        psql_lines = [l for l in blob.splitlines() if "psql" in l and "-c" in l]
        for line in psql_lines:
            stripped = line.strip()
            # SQL 应在双引号或单引号内，不引用 $1/$2 等用户参数
            self.assertNotRegex(stripped, r'psql.*-c.*\$1|psql.*-c.*\$2',
                                f"SQL 不应使用用户传入参数: {stripped}")

    def test_sql_only_metadata(self):
        """SQL 只查询元数据（不查询 credential/password）"""
        blob = INVENTORY.read_text(encoding="utf-8")
        psql_lines = [l for l in blob.splitlines() if "psql" in l and "-c" in l]
        for line in psql_lines:
            stripped = line.strip()
            # 不查询 password / rolpassword 等 credential 字段
            self.assertNotRegex(stripped.lower(), r'select.*rolpassword|select.*password',
                                f"SQL 不应查询 password/credential: {stripped}")

    def test_sql_no_create_alter_drop(self):
        """SQL 不包含 CREATE/ALTER/DROP（mutation）"""
        blob = INVENTORY.read_text(encoding="utf-8")
        psql_lines = [l for l in blob.splitlines() if "psql" in l and "-c" in l]
        for line in psql_lines:
            stripped = line.strip()
            self.assertNotRegex(stripped.upper(), r'\bCREATE\b|\bALTER\b|\bDROP\b',
                                f"SQL 不应包含 CREATE/ALTER/DROP: {stripped}")


class TestSecretRedaction(unittest.TestCase):
    """8. 不读取 umami.env 内容；9. 不读取 pending state 内容；10. 不输出 private key"""

    def test_no_cat_umami_env(self):
        """8. 不读取 umami.env 内容（只 stat）"""
        blob = INVENTORY.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # 不 cat / read / source umami.env
            self.assertNotRegex(stripped, r'\bcat\s+.*umami\.env',
                                f"不应 cat umami.env: {stripped}")
            self.assertNotRegex(stripped, r'\bsource\s+.*umami\.env',
                                f"不应 source umami.env: {stripped}")
            self.assertNotRegex(stripped, r'\bread\s+.*umami\.env',
                                f"不应 read umami.env: {stripped}")

    def test_no_cat_pending_state(self):
        """9. 不读取 .umami-install-state 内容（只 stat）"""
        blob = INVENTORY.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r'\bcat\s+.*\.umami-install-state',
                                f"不应 cat pending state: {stripped}")
            self.assertNotRegex(stripped, r'\bsource\s+.*\.umami-install-state',
                                f"不应 source pending state: {stripped}")

    def test_no_private_key_output(self):
        """10. 不输出 private key 内容"""
        blob = INVENTORY.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # 不 cat / openssl 读取 private key
            self.assertNotRegex(stripped, r'\bcat\s+.*privkey\.pem',
                                f"不应 cat private key: {stripped}")
            # openssl 只用于读 certificate（-in fullchain.pem），不读 private key
            if "openssl" in stripped and "privkey" in stripped:
                self.fail(f"不应 openssl 读取 private key: {stripped}")

    def test_inventory_uses_stat_not_cat_for_env(self):
        """inventory 对 env/pending 只用 stat，不用 cat"""
        blob = INVENTORY.read_text(encoding="utf-8")
        # 对 umami.env / .umami-install-state 只 stat
        # 检查这些文件名附近的命令是 stat 不是 cat
        for filename in ["umami.env", ".umami-install-state"]:
            for line in blob.splitlines():
                stripped = line.strip()
                if filename in stripped and not stripped.startswith("#"):
                    # 行里有 filename 时，不应同时有 cat/read/source
                    if re.search(r'\b(cat|read|source)\b', stripped):
                        # 例外：stat 命令本身可能含文件名
                        if "stat" in stripped:
                            continue
                        self.fail(f"对 {filename} 不应使用 cat/read/source: {stripped}")

    def test_no_database_url_output(self):
        """不输出 DATABASE_URL"""
        blob = INVENTORY.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # 不 echo DATABASE_URL（env 变量）
            if "echo" in stripped and "DATABASE_URL" in stripped:
                self.fail(f"不应 echo DATABASE_URL: {stripped}")


class TestNoMutation(unittest.TestCase):
    """11. 不执行 mutation systemctl；12. 不 nginx reload/restart；13. 不 CREATE/ALTER/DROP；
    14. 不 useradd/usermod；15. 不 mkdir/chmod/chown"""

    MUTATION_PATTERNS = [
        (r'\bsystemctl\s+(enable|start|restart|stop|daemon-reload)\b', "systemctl mutation"),
        (r'\bnginx\s+-s\s+reload\b', "nginx reload"),
        (r'\bnginx\s+-s\s+(stop|reopen)\b', "nginx stop/reopen"),
        (r'\bsystemctl\s+reload\b', "systemctl reload"),
        (r'\buseradd\b', "useradd"),
        (r'\busermod\b', "usermod"),
        (r'\bgroupadd\b', "groupadd"),
        (r'\bmkdir\b', "mkdir"),
        (r'\bchmod\b', "chmod"),
        (r'\bchown\b', "chown"),
        (r'\bCREATE\s+(DATABASE|USER|ROLE)\b', "CREATE mutation"),
        (r'\bALTER\s+(USER|ROLE|DATABASE)\b', "ALTER mutation"),
        (r'\bDROP\s+(DATABASE|USER|ROLE|TABLE)\b', "DROP mutation"),
    ]

    def test_inventory_no_mutation(self):
        """inventory helper 不执行任何 mutation"""
        blob = INVENTORY.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, desc in self.MUTATION_PATTERNS:
                self.assertNotRegex(stripped, pattern,
                                    f"inventory 不应执行 {desc}: {stripped}")

    def test_deploy_shell_no_mutation(self):
        """deploy-shell inventory 分支不执行 mutation（只 sudo inventory helper）"""
        blob = DEPLOY_SHELL.read_text(encoding="utf-8")
        # inventory 分支只 exec sudo -n $INVENTORY，不直接执行 mutation
        # 检查 inventory 分支内无 mutation
        in_inventory = False
        for line in blob.splitlines():
            stripped = line.strip()
            if "inventory )" in stripped or "inventory)" in stripped:
                in_inventory = True
            if in_inventory and (stripped.startswith(";;") or stripped == "esac"):
                in_inventory = False
            if in_inventory and not stripped.startswith("#"):
                for pattern, desc in self.MUTATION_PATTERNS:
                    self.assertNotRegex(stripped, pattern,
                                        f"deploy-shell inventory 分支不应执行 {desc}: {stripped}")


class TestMissingDependencyHandling(unittest.TestCase):
    """16. missing dependency → NOT_INSTALLED/UNKNOWN，不导致整体失败"""

    def test_not_installed_pattern(self):
        """missing dependency 输出 NOT_INSTALLED"""
        blob = INVENTORY.read_text(encoding="utf-8")
        self.assertRegex(blob, r"NOT_INSTALLED",
                         "missing dependency 应输出 NOT_INSTALLED")

    def test_unknown_pattern(self):
        """无法确认的信息输出 UNKNOWN"""
        blob = INVENTORY.read_text(encoding="utf-8")
        self.assertRegex(blob, r"UNKNOWN",
                         "无法确认应输出 UNKNOWN")

    def test_no_exit_on_missing(self):
        """missing dependency 不导致整体失败（不 exit 1）"""
        blob = INVENTORY.read_text(encoding="utf-8")
        # inventory helper 用 set -uo pipefail（不用 set -e），missing dependency 不 exit
        # 检查 command -v ... || true 模式（不因 missing 而 exit）
        self.assertRegex(blob, r"command -v.*\|\|.*true",
                         "missing dependency 应用 || true 不 exit")
        # 不应在开头用 set -e（会导致 missing dependency exit）
        # set -uo pipefail 允许（无 -e）
        for line in blob.splitlines()[:10]:
            stripped = line.strip()
            if stripped.startswith("set "):
                self.assertNotRegex(stripped, r"set\s+-e\b|set\s+.*-e",
                                    "不应 set -e（missing dependency 不应 exit）")


class TestPermissionDenied(unittest.TestCase):
    """17. permission denied → UNKNOWN_PERMISSION_DENIED"""

    def test_permission_denied_pattern(self):
        """permission denied 输出 UNKNOWN_PERMISSION_DENIED"""
        blob = INVENTORY.read_text(encoding="utf-8")
        self.assertRegex(blob, r"UNKNOWN_PERMISSION_DENIED",
                         "permission denied 应输出 UNKNOWN_PERMISSION_DENIED")

    def test_no_sudo_bypass(self):
        """不 sudo 绕过 restricted shell 权限边界（firewall 等不 sudo 提权）"""
        blob = INVENTORY.read_text(encoding="utf-8")
        # ufw/iptables 不应 sudo（用当前用户权限，denied 则 UNKNOWN）
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # ufw status 不应 sudo（可能 permission denied）
            if "ufw" in stripped and "status" in stripped:
                self.assertNotRegex(stripped, r'^sudo\s+.*ufw',
                                    f"ufw 不应 sudo 绕过: {stripped}")
            # iptables 不应 sudo
            if "iptables" in stripped and "-S" in stripped:
                self.assertNotRegex(stripped, r'^sudo\s+.*iptables',
                                    f"iptables 不应 sudo 绕过: {stripped}")


class TestNoRegression(unittest.TestCase):
    """18. 原有 activate/rollback/status/rsync contract 不回归"""

    def test_activate_still_works(self):
        """activate <rid> 分支保持"""
        blob = DEPLOY_SHELL.read_text(encoding="utf-8")
        self.assertRegex(blob, r'activate\\\s\*',
                         "activate 分支应保持")

    def test_rollback_still_works(self):
        """rollback <rid> --reason 分支保持"""
        blob = DEPLOY_SHELL.read_text(encoding="utf-8")
        self.assertRegex(blob, r'rollback\\\s\*',
                         "rollback 分支应保持")

    def test_status_still_works(self):
        """status 分支保持"""
        blob = DEPLOY_SHELL.read_text(encoding="utf-8")
        self.assertRegex(blob, r'status\s*\)',
                         "status 分支应保持")

    def test_rsync_still_works(self):
        """rsync --server 分支保持"""
        blob = DEPLOY_SHELL.read_text(encoding="utf-8")
        self.assertRegex(blob, r'rsync\\\s--server\\\s\*',
                         "rsync 分支应保持")

    def test_reject_default_still_works(self):
        """* 分支 reject 保持"""
        blob = DEPLOY_SHELL.read_text(encoding="utf-8")
        self.assertRegex(blob, r'\*\s*\)\s*\n\s*reject.*不允许的命令',
                         "* 分支应 reject")


if __name__ == "__main__":
    unittest.main()
