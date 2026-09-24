"""T07-5.2 Developer / Platform Registry 测试。

核心：Developer 与 Platform 是独立 entity type，无 FK 关系。
"""
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

    def test_developer_id_unique(self):
        ids = [d["developerId"] for d in self.devs["developers"]]
        self.assertEqual(len(ids), len(set(ids)), "developerId 不唯一")

    def test_platform_id_unique(self):
        ids = [p["platformId"] for p in self.plats["platforms"]]
        self.assertEqual(len(ids), len(set(ids)), "platformId 不唯一")

    def test_no_platform_to_developer_fk(self):
        """Platform 不含 developerId FK（Platform/Developer 独立）"""
        for p in self.plats["platforms"]:
            self.assertNotIn("developerId", p,
                             f"platform {p['platformId']} 含 developerId FK")

    def test_no_developer_to_platform_fk(self):
        """Developer 不含 platforms 反向 FK"""
        for d in self.devs["developers"]:
            self.assertNotIn("platforms", d,
                             f"developer {d['developerId']} 含 platforms FK")

    def test_developer_verification_status_valid(self):
        valid = {"verified", "candidate", "unresolved"}
        for d in self.devs["developers"]:
            self.assertIn(d.get("verificationStatus"), valid,
                          f"developer {d['developerId']} verificationStatus 非法")

    def test_platform_verification_status_valid(self):
        valid = {"verified", "candidate", "unresolved"}
        for p in self.plats["platforms"]:
            self.assertIn(p.get("verificationStatus"), valid,
                          f"platform {p['platformId']} verificationStatus 非法")

    def test_evidence_four_fields(self):
        """evidence 四字段全部非空"""
        fields = ["sourceType", "sourceUrl", "verifiedAt", "verificationNote"]
        for d in self.devs["developers"]:
            ev = d.get("evidence", {})
            for f in fields:
                self.assertTrue(ev.get(f), f"developer {d['developerId']} evidence.{f} 缺失")
        for p in self.plats["platforms"]:
            ev = p.get("evidence", {})
            for f in fields:
                self.assertTrue(ev.get(f), f"platform {p['platformId']} evidence.{f} 缺失")

    def test_provider_ids_valid(self):
        pub_set = set(p["providerId"] for p in self.pub["providers"])
        for d in self.devs["developers"]:
            for pid in d.get("providerIds", []):
                self.assertIn(pid, pub_set,
                              f"developer {d['developerId']} providerId 不在 public_providers: {pid}")
        for p in self.plats["platforms"]:
            if p.get("providerId"):
                self.assertIn(p["providerId"], pub_set,
                              f"platform {p['platformId']} providerId 不在 public_providers")

    def test_google_has_two_platforms(self):
        """Google 对应 2 个 platform（Gemini API + Vertex AI）"""
        google_plats = [p for p in self.plats["platforms"] if p["providerId"] == "google"]
        self.assertEqual(len(google_plats), 2, "Google 应有 2 个 platform")

    def test_developer_not_equal_providerId(self):
        """developer ≠ providerId（至少有 alibaba-qwen ≠ alibaba）"""
        qwen = [d for d in self.devs["developers"] if "qwen" in d["developerId"]]
        self.assertTrue(qwen, "应有 qwen developer")
        for d in qwen:
            self.assertNotEqual(d["developerId"], d.get("providerIds", [""])[0])

    def test_platform_only_developer_is_unresolved(self):
        """brands=[] 的 developer 必须是 unresolved（platform-only ≠ developer）"""
        for d in self.devs["developers"]:
            if not d.get("brands"):
                self.assertEqual(d["verificationStatus"], "unresolved",
                                 f"developer {d['developerId']} brands=[] 但 verificationStatus 非 unresolved")

    def test_no_company_field(self):
        """developer 用 organization，不用 company（不经法律实体核验）"""
        for d in self.devs["developers"]:
            self.assertNotIn("company", d, f"developer {d['developerId']} 含 company 字段")

    def test_validator_script(self):
        r = subprocess.run(
            ["python3", "pipeline/scripts/validate-developer-registry.py"],
            capture_output=True, text=True, cwd=BASE)
        self.assertEqual(r.returncode, 0, f"validator 失败: {r.stderr}")


import json  # noqa: E402

if __name__ == "__main__":
    unittest.main()
