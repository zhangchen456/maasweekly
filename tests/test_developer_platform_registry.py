"""T07-5.2 Developer / Platform Registry 测试。"""
import subprocess
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


class TestDeveloperPlatformRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.devs = json.loads((BASE / "data/model-registry/developers.json").read_text("utf-8"))
        cls.plats = json.loads((BASE / "data/model-registry/platforms.json").read_text("utf-8"))
        cls.pub = json.loads((BASE / "pipeline/config/public_providers.json").read_text("utf-8"))
        cls.reg = json.loads((BASE / "data/model-registry/models.json").read_text("utf-8"))

    def test_developer_id_unique(self):
        ids = [d["developerId"] for d in self.devs["developers"]]
        self.assertEqual(len(ids), len(set(ids)), "developerId 不唯一")

    def test_platform_id_unique(self):
        ids = [p["platformId"] for p in self.plats["platforms"]]
        self.assertEqual(len(ids), len(set(ids)), "platformId 不唯一")

    def test_platform_developer_exists(self):
        dev_set = set(d["developerId"] for d in self.devs["developers"])
        for p in self.plats["platforms"]:
            self.assertIn(p["developerId"], dev_set,
                          f"platform {p['platformId']} developerId 不存在")

    def test_developer_platforms_exist(self):
        plat_set = set(p["platformId"] for p in self.plats["platforms"])
        for d in self.devs["developers"]:
            for pid in d.get("platforms", []):
                self.assertIn(pid, plat_set,
                              f"developer {d['developerId']} platform 不存在: {pid}")

    def test_developer_provider_ids_valid(self):
        pub_set = set(p["providerId"] for p in self.pub["providers"])
        for d in self.devs["developers"]:
            for pid in d.get("providerIds", []):
                self.assertIn(pid, pub_set,
                              f"developer {d['developerId']} providerId 不在 public_providers: {pid}")

    def test_registry_provider_ids_covered(self):
        """registry model 的 providerId 必须有对应 developer"""
        dev_provider_ids = set()
        for d in self.devs["developers"]:
            dev_provider_ids.update(d.get("providerIds", []))
        reg_pids = set(m["providerId"] for m in self.reg["models"] if m.get("providerId"))
        for pid in reg_pids:
            self.assertIn(pid, dev_provider_ids,
                          f"registry providerId 无对应 developer: {pid}")

    def test_evidence_present(self):
        for d in self.devs["developers"]:
            self.assertTrue(d.get("evidence", {}).get("sourceType"),
                            f"developer {d['developerId']} 缺 evidence")
        for p in self.plats["platforms"]:
            self.assertTrue(p.get("evidence", {}).get("sourceType"),
                            f"platform {p['platformId']} 缺 evidence")

    def test_google_has_two_platforms(self):
        """Google developer 应对应多个 platform（Gemini API + Vertex AI）"""
        google = [d for d in self.devs["developers"] if d["developerId"] == "google"][0]
        self.assertGreaterEqual(len(google["platforms"]), 2,
                               "Google 应有 >= 2 个 platform")

    def test_developer_not_equal_providerId(self):
        """developerId ≠ providerId（至少有 alibaba-qwen ≠ alibaba）"""
        qwen = [d for d in self.devs["developers"] if "qwen" in d["developerId"]]
        self.assertTrue(qwen, "应有 qwen developer")
        for d in qwen:
            self.assertNotEqual(d["developerId"], d.get("providerIds", [""])[0],
                               f"developer {d['developerId']} == providerId（应不同）")

    def test_validator_script(self):
        r = subprocess.run(
            ["python3", "pipeline/scripts/validate-developer-registry.py"],
            capture_output=True, text=True, cwd=BASE)
        self.assertEqual(r.returncode, 0,
                        f"validator 失败: {r.stderr}")


import json  # noqa: E402

if __name__ == "__main__":
    unittest.main()
