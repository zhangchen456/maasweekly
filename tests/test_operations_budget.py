import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('budget', ROOT / 'scripts/operations-budget.py')
budget = importlib.util.module_from_spec(spec); spec.loader.exec_module(budget)
POLICY = json.loads((ROOT / 'ops/resource-budget.json').read_text())


class OperationsBudgetTest(unittest.TestCase):
    def test_boundaries_and_missing_measurements(self):
        x = budget.evaluate({'metrics': {'diskUsedPercent': 80, 'diskAvailableBytes': 1073741824}}, POLICY)
        results = {r['metric']: r['state'] for r in x['results']}
        self.assertEqual(results['diskUsedPercent'], 'warning')
        self.assertEqual(results['diskAvailableBytes'], 'critical')
        self.assertEqual(results['serviceMemoryPeakBytes'], 'unmeasured')
        self.assertEqual(len(x['alerts']), 2)

    def test_invalid_or_nonfinite_samples_cannot_pass(self):
        for value in [True, '100', float('nan'), float('inf'), -1]:
            with self.assertRaises(ValueError): budget.evaluate({'metrics': {'diskUsedPercent': value}}, POLICY)


if __name__ == '__main__':
    unittest.main()
