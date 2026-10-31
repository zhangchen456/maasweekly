import importlib.util
from pathlib import Path
from datetime import date
import unittest
spec=importlib.util.spec_from_file_location('health',Path(__file__).parents[1]/'ops/check-formal-weekly.py')
health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health)
class HealthTests(unittest.TestCase):
    def test_recent_formal_report(self):
        self.assertEqual(health.check([{'date':'2026-10-27'}],date(2026,10,31))['ageDays'],4)
    def test_rolling_success_does_not_hide_old_formal_report(self):
        with self.assertRaisesRegex(ValueError,'overdue'):health.check([{'date':'2026-10-13'}],date(2026,10,31))
    def test_missing(self):
        with self.assertRaises(ValueError):health.check([],date(2026,10,31))
    def test_future(self):
        with self.assertRaises(ValueError):health.check([{'date':'2026-11-03'}],date(2026,10,31))
