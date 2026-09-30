"""Execute the PostgreSQL preflight against isolated cluster/SQL fixtures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PostgresPreflightTest(unittest.TestCase):
    def run_probe(self, rows, sql="180006|5432|/var/lib/postgresql/18/main", server=True, sql_ok=True):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            major = rows.split()[0] if rows.split() else "18"
            binary = base / major / "bin/postgres"
            binary.parent.mkdir(parents=True)
            if server:
                binary.write_text("#!/bin/sh\necho 'postgres (PostgreSQL) 18.6'\n")
                binary.chmod(0o755)
            psql = base / "psql"
            psql.write_text("#!/bin/sh\nexit 0\n")
            psql.chmod(0o755)
            helper = (ROOT / "ops/lib-umami-postgres.sh").read_text()
            helper = helper.replace("/usr/lib/postgresql", folder).replace("/usr/bin/psql", str(psql))
            path = base / "helper.sh"
            path.write_text(helper)
            env = dict(os.environ, PROBE_ROWS=rows, PROBE_SQL=sql)
            script = '''
set -euo pipefail
source "$1"
PG_BIN=/usr/bin/psql
pg_lsclusters() { printf '%s\\n' "$PROBE_ROWS"; }
sudo() { printf '%s\\n' "$PROBE_SQL"; return SQL_EXIT; }
umami_pg_discover
umami_pg_validate_connection
'''.replace("SQL_EXIT", "0" if sql_ok else "1")
            return subprocess.run(["bash", "-c", script, "probe", str(path)], env=env, capture_output=True, text=True)

    def test_server_outside_path(self):
        result = self.run_probe("18 main 5432 down postgres /var/lib/postgresql/18/main /log")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_client_only(self):
        self.assertNotEqual(self.run_probe("18 main 5432 down postgres /var/lib/postgresql/18/main /log", server=False).returncode, 0)

    def test_no_target_cluster(self):
        self.assertNotEqual(self.run_probe("18 main 5433 online postgres /var/lib/postgresql/18/main /log").returncode, 0)

    def test_ambiguous_target(self):
        row = "18 main 5432 online postgres /var/lib/postgresql/18/main /log"
        self.assertNotEqual(self.run_probe(row + "\n" + row.replace("main", "other")).returncode, 0)

    def test_wrong_data_directory(self):
        self.assertNotEqual(self.run_probe("18 main 5432 online postgres /var/lib/postgresql/18/main /log", sql="180006|5432|/other").returncode, 0)

    def test_unsupported_version(self):
        self.assertNotEqual(self.run_probe("18 main 5432 online postgres /var/lib/postgresql/18/main /log", sql="120013|5432|/var/lib/postgresql/18/main").returncode, 0)

    def test_minimum_supported_version(self):
        result = self.run_probe("12 main 5432 online postgres /var/lib/postgresql/12/main /log", sql="120014|5432|/var/lib/postgresql/12/main")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_connection_failure(self):
        self.assertNotEqual(self.run_probe("18 main 5432 online postgres /var/lib/postgresql/18/main /log", sql_ok=False).returncode, 0)

    def test_wrong_major(self):
        self.assertNotEqual(self.run_probe("18 main 5432 online postgres /var/lib/postgresql/18/main /log", sql="170006|5432|/var/lib/postgresql/18/main").returncode, 0)

    def test_validation_before_credentials(self):
        installer = (ROOT / "ops/install-umami.sh").read_text()
        self.assertLess(installer.index('"umami_pg_validate_connection"'), installer.index("ROLE_EXISTS=0"))

    def test_installer_dry_run_without_production_source(self):
        result = subprocess.run(["bash", str(ROOT / "ops/install-umami.sh"), "--dry-run"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("clone 后验证 HEAD", result.stdout)


if __name__ == "__main__":
    unittest.main()
