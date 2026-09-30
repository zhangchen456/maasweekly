import subprocess
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SCRIPT = BASE / "ops/install-umami-prerequisites.sh"


class PrerequisiteTest(unittest.TestCase):
    def test_default_is_dry_run(self):
        result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pnpm@12.3.4", result.stdout)
        self.assertIn("18.6-0ubuntu0.26.04.1", result.stdout)
        self.assertNotIn("apt-get update", result.stdout)

    def test_unknown_option_fails_before_mutation(self):
        result = subprocess.run(["bash", str(SCRIPT), "--install"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("apt-get", result.stdout)

    def test_execute_fails_on_other_node_distribution(self):
        # Isolated commands simulate root but a changed /usr/bin/node target.
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            for name, output in [("id", "0"), ("readlink", "/other/node")]:
                path = Path(folder) / name
                path.write_text("#!/bin/sh\necho " + output + "\n")
                path.chmod(0o755)
            env = dict(os.environ, PATH=folder + ":" + os.environ["PATH"])
            result = subprocess.run(["bash", str(SCRIPT), "--execute"], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Node distribution changed", result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
