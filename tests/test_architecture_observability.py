import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('diagnostics', Path(__file__).resolve().parents[1] / 'scripts/architecture-observability.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class DiagnosticsTests(unittest.TestCase):
    def test_fixed_route_and_status_percentiles(self):
        events = [{'kind': 'api.request', 'route': '/private/secret', 'statusCode': s, 'elapsedMs': n} for n, s in enumerate([200, 429, 409, 500, 503, 500])]
        report = module.aggregate(events)
        self.assertEqual(report['routes']['unknown']['p95Ms'], 5)
        self.assertEqual(report['routes']['unknown']['429'], 1)
        self.assertEqual(report['routes']['unknown']['409'], 1)
        self.assertIn('api:5xx:unknown', report['activeAlerts'])
        self.assertNotIn('secret', str(report))
    def test_failure_skip_dedupe_and_recovery(self):
        def source(n, outcome): return {'kind': 'pipeline.source', 'sourceId': 'test', 'runId': 'run', 'attemptId': n, 'outcome': outcome}
        failed = [source(1, 'failed'), source(1, 'failed'), source(2, 'not_run'), source(3, 'failed')]
        report = module.aggregate(failed)
        self.assertEqual(report['activeAlerts'], {'source:test': 'two_failed_attempts'})
        self.assertEqual(module.aggregate(failed, report)['transitions'], [])
        for outcome in ('success', 'unchanged'):
            recovered = module.aggregate(failed + [source(4, outcome)], report)
            self.assertEqual(recovered['transitions'], [{'key': 'source:test', 'state': 'recovered'}])
    def test_health_load_candidate_and_drop(self):
        events = [{'kind': 'runtime.sample', 'health': {'ready': True, 'freshness': 'stale'}}, {'kind': 'dataset.load', 'result': 'failed'}, {'kind': 'release.result', 'outcome': 'failed'}, {'kind': 'pipeline.source', 'sourceId': 'test', 'attemptId': 1, 'outcome': 'success', 'countRatio': 0.3}]
        report = module.aggregate(events)
        self.assertNotIn('api:ready', report['activeAlerts'])
        self.assertEqual(len(report['activeAlerts']), 4)
        events += [{'kind': 'runtime.sample', 'health': {'ready': True, 'freshness': 'fresh'}}, {'kind': 'dataset.load', 'result': 'changed'}, {'kind': 'release.result', 'outcome': 'success'}, {'kind': 'pipeline.source', 'sourceId': 'test', 'attemptId': 2, 'outcome': 'success', 'countRatio': 1}]
        self.assertEqual(module.aggregate(events, report)['activeAlerts'], {})

    def test_real_build_preflight_outcome_and_disable(self):
        import os, shutil, subprocess, tempfile
        base = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='ar08-build-') as temp:
            root = Path(temp)
            def git(*args): subprocess.run(['git', '-C', temp, *args], check=True, capture_output=True)
            git('init'); git('config', 'user.name', 'test'); git('config', 'user.email', 'test@example.invalid')
            (root/'tracked').write_text('one'); git('add', '.'); git('commit', '-m', 'fixture')
            env = {**os.environ, 'MAAS_RELEASE_REPO': temp}
            def run(): return subprocess.run(['bash', str(base/'scripts/build-release.sh'), '--preflight-only'], env=env, capture_output=True, text=True)
            clean = run(); self.assertEqual(clean.returncode, 0)
            import json
            events = [json.loads(line) for line in clean.stderr.splitlines() if line.startswith('{')]
            self.assertEqual(events[-1]['kind'], 'release.result'); self.assertEqual(events[-1]['outcome'], 'success')
            self.assertEqual(len(events[-1]['gitCommit']), 40)
            (root/'tracked').write_text('two')
            failed = run(); self.assertEqual(failed.returncode, 1)
            bad = [json.loads(line) for line in failed.stderr.splitlines() if line.startswith('{')]
            state = module.aggregate(bad); self.assertIn('release:preflight', state['activeAlerts'])
            self.assertEqual(module.aggregate(bad, state)['transitions'], [])
            self.assertEqual(module.aggregate(events, state)['transitions'], [{'key':'release:preflight','state':'recovered'}])
            env['MAAS_RELEASE_DIAGNOSTICS']='0'
            disabled = run(); self.assertEqual(disabled.returncode, 1); self.assertNotIn('release.result', disabled.stderr)

    def test_operations_do_not_clear_other_release_failure(self):
        state = module.aggregate([{'kind':'release.result','operation':'activate','outcome':'failed'}])
        report = module.aggregate([{'kind':'release.result','operation':'build','outcome':'success'}], state)
        self.assertIn('release:activate', report['activeAlerts'])
        self.assertEqual(report['transitions'], [])

    def test_mixed_window_overflow_preserves_previous_state(self):
        import json, subprocess, sys, tempfile
        with tempfile.TemporaryDirectory(prefix='ar08-window-') as temp:
            root=Path(temp); log=root/'log'; state=root/'state'
            state.write_text('{"activeAlerts":{}}')
            log.write_text('normal build text\n{not json\n'+json.dumps({'kind':'release.result','outcome':'failed'})+'\n')
            script=Path(module.__file__)
            run=subprocess.run([sys.executable,str(script),str(log),'--mixed','--state',str(state),'--max-events','0'],capture_output=True)
            self.assertNotEqual(run.returncode,0); self.assertEqual(state.read_text(),'{"activeAlerts":{}}')
