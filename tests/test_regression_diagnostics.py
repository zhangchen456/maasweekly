"""Execute the actual regression runner with an early failure and a long tail."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/run-all-tests.sh'
PRELUDE = SCRIPT.read_text().split('echo "══ Task 01–06 统一回归 ══"')[0]


class RegressionDiagnosticsTest(unittest.TestCase):
    def run_probe(self, body, log_root):
        return subprocess.run(['bash', '-c', PRELUDE + body, str(SCRIPT)],
                              cwd=ROOT, text=True, capture_output=True,
                              env={**os.environ, 'MAAS_REGRESSION_LOG_ROOT': str(log_root)})

    def test_early_assertion_retained_and_failure_remains_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_probe('''
run "early failure" bash -c 'echo "not ok 1 - early assertion"; echo "expected: 200 actual: 503"; for i in {1..80}; do echo "later successful output $i"; done; exit 23'
SUITE_FINISHED=true
[ "${#FAILED[@]}" -eq 0 ] || exit 1
''', Path(temp))
            self.assertEqual(result.returncode, 1)
            self.assertIn('not ok 1 - early assertion', result.stdout)
            self.assertIn('expected: 200 actual: 503', result.stdout)
            self.assertIn('later successful output 80', result.stdout)
            logs = list(Path(temp).glob('maas-regression.*/*.txt'))
            self.assertEqual(len(logs), 1)
            self.assertTrue(logs[0].read_text().startswith('not ok 1'))
            self.assertEqual(logs[0].with_suffix('.txt.meta').read_text(),
                             'suite=early failure\nexitCode=23\n')

    def test_success_cleans_logs_and_interruption_retains_started_output(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.run_probe('run "ok" true\nSUITE_FINISHED=true\n', Path(temp)).returncode, 0)
            self.assertEqual(list(Path(temp).iterdir()), [])
            result = self.run_probe('run "interrupted" bash -c \'echo begun; exit 143\'\nexit 143\n', Path(temp))
            self.assertEqual(result.returncode, 143)
            self.assertEqual(len(list(Path(temp).glob('maas-regression.*/*.txt'))), 1)

    def test_workflow_archives_failure_logs_even_after_failed_build(self):
        workflow = (ROOT / '.github/workflows/release-deploy.yml').read_text()
        self.assertIn('MAAS_REGRESSION_LOG_ROOT: ${{ runner.temp }}/regression-failures', workflow)
        job_env = workflow.split('    steps:')[0]
        self.assertNotIn('runner.temp', job_env)
        build = workflow.split('- name: Build release and deploy')[1].split('- name: Online verify')[0]
        self.assertIn('MAAS_REGRESSION_LOG_ROOT:', build)
        archive = workflow.split('- name: Archive release diagnostics')[1]
        self.assertIn('if: always()', archive)
        self.assertIn('${{ runner.temp }}/regression-failures/', archive)


if __name__ == '__main__':
    unittest.main()
