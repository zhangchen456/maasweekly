import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'pipeline'))
from data_store import (DAILY, SUMMARIES, PRICE_EVENTS, WEEKLY, WEEK_SUMMARIES, compose_daily, compose_weekly,
                        save_observations, save_day_summaries, save_weekly, provenance, record_summary_failure, write)

class StandardInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_independent_summary_failure_preserves_facts_and_freshness(self):
        data = {'updated_at': 'fixed', 'days': [{'date': '2026-09-01', 'changed': [{'id': 'obs_test', 'platform': 'test', 'source_type': 'blog', 'llm_summary': 'old'}], 'failed': [], 'highlights': [{'text': 'old'}]}]}
        save_observations(self.root, data); save_day_summaries(self.root, data['days'])
        before = (self.root / DAILY).read_bytes()
        record_summary_failure(self.root, SUMMARIES, '2026-09-01', 'test-model')
        self.assertEqual((self.root / DAILY).read_bytes(), before)
        self.assertEqual(compose_daily(self.root), data)
        entry = json.loads((self.root / SUMMARIES).read_text())['2026-09-01']
        self.assertEqual(entry['provenance']['status'], 'legacy_unknown')
        self.assertEqual(entry['lastAttempt']['status'], 'failed')
    def test_price_only_day_and_window_and_week_story(self):
        save_observations(self.root, {'days': [{'date': '2026-09-10', 'changed': []}]})
        write(self.root, PRICE_EVENTS, {'2026-01-01': [1], '2026-09-11': [2]})
        self.assertEqual([d['date'] for d in compose_daily(self.root)['days']], ['2026-09-10', '2026-09-11'])
        weeks = [{'week': '2026-W37', 'story': {'theme': 'existing'}, 'highlights': []}]
        save_weekly(self.root, weeks)
        self.assertEqual(compose_weekly(self.root), weeks)
        self.assertNotIn('story', json.loads((self.root / WEEKLY).read_text())[0])
    def test_metadata_uses_exact_prompt_and_never_guesses_legacy(self):
        import hashlib
        meta = provenance({'changed': [{'id': 'obs_test'}]}, 'template', 'model', 'actual prompt')
        self.assertEqual(meta['inputSha256'], hashlib.sha256(b'actual prompt').hexdigest())
        self.assertEqual(meta['inputRefs'], ['obs_test'])
    def test_symlink_standard_input_refused(self):
        target = self.root / 'data/other'; target.mkdir(parents=True)
        (self.root / 'data/normalized').symlink_to(target, target_is_directory=True)
        (target / 'source-streams.json').write_text('{"days":[]}')
        with self.assertRaises(ValueError): compose_daily(self.root)
    def test_consumer_and_writers_have_no_site_authority(self):
        source = (BASE / 'pipeline/public_export/loaders.py').read_text()
        self.assertNotIn('"site/', source)
        for filename in ('llm-digest.py', 'llm-weekly-digest.py', 'fetch-prices.py'):
            source = (BASE / 'pipeline/scripts' / filename).read_text()
            self.assertNotIn('/ "site"', source)
    def test_generator_is_deterministic_and_fails_unsupported_construct(self):
        import subprocess
        result = subprocess.run([sys.executable, str(BASE / 'scripts/generate-public-contract.py'), '--check'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        spec = importlib.util.spec_from_file_location('generator', BASE / 'scripts/generate-public-contract.py')
        generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
        with self.assertRaises(ValueError): generator.compile_type({'oneOf': []}, 'change.schema.json')
