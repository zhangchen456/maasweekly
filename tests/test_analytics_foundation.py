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
    """1. Umami version 被 pin；2. 禁止 latest/main/master；P1: commit SHA 双重 pin"""

    UMAMI_COMMIT = "ec0ff50388c264ed8ce46f00967e92f7e71476ae"

    def test_install_umami_exists(self):
        self.assertTrue(INSTALL_UMAMI.exists(), f"{INSTALL_UMAMI} 应存在")

    def test_umami_version_pinned(self):
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertIn(UMAMI_VERSION, blob,
                      f"install-umami.sh 应 pin Umami 版本 {UMAMI_VERSION}")

    def test_umami_commit_sha_pinned(self):
        """P1 修复：同时 pin 40-char upstream commit SHA，防 upstream tag 移动"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertIn(self.UMAMI_COMMIT, blob,
                      "install-umami.sh 应 pin Umami v3.4.0 的 40-char commit SHA")
        # UMAMI_COMMIT 变量定义
        self.assertRegex(blob, r'UMAMI_COMMIT="[0-9a-f]{40}"',
                         "应定义 UMAMI_COMMIT 变量（40-char SHA）")

    def test_clone_verifies_head(self):
        """P1 修复：clone 后验证 HEAD == pinned SHA"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # clone 后必须有 HEAD 验证
        self.assertRegex(blob, r"ACTUAL_COMMIT.*git rev-parse HEAD",
                         "clone 后应验证 HEAD")
        self.assertRegex(blob, r"UMAMI_COMMIT",
                         "HEAD 验证应对比 UMAMI_COMMIT")

    def test_existing_dir_verifies_head(self):
        """P1 修复：已存在 UMAMI_DIR 时验证 HEAD + clean worktree，不一致 fail closed"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 目录已存在时必须有 HEAD 验证
        self.assertRegex(blob, r"ACTUAL_COMMIT.*git rev-parse HEAD",
                         "目录已存在时应验证 HEAD")
        # 验证 clean worktree
        self.assertRegex(blob, r"git status --porcelain",
                         "应验证 clean worktree")
        # 不一致 fail closed
        self.assertRegex(blob, r"die.*版本不匹配|die.*HEAD 不匹配",
                         "版本不匹配应 die（fail closed）")

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
        """幂等：状态 B（role exists + env exists）preserve credential"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"UMAMI_ENV=.*umami\.env",
                         "应定义 UMAMI_ENV 变量指向 umami.env")
        self.assertRegex(blob, r"状态 B.*existing|preserve credential",
                         "应说明状态 B preserve credential")

    def test_installer_no_hardcoded_production_password(self):
        """12. installer 不包含硬编码生产 password"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        hardcoded = re.findall(r"(?:PASSWORD|password)\s*=\s*['\"][a-f0-9]{16,}['\"]", blob)
        self.assertEqual(hardcoded, [],
                         f"不应硬编码生产 password: {hardcoded}")

    def test_installer_db_user_exists_check(self):
        """幂等：PostgreSQL user 已存在时跳过创建"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"ROLE_EXISTS|rolname",
                         "应检查 PostgreSQL role 是否已存在")

    def test_installer_db_exists_check(self):
        """幂等：database 已存在时跳过创建"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"DB_EXISTS|pg_database|datname",
                         "应检查 PostgreSQL database 是否已存在")

    def test_no_alter_user_in_normal_install(self):
        """Round 3 P0 修复：fresh install 不使用 ALTER USER（DB_PASS 一次生成，CREATE ROLE 直接用）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 只检查实际 PostgreSQL 命令行（sudo -u postgres psql -c "ALTER USER"）
        # 排除 echo/注释/heredoc 说明文字
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo ") or stripped.startswith('cat '):
                continue
            # heredoc 内容行（cat <<EOF 与 EOF 之间）不是实际命令
            # 只检查 sudo -u postgres ... ALTER USER 这种实际命令
            if "ALTER USER" in stripped and "psql" in stripped:
                self.fail(f"install-umami.sh 不应使用 ALTER USER（Round 3: DB_PASS 一次生成）: {stripped}")


