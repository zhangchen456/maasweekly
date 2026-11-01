import importlib.util
import unittest
import tempfile, json
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('llm_digest', Path(__file__).resolve().parents[1] / 'pipeline/scripts/llm-digest.py')
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)

class DigestPlatformsTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        (root/'data/normalized').mkdir(parents=True)
        (root/'data/normalized/platform-logos.json').write_text(json.dumps([{'id':'qwen','name':'阿里百炼','aliases':['阿里百炼']}]))
        p=patch.object(digest,'BASE',root);p.start();self.addCleanup(p.stop)

    def test_price_provider_alias_is_canonical(self):
        result = {'highlights': [{'platform': 'qwen'}]}
        self.assertEqual(digest.validate_highlight_platforms(result, [], [{'provider': 'qwen'}])['highlights'][0]['platform'], '阿里百炼')

    def test_section_heading_is_rejected(self):
        with self.assertRaises(ValueError):
            digest.validate_highlight_platforms({'highlights': [{'platform': '官方定价页'}]}, [], [{'provider': 'qwen'}])

    def test_new_source_does_not_require_logo_registration(self):
        result = {'highlights': [{'platform': 'New Provider'}]}
        self.assertEqual(digest.validate_highlight_platforms(result, [{'platform': 'New Provider'}], []), result)

if __name__ == '__main__':
    unittest.main()
