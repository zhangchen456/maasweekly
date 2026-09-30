"""
T08-1A Analytics Foundation contract tests.

Gate A 静态契约测试：验证 Umami Analytics 基础设施配置满足安全与架构约束，
不依赖真实 PostgreSQL/Umami 运行（CI 环境不启动这些服务）。

覆盖任务书 §24 的 14 项契约检查：
  1. Umami version 被 pin
  2. 禁止 latest/main/master
  3. env.example 不含 secret
  4. systemd 不以 root 运行
  5. service 仅监听 localhost
  6. nginx upstream 指向 localhost
  7. nginx config 不影响现有 route contract
  8. telemetry guard 允许 Umami Foundation
  9. telemetry guard 仍阻止未经批准 telemetry
  10. frontend 没有 Umami tracking script
  11. installer 保留已有 env（幂等）
  12. installer 不包含硬编码生产 password
  13. rollback 不删除 DB
  14. existing relevant tests continue passing（由 run-all-tests.sh 覆盖）
"""

import os
import re
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# T08-1A 候选文件
INSTALL_UMAMI = BASE / "ops" / "install-umami.sh"
ROLLBACK_UMAMI = BASE / "ops" / "rollback-umami.sh"
UMAMI_SERVICE = BASE / "ops" / "maas-umami.service"
UMAMI_ENV_EXAMPLE = BASE / "ops" / "maas-umami.env.example"
UMAMI_NGINX = BASE / "ops" / "nginx" / "maasweekly-umami.conf"

# 现有文件（telemetry guard 边界确认）
LAYOUT_ASTRO = BASE / "site" / "src" / "layouts" / "Layout.astro"
SKILL_INSTALLER = BASE / "site" / "scripts" / "install-skill.sh"

# 已冻结的 Umami 版本
UMAMI_VERSION = "v3.4.0"