class TestCredentialStateMachine(unittest.TestCase):
    """Round 3 P0 修复：显式四态状态机。

    四态（在任何 mutation 之前显式检测）：
      A. role absent + env absent  → fresh install（generate credential once）
      B. role exists + env exists  → existing healthy（preserve）
      C. role exists + env absent  → fail closed（STOP，不自动 rotate）
      D. role absent + env exists  → fail closed（STOP，inconsistent）

    C/D 检测必须发生在任何 PostgreSQL/user/database/source mutation 之前。
    """

    @classmethod
    def setUpClass(cls):
        cls.blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 提取非注释行及其行号
        cls.lines = []
        for i, line in enumerate(cls.blob.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            cls.lines.append((i, stripped))

    def _step_index(self, pattern, start=0):
        """返回第一个匹配 pattern 的非注释行的行号"""
        for i, line in self.lines:
            if i < start:
                continue
            if re.search(pattern, line):
                return i
        return -1

    def test_four_state_detection(self):
        """四态状态机：A fresh / B existing / C fail closed / D fail closed"""
        blob = self.blob
        # 状态 A：role absent + env absent → fresh install
        self.assertRegex(blob, r"状态 A.*fresh|A_fresh",
                         "应显式检测状态 A（fresh install）")
        # 状态 B：role exists + env exists → preserve
        self.assertRegex(blob, r"状态 B.*existing|B_existing",
                         "应显式检测状态 B（existing healthy）")
        # 状态 C：role exists + env absent → fail closed
        self.assertRegex(blob, r"状态 C.*incomplete|fail closed",
                         "应显式检测状态 C（role exists + env absent → fail closed）")
        # 状态 D：role absent + env exists → fail closed
        self.assertRegex(blob, r"状态 D.*inconsistent",
                         "应显式检测状态 D（role absent + env exists → fail closed）")

    def test_state_C_fail_closed(self):
        """状态 C（role exists + env absent）die（fail closed），不自动 rotate"""
        blob = self.blob
        # 状态 C 必须 die
        self.assertRegex(blob, r"die.*状态 C|die.*role.*已存在.*env.*不存在|die.*incomplete",
                         "状态 C 必须 die（fail closed）")

    def test_state_D_fail_closed(self):
        """状态 D（role absent + env exists）die（fail closed）"""
        blob = self.blob
        # 状态 D 必须 die
        self.assertRegex(blob, r"die.*状态 D|die.*role.*不存在.*env.*存在|die.*inconsistent",
                         "状态 D 必须 die（fail closed）")

    def test_state_detection_before_any_mutation(self):
        """Round 3 P0 核心修复：C/D 状态检测必须发生在任何 mutation 之前。

        mutation 包括：CREATE USER / CREATE DATABASE / useradd / mkdir / chown / git clone。
        状态检测（ROLE_EXISTS / ENV_EXISTS）必须在所有这些之前。
        """
        # 状态检测的行号
        state_check = self._step_index(r"ROLE_EXISTS|状态.*预检|credential.*状态")
        self.assertGreater(state_check, 0, "应有 credential 状态预检")

        # 各 mutation 的行号
        mutations = [
            (r"CREATE USER|CREATE ROLE", "CREATE USER"),
            (r"CREATE DATABASE", "CREATE DATABASE"),
            (r"useradd", "useradd"),
            (r"git clone", "git clone"),
        ]
        for pattern, name in mutations:
            mut_line = self._step_index(pattern)
            if mut_line > 0:  # dry-run 分支可能不含
                self.assertLess(state_check, mut_line,
                                f"状态检测必须在 {name} 之前：状态检测={state_check}, {name}={mut_line}")

    def test_fresh_install_credential_generated_once(self):
        """Round 3 P0 修复：fresh install DB_PASS 一次生成，CREATE ROLE 直接用"""
        blob = self.blob
        # DB_PASS 生成（openssl rand）
        self.assertRegex(blob, r"DB_PASS=.*openssl rand",
                         "fresh install 应生成 DB_PASS")
        # CREATE USER 直接使用 DB_PASS（不是 ALTER USER）
        self.assertRegex(blob, r"CREATE USER.*DB_PASS|CREATE USER.*PASSWORD.*DB_PASS",
                         "CREATE USER 应直接使用生成的 DB_PASS")

    def test_fresh_install_no_alter_user(self):
        """Round 3 P0 修复：fresh install 不 CREATE 后 ALTER（无 ALTER USER 实际命令）"""
        blob = self.blob
        # 整个 install-umami.sh 不应有 psql -c "ALTER USER" 实际命令
        # （注释/echo/heredoc 说明文字除外；只检查 sudo -u postgres psql -c "ALTER USER"）
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo ") or stripped.startswith("cat "):
                continue
            # 实际 PostgreSQL 命令行包含 ALTER USER
            if "ALTER USER" in stripped and "psql" in stripped:
                self.fail(f"install-umami.sh 不应有 ALTER USER 实际命令（Round 3: DB_PASS 一次生成）: {stripped}")

    def test_atomic_env_write(self):
        """Round 3 P0 修复：env 使用 temp file + atomic rename"""
        blob = self.blob
        self.assertRegex(blob, r"mktemp.*umami\.env\.tmp|TMP_ENV.*mktemp",
                         "应使用 temp file 写 env")
        self.assertRegex(blob, r"mv\s+-f.*\$TMP_ENV.*\$UMAMI_ENV|atomic rename",
                         "应 atomic rename temp file → umami.env")


class TestRenderNginxIsolation(unittest.TestCase):
    """Round 3 P1 修复：render-nginx 是真正独立的 nginx 操作。

    render-nginx 不得触发 PostgreSQL/source/build/systemd mutation。
    Production Authorization Package 才能准确标注 Phase 3 = nginx mutation。
    """

    def test_render_nginx_script_exists(self):
        """render-umami-nginx.sh 独立脚本存在"""
        render_script = BASE / "ops" / "render-umami-nginx.sh"
        self.assertTrue(render_script.exists(), "ops/render-umami-nginx.sh 应存在")

    def test_render_nginx_no_db_mutation(self):
        """render-umami-nginx.sh 不触发 PostgreSQL mutation"""
        render_script = BASE / "ops" / "render-umami-nginx.sh"
        blob = render_script.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"CREATE\s+(USER|ROLE|DATABASE)",
                                f"render-umami-nginx.sh 不应包含 PostgreSQL mutation: {stripped}")
            self.assertNotRegex(stripped, r"ALTER\s+USER",
                                f"render-umami-nginx.sh 不应包含 ALTER USER: {stripped}")

    def test_render_nginx_no_source_build_mutation(self):
        """render-umami-nginx.sh 不触发 source/build mutation"""
        render_script = BASE / "ops" / "render-umami-nginx.sh"
        blob = render_script.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"git clone",
                                f"render-umami-nginx.sh 不应 git clone: {stripped}")
            self.assertNotRegex(stripped, r"pnpm\s+(install|run build)",
                                f"render-umami-nginx.sh 不应 pnpm install/build: {stripped}")

    def test_render_nginx_no_systemd_mutation(self):
        """render-umami-nginx.sh 不触发 systemd mutation"""
        render_script = BASE / "ops" / "render-umami-nginx.sh"
        blob = render_script.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"systemctl\s+(enable|start|daemon-reload)",
                                f"render-umami-nginx.sh 不应 systemctl mutation: {stripped}")
            self.assertNotRegex(stripped, r"install.*maas-umami\.service",
                                f"render-umami-nginx.sh 不应安装 systemd service: {stripped}")

    def test_render_nginx_only_nginx_operations(self):
        """render-umami-nginx.sh 只做 nginx 操作（sed 渲染 + nginx -t + reload）"""
        render_script = BASE / "ops" / "render-umami-nginx.sh"
        blob = render_script.read_text(encoding="utf-8")
        self.assertRegex(blob, r"sed.*ssl_certificate|sed.*NGINX_SRC",
                         "应 sed 渲染 nginx config")
        self.assertRegex(blob, r"nginx\s+-t",
                         "应 nginx -t")
        self.assertRegex(blob, r"nginx\s+-s\s+reload",
                         "应 nginx -s reload")

    def test_install_umami_does_not_render_nginx(self):
        """install-umami.sh 不渲染 nginx config（由 render-umami-nginx.sh 负责）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"render-umami-nginx\.sh",
                         "install-umami.sh 应引用 render-umami-nginx.sh")
        # install-umami.sh 不应直接渲染 ssl_certificate
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"sed.*ssl_certificate",
                                f"install-umami.sh 不应直接渲染 ssl_certificate: {stripped}")


class TestBuildCompletion(unittest.TestCase):
    """Round 3 P1 修复：build 完成契约。

    不以 .next exists 判断 build 成功（.next 可能是中途失败半成品）。
    采用可证明与 pinned SHA 对应的 build strategy：每次明确 pnpm install + pnpm run build。
    """

    def test_no_next_dir_skip_build(self):
        """不以 .next exists 判断 build 成功"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 不应有"if [ -d .next ]; then skip build"逻辑
        # 检查非注释行
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r'if\s+\[\s*-d.*\.next.*\].*skip',
                                f"不应以 .next exists 判断 build 成功: {stripped}")

    def test_build_always_executed(self):
        """每次明确 pnpm run build（不靠目录存在 skip）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"pnpm run build",
                         "应明确执行 pnpm run build")

    def test_pnpm_install_always_executed(self):
        """每次明确 pnpm install（不靠 node_modules exists skip）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"pnpm install",
                         "应明确执行 pnpm install")


