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
        recovered = module.aggregate(failed + [source(4, 'success')], report)
        self.assertEqual(recovered['transitions'], [{'key': 'source:test', 'state': 'recovered'}])
    def test_health_load_candidate_and_drop(self):
        events = [{'kind': 'runtime.sample', 'health': {'ready': True, 'freshness': 'stale'}}, {'kind': 'dataset.load', 'result': 'failed'}, {'kind': 'release.result', 'outcome': 'failed'}, {'kind': 'pipeline.source', 'sourceId': 'test', 'attemptId': 1, 'outcome': 'success', 'countRatio': 0.3}]
        report = module.aggregate(events)
        self.assertNotIn('api:ready', report['activeAlerts'])
        self.assertEqual(len(report['activeAlerts']), 4)
        events += [{'kind': 'runtime.sample', 'health': {'ready': True, 'freshness': 'fresh'}}, {'kind': 'dataset.load', 'result': 'changed'}, {'kind': 'release.result', 'outcome': 'success'}, {'kind': 'pipeline.source', 'sourceId': 'test', 'attemptId': 2, 'outcome': 'success', 'countRatio': 1}]
        self.assertEqual(module.aggregate(events, report)['activeAlerts'], {})