class TestUmamiVersionPinned(unittest.TestCase):
    """1. Umami version 被 pin；2. 禁止 latest/main/master"""

    def test_install_umami_exists(self):
        self.assertTrue(INSTALL_UMAMI.exists(), f"{INSTALL_UMAMI} 应存在")

    def test_umami_version_pinned(self):
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertIn(UMAMI_VERSION, blob,
                      f"install-umami.sh 应 pin Umami 版本 {UMAMI_VERSION}")

    def test_no_latest_main_master_for_umami(self):
        """禁止 latest/main/master 用于 Umami 版本"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 检查 git clone 行不使用 latest/main/master
        clone_lines = [l for l in blob.splitlines() if "git clone" in l]
        self.assertTrue(len(clone_lines) > 0, "应有 git clone 行")
        for line in clone_lines:
            # Umami repo 的 clone 必须用具体 tag
            if "umami-software/umami" in line:
                self.assertIn(UMAMI_VERSION, line,
                              f"Umami clone 必须 pin {UMAMI_VERSION}，禁止 latest/main/master: {line}")
                self.assertNotRegex(line, r"--branch\s+(latest|main|master)\b",
                                    f"禁止 latest/main/master: {line}")


class TestEnvExampleNoSecret(unittest.TestCase):
    """3. env.example 不含 secret"""

    def test_env_example_exists(self):
        self.assertTrue(UMAMI_ENV_EXAMPLE.exists(), f"{UMAMI_ENV_EXAMPLE} 应存在")

    def test_no_real_database_url(self):
        """DATABASE_URL 必须是占位符，不是真实连接串"""
        blob = UMAMI_ENV_EXAMPLE.read_text(encoding="utf-8")
        # 匹配 postgresql://user:password@... 但 password 不能是真实值
        # 占位符形式：postgresql://maas_umami:<root 生成...>@localhost
        urls = re.findall(r"DATABASE_URL=postgresql://\S+", blob)
        self.assertTrue(len(urls) > 0, "应有 DATABASE_URL")
        for url in urls:
            # 密码段必须是占位符（含 < 或 "root 生成"）
            self.assertRegex(url, r"postgresql://maas_umami:<",
                             f"DATABASE_URL 密码必须是占位符: {url}")

    def test_no_real_app_secret(self):
        """APP_SECRET 必须是占位符"""
        blob = UMAMI_ENV_EXAMPLE.read_text(encoding="utf-8")
        secrets = re.findall(r"APP_SECRET=\S+", blob)
        self.assertTrue(len(secrets) > 0, "应有 APP_SECRET")
        for s in secrets:
            self.assertRegex(s, r"APP_SECRET=<",
                             f"APP_SECRET 必须是占位符: {s}")

    def test_hostname_localhost(self):
        """HOSTNAME 必须默认 127.0.0.1（不监听公网）"""
        blob = UMAMI_ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertRegex(blob, r"HOSTNAME=127\.0\.0\.1",
                         "HOSTNAME 必须 127.0.0.1")


class TestSystemdNonRoot(unittest.TestCase):
    """4. systemd 不以 root 运行"""

    def test_service_exists(self):
        self.assertTrue(UMAMI_SERVICE.exists(), f"{UMAMI_SERVICE} 应存在")

    def test_user_not_root(self):
        blob = UMAMI_SERVICE.read_text(encoding="utf-8")
        user_lines = re.findall(r"^User=(\S+)", blob, re.M)
        self.assertTrue(len(user_lines) > 0, "应有 User= 行")
        self.assertNotIn("root", user_lines, "User 不能是 root")
        self.assertIn("maasumami", user_lines, "User 应是 maasumami")

    def test_no_memory_deny_write_execute(self):
        """不用 MemoryDenyWriteExecute=true（Node/V8 JIT 需要 RWX）。
        注释中提到该指令名是允许的（说明为何不用），但不得真正启用。"""
        blob = UMAMI_SERVICE.read_text(encoding="utf-8")
        # 检查非注释行不得启用 MemoryDenyWriteExecute
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"^MemoryDenyWriteExecute\s*=",
                                "不得启用 MemoryDenyWriteExecute（V8 JIT 需要 RWX）")

    def test_restrict_address_families(self):
        """只允许 AF_INET AF_INET6 AF_UNIX"""
        blob = UMAMI_SERVICE.read_text(encoding="utf-8")
        self.assertRegex(blob, r"RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
                         "应限制 AddressFamilies")


class TestNginxLocalhostUpstream(unittest.TestCase):
    """5. service 仅监听 localhost；6. nginx upstream 指向 localhost；7. 不影响现有 route contract"""

    def test_nginx_exists(self):
        self.assertTrue(UMAMI_NGINX.exists(), f"{UMAMI_NGINX} 应存在")

    def test_nginx_upstream_localhost(self):
        blob = UMAMI_NGINX.read_text(encoding="utf-8")
        self.assertRegex(blob, r"proxy_pass\s+http://127\.0\.0\.1:3000",
                         "nginx upstream 必须 127.0.0.1:3000")

    def test_nginx_server_name_analytics_subdomain(self):
        """独立 subdomain，不混入 daily.maas.click 主站"""
        blob = UMAMI_NGINX.read_text(encoding="utf-8")
        self.assertRegex(blob, r"server_name\s+analytics\.maas\.click",
                         "应服务 analytics.maas.click 子域名")

    def test_nginx_does_not_touch_agent_routes(self):
        """不影响现有 agent-api route contract（不含 /api/v1/ /api/mcp 等 location）"""
        blob = UMAMI_NGINX.read_text(encoding="utf-8")
        # 不应包含 agent-api 的 location
        self.assertNotRegex(blob, r"location\s+/?api/v1/",
                            "不应包含 /api/v1/ location（属 agent-api contract）")
        self.assertNotRegex(blob, r"location\s+=\s*/api/mcp",
                            "不应包含 /api/mcp location（属 agent-api contract）")


class TestTelemetryGuard(unittest.TestCase):
    """8. telemetry guard 允许 Umami Foundation；9. 仍阻止未经批准 telemetry"""

    # 未经批准的 telemetry（仍应被禁止）
    UNAPPROVED_TELEMETRY = [
        "gtag", "googletagmanager", "google-analytics.com",
        "segment.com", "analytics.segment.com",
        "posthog", "app.posthog.com",
        "plausible", "plausible.io",
        "matomo", "matomo.org",
        "hotjar", "static.hotjar.com",
    ]

    def test_layout_no_umami_tracking_script(self):
        """10. frontend 没有 Umami tracking script（T08-1A 不做前端采集）"""
        self.assertTrue(LAYOUT_ASTRO.exists(), f"{LAYOUT_ASTRO} 应存在")
        blob = LAYOUT_ASTRO.read_text(encoding="utf-8")
        # T08-1A 不应在 Layout.astro 引入 Umami tracking script
        self.assertNotIn("umami", blob.lower(),
                          "T08-1A 不应在 Layout.astro 引入 Umami script（属 T08-1B）")
        self.assertNotRegex(blob, r'src=["\x27]https?://[^"\x27]*umami',
                            "不应引入 Umami tracking script src")

    def test_layout_no_unapproved_telemetry(self):
        """9. frontend 仍无未经批准的 telemetry"""
        self.assertTrue(LAYOUT_ASTRO.exists())
        blob = LAYOUT_ASTRO.read_text(encoding="utf-8")
        for term in self.UNAPPROVED_TELEMETRY:
            self.assertNotIn(term.lower(), blob.lower(),
                             f"Layout.astro 不应包含未经批准的 telemetry: {term}")

    def test_skill_installer_still_no_telemetry(self):
        """Skill install.sh 仍不调用 telemetry（原 test_no_sudo_no_telemetry 语义保持）"""
        self.assertTrue(SKILL_INSTALLER.exists())
        blob = SKILL_INSTALLER.read_text(encoding="utf-8")
        posts = re.findall(r"curl[^\n]*-X\s*POST|curl[^\n]*--data", blob)
        self.assertEqual(posts, [], "Skill install.sh 无遥测上报")

    def test_umami_install_does_not_break_skill_guard(self):
        """8. Umami installer 引入不破坏 Skill telemetry guard（不同对象）"""
        # install-umami.sh 是独立脚本，不修改 install-skill.sh
        skill_blob = SKILL_INSTALLER.read_text(encoding="utf-8")
        posts = re.findall(r"curl[^\n]*-X\s*POST|curl[^\n]*--data", skill_blob)
        self.assertEqual(posts, [], "Skill install.sh 仍无遥测（Umami 不影响）")


class TestInstallerIdempotent(unittest.TestCase):
    """11. installer 保留已有 env（幂等）；12. 不包含硬编码生产 password"""

    def test_installer_preserves_existing_env(self):
        """幂等：umami.env 已存在时保留"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 检查幂等逻辑：用 UMAMI_ENV 变量检查存在性，并说明保留既有 secret
        self.assertRegex(blob, r"UMAMI_ENV=.*umami\.env",
                         "应定义 UMAMI_ENV 变量指向 umami.env")
        self.assertRegex(blob, r'if\s+\[\s+-f\s+"\$UMAMI_ENV"\s+\]',
                         "应检查 umami.env 是否已存在")
        self.assertRegex(blob, r"保留既有 secret|保留",
                         "应说明保留既有 secret")

    def test_installer_no_hardcoded_production_password(self):
        """12. installer 不包含硬编码生产 password"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 不应包含真实的 hex 密码（openssl rand 在服务器现场生成）
        # 占位符 <root 生成...> 是允许的；openssl rand 命令是允许的
        # 禁止 PASSWORD=xxxxx 或 password="xxxxx" 等硬编码值
        hardcoded = re.findall(r"(?:PASSWORD|password)\s*=\s*['\"][a-f0-9]{16,}['\"]", blob)
        self.assertEqual(hardcoded, [],
                         f"不应硬编码生产 password: {hardcoded}")

    def test_installer_db_user_exists_check(self):
        """幂等：PostgreSQL user 已存在时跳过创建"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"USER_EXISTS|rolname",
                         "应检查 PostgreSQL user 是否已存在")

    def test_installer_db_exists_check(self):
        """幂等：database 已存在时跳过创建"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"DB_EXISTS|pg_database|datname",
                         "应检查 PostgreSQL database 是否已存在")


class TestRollbackNonDestructive(unittest.TestCase):
    """13. rollback 不删除 DB"""

    def test_rollback_exists(self):
        self.assertTrue(ROLLBACK_UMAMI.exists(), f"{ROLLBACK_UMAMI} 应存在")

    def test_rollback_no_drop_database(self):
        """rollback 禁止 DROP DATABASE"""
        blob = ROLLBACK_UMAMI.read_text(encoding="utf-8")
        # 不应包含 DROP DATABASE（注释中提到也不行，除非显式 --purge-data 警告）
        # 检查非注释行
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"\bDROP\s+DATABASE",
                                f"rollback 不应执行 DROP DATABASE: {stripped}")

    def test_rollback_no_dropdb_command(self):
        """rollback 禁止 dropdb 命令（除非显式手动提示）"""
        blob = ROLLBACK_UMAMI.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo"):
                continue
            self.assertNotRegex(stripped, r"^\s*dropdb\b",
                                f"rollback 不应直接执行 dropdb: {stripped}")

    def test_rollback_preserves_env_and_app(self):
        """rollback 保留 umami.env 与 Umami 应用目录"""
        blob = ROLLBACK_UMAMI.read_text(encoding="utf-8")
        self.assertIn("保留", blob, "应明确保留项")
        self.assertRegex(blob, r"umami\.env", "应保留 umami.env")
        self.assertRegex(blob, r"/srv/maasweekly/umami", "应保留 Umami 应用目录")

    def test_rollback_does_not_touch_main_site(self):
        """rollback 不影响 daily.maas.click 主站与 agent-api"""
        blob = ROLLBACK_UMAMI.read_text(encoding="utf-8")
        # 不应修改主站 https.conf 或 agent 配置
        self.assertNotRegex(blob, r"maasweekly-https\.conf",
                            "rollback 不应修改主站 https.conf")
        self.assertNotRegex(blob, r"maasweekly-agent",
                            "rollback 不应修改 agent-api 配置")


if __name__ == "__main__":
    unittest.main()
