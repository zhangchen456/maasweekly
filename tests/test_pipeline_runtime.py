import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
BASE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(BASE / 'pipeline')); sys.path.insert(0, str(BASE / 'tests')); sys.path.insert(0, str(BASE / 'pipeline/scripts'))
from input_snapshot import capture, load_view, assert_no_pending, PENDING
from run_protocol import RunJournal
from public_export.loaders import load_all
from test_public_export import FixtureRepo
from pricing.base import ContentSnapshot
from pricing.registry import all_entries
from pricing.runner import collect

def snapshot(source, when=1800000000):
    content = (BASE / 'tests/fixtures/pricing' / (source.split(':')[0] + '_pricing.html')).read_text()
    return ContentSnapshot(snapshot_id='fixed', source_key=source, url='https://example.com', fetched_at=when,
                           http_status=200, content_type='text/html', sha256=hashlib.sha256(content.encode()).hexdigest(), content=content)

class PipelineRuntimeTests(unittest.TestCase):
    def setUp(self): self.fx = FixtureRepo(); self.root = self.fx.root
    def tearDown(self): self.fx.cleanup()
    def test_real_process_crash_keeps_committed_view_and_discard_restores_current(self):
        record = self.fx.add_obs(); before = load_all(self.root, BASE / 'pipeline/config/public_providers.json').records
        code = """import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/pipeline')
from run_protocol import RunJournal
root=Path(sys.argv[2])
with RunJournal(root, 'test', 'run_crash'):
 p=next((root/'data/records').glob('*.json')); d=json.loads(p.read_text()); d['title']='partial'; p.write_text(json.dumps(d))
 os._exit(91)
"""
        result = subprocess.run([sys.executable, '-c', code, str(BASE), str(self.root)])
        self.assertEqual(result.returncode, 91)
        self.assertEqual(load_all(self.root, BASE / 'pipeline/config/public_providers.json').records, before)
        with self.assertRaises(ValueError): assert_no_pending(self.root)
        with self.assertRaises(ValueError):
            with RunJournal(self.root, 'test', 'another'): pass
        with RunJournal(self.root, 'test', 'run_crash', recover=True) as run: run.discard()
        self.assertFalse((self.root / PENDING).exists())
        self.assertEqual(json.loads((self.root / 'data/records' / (record['id'] + '.json')).read_text()), record)
    def test_snapshot_integrity_and_no_duplicate_fact_archives(self):
        bundle = self.fx.add_price(); self.fx.add_obs(); capture(self.root, 'baseline'); view = load_view(self.root)
        target = view.files['data/price-facts/versions/' + bundle['pfv']['version_id'] + '.json']['path']
        self.assertTrue(target.startswith('data/price-facts/versions/'))
        current = self.root / 'data/price-facts/current.json'; current.write_text('{}')
        self.assertTrue(load_all(self.root, BASE / 'pipeline/config/public_providers.json').current['facts'])
        immutable = view.path('data/normalized/source-streams.json'); immutable.write_text('tampered')
        with self.assertRaises(ValueError): load_view(self.root).path('data/normalized/source-streams.json')
    def test_bound_concurrency_and_fetch_retry_only_and_cleanup(self):
        entries = all_entries()[:4]; state = {'active': 0, 'peak': 0, 'calls': {}, 'shutdown': 0}
        class Provider:
            async def fetch(self, spec):
                state['active'] += 1; state['peak'] = max(state['peak'], state['active'])
                try:
                    state['calls'][spec.source_key] = state['calls'].get(spec.source_key, 0) + 1
                    await asyncio.sleep(.01)
                    if spec.source_key == entries[0].source_key and state['calls'][spec.source_key] == 1: raise TimeoutError()
                    return snapshot(spec.source_key)
                finally: state['active'] -= 1
        async def shutdown(): state['shutdown'] += 1
        with patch('pricing.runner.provider_for', return_value=Provider()), patch('pricing.runner.PlaywrightSourceProvider.shutdown', side_effect=shutdown):
            results = asyncio.run(collect(entries, concurrency=2, backoff=0, domain_interval=0))
        self.assertEqual(state['peak'], 2); self.assertEqual(state['active'], 0); self.assertEqual(state['shutdown'], 1)
        self.assertTrue(all(value[4] is None for value in results)); self.assertEqual(results[0][5]['retries'], 1)
        malformed = snapshot(entries[0].source_key); malformed.content = '<html>no price tables</html>'; malformed.sha256 = hashlib.sha256(malformed.content.encode()).hexdigest()
        with patch('pricing.runner.provider_for', side_effect=AssertionError('offline must not network')):
            results = asyncio.run(collect(entries[:1], offline={entries[0].source_key: malformed}, backoff=0, domain_interval=0))
        self.assertIsNotNone(results[0][4]); self.assertEqual(results[0][5]['retries'], 0)
    def test_staged_recovery_preserves_observation_and_no_http(self):
        entry = all_entries()[0]; original = snapshot(entry.source_key)
        try:
            with RunJournal(self.root, 'prices', 'staged') as run:
                run.stage_snapshot(entry.source_key, original, 'original_attempt'); run.source_result(entry.source_key, {'extractorVersion': __import__('pricing.extractors', fromlist=['get_extractor']).get_extractor(entry.source_key).version})
                raise RuntimeError('interrupt after fetch')
        except RuntimeError: pass
        with RunJournal(self.root, 'prices', 'staged', recover=True) as run:
            with patch('pricing.runner.provider_for', side_effect=AssertionError('recover must not fetch')):
                results = asyncio.run(collect([entry], journal=run, domain_interval=0))
            self.assertEqual(results[0][1].fetched_at, original.fetched_at)
            self.assertEqual(results[0][5]['attemptId'], 'original_attempt'); run.finish('success')
    def test_current_cannot_rewind_source_freshness(self):
        spec = importlib.util.spec_from_file_location('prices', BASE / 'pipeline/scripts/fetch-prices.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        current = {'facts': {}, 'sources': {'openai:pricing': {'status': 'ok', 'latest_attempt_at': 200, 'last_success_at': 200}}}
        before = json.loads(json.dumps(current))
        module._update_current(current, [], self.root, [{'source_key': 'openai:pricing', 'status': 'ok', 'latest_attempt_at': 100, 'last_success_at': 100, 'coverage': 'full'}])
        self.assertEqual(current, before)
    def test_price_cli_crash_after_archive_and_recover_twice_offline(self):
        shutil.copytree(BASE / 'pipeline/config', self.root / 'pipeline/config', dirs_exist_ok=True)
        code = '''import importlib.util, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/pipeline'); sys.path.insert(0, sys.argv[1] + '/tests')
from test_pipeline_runtime import snapshot
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('prices_child',Path(sys.argv[1])/'pipeline/scripts/fetch-prices.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Provider:
 async def fetch(self,spec): return snapshot(spec.source_key,time.time())
original=m._commit_archive_plan
def crash(*a,**kw):
 original(*a,**kw); os._exit(88)
m._commit_archive_plan=crash
sys.argv=['prices','--input-root',sys.argv[2],'--only','anthropic','--run-id','cli_crash']
with patch('pricing.runner.provider_for',return_value=Provider()): m.main()
'''
        result = subprocess.run([sys.executable, '-c', code, str(BASE), str(self.root)], stdout=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 88)
        self.assertFalse(load_all(self.root, BASE / 'pipeline/config/public_providers.json').current['facts'])
        journal_file = self.root / 'data/price-runs/staging/cli_crash/journal.json'
        staged = json.loads(journal_file.read_text()); observed = staged['sources']['anthropic:pricing']['snapshot']['fetched_at']
        spec = importlib.util.spec_from_file_location('prices_recovery', BASE / 'pipeline/scripts/fetch-prices.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with patch.object(sys, 'argv', ['prices', '--input-root', str(self.root), '--recover', 'cli_crash']), patch('pricing.runner.provider_for', side_effect=AssertionError('recovery cannot fetch')):
            self.assertEqual(module.main(), 0)
        current = json.loads((self.root / 'data/price-facts/current.json').read_text())
        self.assertEqual(current['sources']['anthropic:pricing']['last_success_at'], observed)
        counts = lambda: (len(list((self.root / 'data/price-facts/versions').glob('*.json'))), len(list((self.root / 'data/price-record-revisions').glob('*/*.json'))))
        before = counts(); version = load_view(self.root).version
        record = self.root / 'data/price-runs' / staged['runDate'] / 'cli_crash.json'
        for index in range(2):
            with patch.object(sys, 'argv', ['prices', '--input-root', str(self.root), '--offline-snapshot', str(record), '--run-id', 'offline_' + str(index)]), patch('pricing.runner.provider_for', side_effect=AssertionError('offline cannot fetch')):
                self.assertEqual(module.main(), 0)
            self.assertEqual(counts(), before)
            self.assertEqual(load_view(self.root).version, version)
        self.assertFalse((self.root / PENDING).exists())
    def test_crash_after_pointer_is_committed_and_discard_forbidden(self):
        self.fx.add_obs()
        try:
            with RunJournal(self.root, 'test', 'after_pointer') as run:
                original = run._complete
                with patch.object(run, '_complete', side_effect=RuntimeError('crash after pointer')): run.finish('success')
        except RuntimeError: pass
        with RunJournal(self.root, 'test', 'after_pointer', recover=True) as run:
            self.assertTrue(run.finalized)
            with self.assertRaises(ValueError): run.discard()
        self.assertFalse((self.root / PENDING).exists())
    def test_synchronous_staged_transport_recovers_without_http(self):
        from staged_fetch import fetch
        try:
            with RunJournal(self.root, 'sources', 'source_crash'):
                self.assertEqual(fetch('https://example.com', lambda: ('captured text', None), version='text-1')[0], 'captured text')
                raise RuntimeError('crash')
        except RuntimeError: pass
        with RunJournal(self.root, 'sources', 'source_crash', recover=True) as run:
            self.assertEqual(fetch('https://example.com', lambda: self.fail('HTTP during recovery'), version='text-1')[0], 'captured text')
            run.finish('success')
    def test_browser_singleflight_context_failure_and_shutdown(self):
        from pricing.providers import PlaywrightSourceProvider
        counters = {'launch': 0, 'contextClosed': 0, 'browserClosed': 0, 'stopped': 0}
        class Context:
            async def new_page(self): raise RuntimeError('new page failed')
            async def close(self): counters['contextClosed'] += 1
        class Browser:
            async def new_context(self, **kw): return Context()
            async def close(self): counters['browserClosed'] += 1
        class Engine:
            async def launch(self, **kw):
                counters['launch'] += 1; await asyncio.sleep(.01); return Browser()
        class Playwright:
            chromium = Engine()
            async def stop(self): counters['stopped'] += 1
        class Start:
            async def start(self): return Playwright()
        async def exercise():
            provider = PlaywrightSourceProvider()
            first, second = await asyncio.gather(provider._ensure_browser(), provider._ensure_browser())
            self.assertIs(first, second)
            with self.assertRaises(RuntimeError): await provider._render_url('https://example.com', 'openai:pricing')
            await provider.shutdown()
        with patch('playwright.async_api.async_playwright', return_value=Start()): asyncio.run(exercise())
        self.assertEqual(counters, {'launch': 1, 'contextClosed': 1, 'browserClosed': 1, 'stopped': 1})
        self.assertIsNone(PlaywrightSourceProvider._browser)
    def test_source_cli_recovery_original_report_and_recovery_bundle(self):
        shutil.copytree(BASE / 'pipeline/config', self.root / 'pipeline/config', dirs_exist_ok=True)
        (self.root / 'pipeline/config/maas_official_sources.json').write_text(json.dumps({'platforms': [{'name': 'OpenAI', 'sources': {'pricing': 'https://openai.com/api/pricing/'}}]}))
        spec = importlib.util.spec_from_file_location('source_cli', BASE / 'pipeline/scripts/fetch_sources.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.configure_root(self.root)
        original = None
        try:
            with RunJournal(self.root, 'sources', 'source_cli') as run, patch.object(sys, 'argv', ['sources']), patch.object(module, '_fetch_page', return_value=('Original document\nA pricing line long enough to count', None)):
                module.main(); original = (self.root / 'data/diff' / (run.data['runDate'] + '.json')).read_bytes()
                raise RuntimeError('crash after report')
        except RuntimeError: pass
        spec = importlib.util.spec_from_file_location('recovery_bundle', BASE / 'scripts/architecture-recovery-bundle.py')
        bundler = importlib.util.module_from_spec(spec); spec.loader.exec_module(bundler)
        bundle = self.root / 'recovery.tar.gz'; self.assertTrue(bundler.bundle(self.root, bundle))
        with tempfile.TemporaryDirectory() as other:
            import tarfile
            with tarfile.open(bundle) as archive: archive.extractall(other, filter='data')
            self.assertEqual(load_all(Path(other), BASE / 'pipeline/config/public_providers.json').records if (Path(other) / 'pipeline/config/source_registry.json').exists() else load_view(Path(other)).version, load_view(self.root).version)
        with RunJournal(self.root, 'sources', 'source_cli', recover=True) as run, patch.object(sys, 'argv', ['sources']), patch.object(module, '_fetch_page', side_effect=AssertionError('network during recovery')):
            module.main(); self.assertEqual((self.root / 'data/diff' / (run.data['runDate'] + '.json')).read_bytes(), original); run.finish('success')
    def test_leaderboard_dry_run_and_recovery_do_not_write_or_refetch(self):
        spec = importlib.util.spec_from_file_location('leaderboards', BASE / 'pipeline/scripts/fetch-leaderboards.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.configure_root(self.root)
        payload = {'meta': {'as_of': '2026-10-01', 'window_end_date': '2026-10-01'}, 'data': [{'app_slug': 'agent', 'app_name': 'Agent', 'model_permaslug': 'openai/gpt-test', 'turn_range': '10-49-turns', 'median_session_cost_usd': .5}]}
        before = set(p.relative_to(self.root) for p in self.root.rglob('*') if p.is_file())
        with patch.object(sys, 'argv', ['leaderboards', '--only', 'session-cost', '--dry-run']), patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}), patch.object(module, '_fetch_json', return_value=(payload, None)), patch.object(module, '_run_logo_check', side_effect=AssertionError('dry logo fetch')):
            self.assertEqual(module.main(), 0)
        self.assertEqual(set(p.relative_to(self.root) for p in self.root.rglob('*') if p.is_file()), before)
        try:
            with RunJournal(self.root, 'leaderboards', 'lb_cli') as run, patch.object(sys, 'argv', ['leaderboards', '--only', 'session-cost']), patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test'}), patch.object(module, '_fetch_json', return_value=(payload, None)), patch.object(module, '_run_logo_check'):
                module.main(); original = (self.root / 'data/derived/leaderboards/openrouter_session_cost.json').read_bytes(); raise RuntimeError('crash')
        except RuntimeError: pass
        with RunJournal(self.root, 'leaderboards', 'lb_cli', recover=True) as run, patch.object(sys, 'argv', ['leaderboards', '--only', 'session-cost']), patch.object(module, '_fetch_json', side_effect=AssertionError('refetch')), patch.object(module, '_run_logo_check'):
            self.assertEqual(module.main(), 0); self.assertEqual((self.root / 'data/derived/leaderboards/openrouter_session_cost.json').read_bytes(), original); run.finish('success')
    def test_discard_quarantines_uncommitted_revision_without_damaging_baseline(self):
        from record_archive import merge_record, validate_archive
        record = self.fx.add_obs(); old = json.loads(json.dumps(record)); updated = {**record, 'title': 'new title'}
        try:
            with RunJournal(self.root, 'test', 'revision_interrupt'):
                merge_record(self.root / 'data/records', self.root / 'data/record-revisions', updated)
                raise RuntimeError('interrupt after revision')
        except RuntimeError: pass
        self.assertEqual(load_all(self.root, BASE / 'pipeline/config/public_providers.json').records, [old])
        with RunJournal(self.root, 'test', 'revision_interrupt', recover=True) as run:
            run.discard()
            self.assertEqual(len(run.data['quarantined']), 1)
        self.assertEqual(validate_archive(self.root / 'data/records', self.root / 'data/record-revisions'), [])
        self.assertEqual(json.loads((self.root / 'data/records' / (old['id'] + '.json')).read_text()), old)
        with RunJournal(self.root, 'test', 'following_run') as run: run.finish('success')
    def test_runtime_checkpoint_cache_bounded_without_fact_archive_cleanup(self):
        self.fx.add_price(); record = self.fx.add_obs()
        from data_store import write
        from input_snapshot import InputView, POINTER
        for index in range(4):
            with RunJournal(self.root, 'test', 'checkpoint_' + str(index)) as run:
                write(self.root, 'data/normalized/cache-test.json', {'round': index})
                run.finish('success')
        pointer = json.loads((self.root / POINTER).read_text())
        self.assertEqual(len(list((self.root / 'data/input-manifests').glob('*.json'))), 2)
        previous = InputView(self.root, {'schemaVersion': 1, 'inputVersion': pointer['previousInputVersion'], 'manifestPath': 'data/input-manifests/' + pointer['previousInputVersion'] + '.json'})
        self.assertEqual(json.loads(previous.path('data/normalized/cache-test.json').read_text()), {'round': 2})
        self.assertTrue(load_all(self.root, BASE / 'pipeline/config/public_providers.json').current['facts'])
        self.assertTrue((self.root / 'data/record-revisions' / record['id'] / '1.json').exists())