class TestPartialFailureRerun(unittest.TestCase):
    """Round 3 P0 修复：部分失败/re-run 契约。

    installer 必须能从部分失败恢复（重复执行不破坏已就位状态）。
    关键：第一次执行若在 CREATE USER 之后、env 生成之前失败，
    第二次执行不能因 role exists + env absent 永久卡在状态 C。
    """

    def test_state_C_is_recoverable_via_explicit_path(self):
        """状态 C（role exists + env absent）应给出人工诊断路径，而非 destructive recovery"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 状态 C 应 die，且不提供 destructive recovery（dropdb/dropuser）
        self.assertRegex(blob, r"die.*状态 C|die.*incomplete",
                         "状态 C 应 die")
        # 不应建议 dropdb/dropuser（destructive recovery）——检查实际命令行，排除 echo/注释
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo "):
                continue
            self.assertNotRegex(stripped, r"^\S*(dropdb|dropuser)",
                                f"状态 C 不应建议 destructive recovery (dropdb/dropuser): {stripped}")

    def test_installer_no_destructive_recovery_hints(self):
        """installer 不提供 destructive recovery 路径（不 dropdb/dropuser）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo "):
                continue
            self.assertNotRegex(stripped, r"^\S*(dropdb|dropuser)",
                                f"installer 不应提示 dropdb/dropuser: {stripped}")

    def test_state_detection_before_useradd(self):
        """状态检测必须在 useradd 之前（useradd 是首个 mutation）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        lines = []
        for i, line in enumerate(blob.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            lines.append((i, stripped))

        state_check = -1
        useradd_line = -1
        for i, line in lines:
            if state_check < 0 and re.search(r"ROLE_EXISTS|状态.*预检|credential.*状态", line):
                state_check = i
            if useradd_line < 0 and re.search(r"useradd", line):
                useradd_line = i

        if state_check > 0 and useradd_line > 0:
            self.assertLess(state_check, useradd_line,
                            f"状态检测({state_check})必须在 useradd({useradd_line})之前")


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

    def test_rollback_no_destructive_cleanup_hints(self):
        """P1 修复：rollback 不提供 destructive cleanup 命令提示（避免误操作入口）"""
        blob = ROLLBACK_UMAMI.read_text(encoding="utf-8")
        # 不应在提示中给出 dropdb/dropuser/rm -rf 等命令
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"dropdb\b",
                                f"rollback 不应提示 dropdb 命令: {stripped}")
            self.assertNotRegex(stripped, r"dropuser\b",
                                f"rollback 不应提示 dropuser 命令: {stripped}")
            self.assertNotRegex(stripped, r"rm\s+-rf.*umami",
                                f"rollback 不应提示 rm -rf umami: {stripped}")


class TestExecutionOrderContract(unittest.TestCase):
    """P0 修复：执行顺序契约测试（核心修复）。

    Gate A FAIL 根因：静态契约测试 28/28 通过，但首次安装仍会失败——因为
    测试只检查"元素存在"，没验证"关键生命周期顺序"。

    本类验证 install-umami.sh 中关键步骤的执行顺序：
      PostgreSQL active → role → database → env → clone/install → build

    顺序错误的后果：
      - build 在 env 之前 → prisma 无 DATABASE_URL → FAIL
      - database 在 role 之前 → CREATE DATABASE OWNER <不存在的 role> → FAIL
    """

    @classmethod
    def setUpClass(cls):
        cls.blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 提取非注释行及其在文件中的行号，用于顺序断言
        cls.lines = []
        for i, line in enumerate(cls.blob.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            cls.lines.append((i, stripped))

    def _step_index(self, pattern, start=0):
        """返回第一个匹配 pattern 的非注释行的行号，从 start 之后找"""
        for i, line in self.lines:
            if i < start:
                continue
            if re.search(pattern, line):
                return i
        return -1

    def test_postgresql_active_before_role_creation(self):
        """PostgreSQL active 必须在 role creation 之前"""
        pg_active = self._step_index(r"systemctl.*postgresql|is-active.*postgresql")
        role_create = self._step_index(r"CREATE USER|CREATE ROLE")
        self.assertGreater(pg_active, 0, "应有 PostgreSQL active 检查")
        self.assertGreater(role_create, 0, "应有 role 创建")
        self.assertLess(pg_active, role_create,
                       "PostgreSQL active 必须在 role creation 之前")

    def test_role_before_database(self):
        """P0 修复：role 必须先于 CREATE DATABASE ... OWNER role"""
        role_step = self._step_index(r"CREATE USER|CREATE ROLE|USER_EXISTS")
        db_step = self._step_index(r"CREATE DATABASE")
        self.assertGreater(role_step, 0, "应有 role 创建/检查")
        self.assertGreater(db_step, 0, "应有 database 创建")
        self.assertLess(role_step, db_step,
                       "role 必须先于 database（CREATE DATABASE OWNER role 需要 role 已存在）")

    def test_database_before_env(self):
        """database 必须在 umami.env 生成之前（DATABASE_URL 引用 database）。

        Round 3 四态状态机：ENV_EXISTS 状态检测（if [ -f "$UMAMI_ENV" ]）在
        CREATE DATABASE 之前——这是状态检测，不是 env 生成。env 生成（TMP_ENV/mv）
        必须在 CREATE DATABASE 之后。"""
        db_step = self._step_index(r"CREATE DATABASE")
        # env 生成逻辑（temp file + atomic rename），不是状态检测
        env_gen_step = self._step_index(r"TMP_ENV|mktemp.*umami\.env\.tmp|写.*umami\.env")
        self.assertGreater(db_step, 0, "应有 CREATE DATABASE")
        self.assertGreater(env_gen_step, 0, "应有 umami.env 生成逻辑（temp file + atomic rename）")
        self.assertLess(db_step, env_gen_step,
                       "CREATE DATABASE 必须在 umami.env 生成之前")

    def test_env_before_clone(self):
        """P0 修复：umami.env 必须在 clone 之前（build 需要 DATABASE_URL）"""
        # env 生成逻辑（temp file + atomic rename），不是状态检测
        env_step = self._step_index(r"TMP_ENV|mktemp.*umami\.env\.tmp|写.*umami\.env")
        clone_step = self._step_index(r"git clone")
        self.assertGreater(env_step, 0, "应有 umami.env 生成逻辑")
        self.assertGreater(clone_step, 0, "应有 git clone")
        self.assertLess(env_step, clone_step,
                       "umami.env 生成必须在 git clone 之前")

    def test_clone_before_build(self):
        """clone 必须在 pnpm install/build 之前"""
        clone_step = self._step_index(r"git clone")
        build_step = self._step_index(r"pnpm run build|pnpm install")
        self.assertGreater(clone_step, 0, "应有 git clone")
        self.assertGreater(build_step, 0, "应有 pnpm install/build")
        self.assertLess(clone_step, build_step,
                       "git clone 必须在 pnpm install/build 之前")

    def test_env_before_build(self):
        """P0 修复：umami.env 必须在 build 之前（prisma 需要 DATABASE_URL）"""
        # env 生成逻辑（temp file + atomic rename），不是状态检测
        env_step = self._step_index(r"TMP_ENV|mktemp.*umami\.env\.tmp|写.*umami\.env")
        build_step = self._step_index(r"pnpm run build")
        self.assertGreater(env_step, 0, "应有 umami.env 生成逻辑")
        self.assertGreater(build_step, 0, "应有 pnpm run build")
        self.assertLess(env_step, build_step,
                       "umami.env 生成必须在 pnpm run build 之前（prisma 自动建表需要 DATABASE_URL）")

    def test_build_before_systemd(self):
        """build 必须在 systemd service 安装之前"""
        build_step = self._step_index(r"pnpm run build")
        systemd_step = self._step_index(r"install.*maas-umami\.service|systemctl daemon-reload")
        self.assertGreater(build_step, 0, "应有 pnpm run build")
        self.assertGreater(systemd_step, 0, "应有 systemd service 安装")
        self.assertLess(build_step, systemd_step,
                       "build 必须在 systemd service 安装之前")

    def test_full_order_pipeline(self):
        """完整顺序（Round 3 四态状态机）：
        preflight → pg active → credential state precheck → user → role → db → env → clone → build → systemd

        Round 3 修复：PostgreSQL active 在 credential 状态预检之前（状态预检需查询 PG）；
        credential 状态预检在 user/role/db mutation 之前。"""
        checks = [
            (r"preflight|检查 node", "preflight"),
            (r"systemctl.*postgresql|is-active.*postgresql", "PostgreSQL active"),
            (r"ROLE_EXISTS|状态.*预检|credential.*状态", "credential state precheck"),
            (r"useradd", "service user"),
            (r"CREATE USER", "role"),
            (r"CREATE DATABASE", "database"),
            (r"TMP_ENV|mktemp.*umami\.env\.tmp|写.*umami\.env", "env generation"),
            (r"git clone", "clone"),
            (r"pnpm run build", "build"),
            (r"maas-umami\.service|systemctl daemon-reload", "systemd"),
        ]
        prev_line = 0
        prev_name = "(start)"
        for pattern, name in checks:
            line = self._step_index(pattern, start=prev_line)
            self.assertGreater(line, 0,
                               f"应找到 {name} 步骤（pattern: {pattern}）")
            self.assertGreater(line, prev_line,
                               f"顺序错误：{name}（行 {line}）应在 {prev_name}（行 {prev_line}）之后")
            prev_line = line
            prev_name = name


class TestTlsNginxClosedLoop(unittest.TestCase):
    """P1 修复：TLS / nginx 安装 contract 闭环。

    Gate A FAIL：原实现安装一个 nginx -t 已知会失败的 443 ssl config（注释掉的
    ssl_certificate），依赖生产服务器手工取消注释——这会产生 repo 与生产漂移。

    修复：installer 不安装含注释 ssl_certificate 的模板；Gate B 用 --render-nginx
    <cert> <key> 渲染完整 config，保证 nginx -t 闭环通过。
    """

    def test_nginx_template_no_commented_ssl_directives(self):
        """nginx 模板不应有注释的 ssl_certificate 行（避免 repo/生产漂移）"""
        blob = UMAMI_NGINX.read_text(encoding="utf-8")
        # 模板可以说明证书路径，但不应用注释行假装是 ssl_certificate 配置
        # 允许注释说明（如 # ssl_certificate 由 --render-nginx 渲染）
        # 但不应有 "# ssl_certificate /etc/..." 这种"待取消注释"的行
        for line in blob.splitlines():
            stripped = line.strip()
            # 禁止"# ssl_certificate <path>;"这种待取消注释的配置
            self.assertNotRegex(stripped, r"^#\s*ssl_certificate\s+/",
                                f"nginx 模板不应有待取消注释的 ssl_certificate: {stripped}")

    def test_installer_render_nginx_delegated_to_separate_script(self):
        """Round 3 P1 修复：render-nginx 拆为独立脚本 render-umami-nginx.sh"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        self.assertRegex(blob, r"render-umami-nginx\.sh",
                         "install-umami.sh 应引用 render-umami-nginx.sh（独立脚本）")
        self.assertNotRegex(blob, r"--render-nginx",
                            "install-umami.sh 不应支持 --render-nginx（已拆为独立脚本）")

    def test_render_nginx_script_runs_nginx_t(self):
        """Round 3：render-umami-nginx.sh 执行 nginx -t（完整配置，预期通过）"""
        render_script = BASE / "ops" / "render-umami-nginx.sh"
        blob = render_script.read_text(encoding="utf-8")
        self.assertRegex(blob, r"nginx\s+-t",
                         "render-umami-nginx.sh 应 nginx -t")

    def test_install_umami_does_not_run_nginx_t(self):
        """Round 3：install-umami.sh 不执行 nginx -t（由 render-umami-nginx.sh 负责）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        # 只检查实际命令行（nginx -t 作为独立命令），排除 echo/注释/heredoc 文字
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("echo ") or stripped.startswith("cat "):
                continue
            # 实际 nginx -t 命令（run "..." "nginx -t" 或裸 nginx -t）
            if re.match(r'^(nginx\s+-t|run\s+.*nginx\s+-t)', stripped):
                self.fail(f"install-umami.sh 不应 nginx -t（由 render-umami-nginx.sh 负责）: {stripped}")

    def test_install_umami_does_not_install_nginx_config(self):
        """Round 3：install-umami.sh 不安装 nginx config 到生产（由 render-umami-nginx.sh 负责）"""
        blob = INSTALL_UMAMI.read_text(encoding="utf-8")
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"install.*NGINX_DST|install.*maasweekly-umami\.conf.*/etc/nginx",
                                f"install-umami.sh 不应直接安装 nginx config: {stripped}")


if __name__ == "__main__":
    unittest.main()
