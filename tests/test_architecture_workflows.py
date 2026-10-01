"""AR-05: actual workflow graphs and isolated Git writer/candidate scenarios."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

BASE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('workflow_policy', BASE / 'scripts/workflow-policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def workflow(name):
    return yaml.load((BASE / '.github/workflows' / (name + '.yml')).read_text(), Loader=yaml.BaseLoader)


class WorkflowGraph(unittest.TestCase):
    def test_independent_writer_and_release_locks_have_no_parent_self_lock(self):
        for name, job in [('daily-update', 'update-and-deploy'), ('weekly-update', 'weekly')]:
            doc = workflow(name)
            self.assertNotIn('concurrency', doc)
            writer = doc['jobs'][job]
            self.assertEqual(writer['concurrency'], {'group': 'maas-data-write-main', 'cancel-in-progress': 'false', 'queue': 'max'})
            publish = doc['jobs']['deploy']
            self.assertEqual(publish['needs'], job)
            self.assertEqual(publish['uses'], './.github/workflows/release-deploy.yml')
            self.assertIn('outputs.sha', publish['with']['commit'])
            self.assertNotIn('concurrency', publish)
        deploy = workflow('release-deploy')['jobs']['deploy']
        self.assertEqual(deploy['concurrency']['group'], 'maas-production-deploy-main')
        self.assertEqual(deploy['concurrency']['cancel-in-progress'], 'false')
        self.assertEqual(deploy['concurrency']['queue'], 'max')
        self.assertEqual(deploy['env']['MAAS_VERIFY_MAIN_CANDIDATE'], '1')

    def test_push_and_weekly_markdown_have_a_single_responsible_publish_path(self):
        doc = workflow('deploy')['jobs']
        self.assertEqual(doc['import-weekly']['uses'], './.github/workflows/weekly-update.yml')
        self.assertEqual(doc['import-weekly']['with']['mode'], 'import')
        self.assertIn("import_weekly != 'true'", doc['deploy']['if'])
        for paths, deploy, weekly in [
            (['data/records/manual.json'], True, False), (['site/src/content/weekly/x.md'], True, False),
            (['data/weekly/2026-10-01.md'], True, True), (['docs/design.md'], False, False),
            (['README.md'], False, False), (['contracts/schema.json'], True, False),
            (['pipeline/a.py', 'data/weekly/x.md'], True, True), (['.github/workflows/deploy.yml'], True, False),
        ]:
            self.assertEqual(policy.classify(paths), {'deploy': deploy, 'importWeekly': weekly})

    def test_verify_uses_exact_deployed_rid_not_directory_mtime(self):
        steps = workflow('release-deploy')['jobs']['deploy']['steps']
        verify = next(s for s in steps if s['name'].startswith('Online verify'))
        self.assertEqual(verify['if'], "steps.deploy.outputs.deployed == 'true'")
        self.assertEqual(verify['env']['RELEASE_ID'], '${{ steps.deploy.outputs.rid }}')
        self.assertNotIn('ls -td', (BASE / 'ops/deploy-release.sh').read_text())


class IsolatedGit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ar05-git-')
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        self.command(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.a = self.clone('a')
        (self.a / 'base.txt').write_text('initial')
        self.commit(self.a, 'initial')
        self.command(self.a, 'push', 'origin', 'HEAD:main')
        self.b = self.clone('b')

    def tearDown(self):
        self.temp.cleanup()

    def command(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL, text=True).strip()

    def clone(self, name):
        target = self.root / name
        self.command(self.root, 'clone', str(self.remote), str(target))
        self.command(target, 'config', 'user.name', 'architecture test')
        self.command(target, 'config', 'user.email', 'test@example.invalid')
        return target

    def commit(self, repo, message):
        self.command(repo, 'add', '.')
        self.command(repo, 'commit', '-m', message)
        return self.command(repo, 'rev-parse', 'HEAD')

    def writer(self, repo):
        output = self.root / 'output.txt'
        return subprocess.run(['bash', str(BASE / 'scripts/commit-workflow-data.sh'), 'data test'],
            cwd=repo, env={**os.environ, 'GITHUB_OUTPUT': str(output)}, capture_output=True, text=True)

    def test_local_release_selection_ignores_newer_unrelated_output_mtime(self):
        import shutil
        repo = self.a
        (repo / 'ops').mkdir(); (repo / 'scripts').mkdir(); (repo / 'data/public/v1').mkdir(parents=True)
        for name in ['deploy-release.sh', 'lib-release.sh']:
            shutil.copyfile(BASE / 'ops' / name, repo / 'ops' / name)
        version = 'ds_' + 'a' * 64
        (repo / 'data/public/v1/manifest.json').write_text(json.dumps({'datasetVersion': version}))
        builder = repo / 'scripts/build-release.sh'
        builder.write_text("""#!/usr/bin/env bash
set -euo pipefail
RID="rl_$(git rev-parse --short=10 HEAD)_aaaaaaaaaaaa"
mkdir -p "dist-release/$RID/metadata"
printf '{"testsSkipped": false}' > "dist-release/$RID/metadata/release-manifest.json"
""")
        builder.chmod(0o755)
        self.commit(repo, 'test builder')
        unrelated = repo / 'dist-release/rl_bbbbbbbbbb_bbbbbbbbbbbb'
        unrelated.mkdir(parents=True); os.utime(unrelated, (4102444800, 4102444800))
        expected = 'rl_' + self.command(repo, 'rev-parse', '--short=10', 'HEAD') + '_aaaaaaaaaaaa'
        result = subprocess.run(['bash', 'ops/deploy-release.sh', '--local-only'], cwd=repo,
            env={**os.environ, 'MAAS_DEPLOY_MODE': 'release'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(expected + ' 已构建', result.stdout)
        self.assertNotIn('rl_bbbbbbbbbb_bbbbbbbbbbbb', result.stdout)

    def test_daily_weekly_collision_exits_and_regeneration_preserves_both_inputs(self):
        (self.a / 'daily.json').write_text('daily'); self.command(self.a, 'add', '.')
        self.assertEqual(self.writer(self.a).returncode, 0)
        (self.b / 'weekly.json').write_text('weekly'); self.command(self.b, 'add', '.')
        conflict = self.writer(self.b)
        self.assertEqual(conflict.returncode, 75)
        self.assertIn('regenerate', conflict.stderr)
        # Only a disposable test checkout is reset; production scripts never
        # automatically discard or rebase generated changes.
        self.command(self.b, 'reset', '--hard', 'origin/main')
        (self.b / 'weekly.json').write_text('weekly'); self.command(self.b, 'add', '.')
        self.assertEqual(self.writer(self.b).returncode, 0)
        self.assertEqual((self.b / 'daily.json').read_text(), 'daily')
        self.assertEqual((self.b / 'weekly.json').read_text(), 'weekly')
        sha = self.command(self.b, 'rev-parse', 'HEAD')
        self.assertIn('sha=' + sha, (self.root / 'output.txt').read_text())

    def test_code_push_during_collection_is_not_rebased_into_a_stale_projection(self):
        (self.a / 'projection.json').write_text('based on old code'); self.command(self.a, 'add', '.')
        (self.b / 'server.ts').write_text('new code'); self.commit(self.b, 'code')
        self.command(self.b, 'push', 'origin', 'HEAD:main')
        self.assertEqual(self.writer(self.a).returncode, 75)
        self.assertEqual(self.command(self.a, 'show', 'origin/main:server.ts'), 'new code')
        self.assertNotIn('projection.json', self.command(self.a, 'ls-tree', '--name-only', 'origin/main'))

    def test_out_of_order_runtime_candidate_is_skipped_but_later_docs_are_harmless(self):
        old = self.command(self.a, 'rev-parse', 'HEAD')
        (self.a / 'server.ts').write_text('new runtime'); new = self.commit(self.a, 'runtime')
        self.command(self.a, 'push', 'origin', 'HEAD:main')
        self.command(self.a, 'checkout', old)
        self.assertFalse(policy.candidate(self.a, old, 'origin/main')['eligible'])
        self.command(self.a, 'checkout', new)
        (self.a / 'README.md').write_text('documentation'); self.commit(self.a, 'docs')
        self.command(self.a, 'push', 'origin', 'HEAD:main')
        self.command(self.a, 'checkout', new)
        self.assertTrue(policy.candidate(self.a, new, 'origin/main')['eligible'])
        self.command(self.a, 'checkout', '-b', 'unapproved')
        (self.a / 'server.ts').write_text('future timestamp irrelevant'); side = self.commit(self.a, 'side')
        self.assertFalse(policy.candidate(self.a, side, 'origin/main')['eligible'])
        self.assertFalse(policy.candidate(self.a, 'main', 'origin/main')['eligible'])


class BuildIsolation(unittest.TestCase):
    def test_failed_suite_retains_real_exit_and_log_and_success_removes_logs(self):
        prefix = (BASE / 'scripts/run-all-tests.sh').read_text().split('\necho "══', 1)[0]
        with tempfile.TemporaryDirectory(prefix='ar05-logs-') as directory:
            root = Path(directory)
            script = root / 'runner.sh'
            script.write_text(prefix + """
run "sentinel" bash -c 'echo sentinel-failure; exit 23'
SUITE_FINISHED=true
exit 1
""")
            result = subprocess.run(['bash', str(script)], env={**os.environ, 'TMPDIR': directory}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('退出码 23', result.stdout)
            logs = list(root.glob('maas-regression.*/1.txt'))
            self.assertEqual(len(logs), 1)
            self.assertIn('sentinel-failure', logs[0].read_text())
            subprocess.run(['rm', '-rf', str(logs[0].parent)], check=True)
            script.write_text(prefix + '\nrun "sentinel" true\nSUITE_FINISHED=true\nexit 0\n')
            result = subprocess.run(['bash', str(script)], env={**os.environ, 'TMPDIR': directory}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(list(root.glob('maas-regression.*')), [])

    def test_dependency_fingerprint_requires_reinstall_after_lock_change_or_incomplete_cache(self):
        with tempfile.TemporaryDirectory(prefix='ar05-deps-') as directory:
            root = Path(directory); binaries = root / 'bin'; binaries.mkdir()
            package = root / 'package'; package.mkdir()
            (package / 'package-lock.json').write_text('{}')
            fake = binaries / 'npm'
            fake.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo 10.0.0; exit 0; fi\necho install >> installs.txt\nmkdir -p node_modules/.bin\ntouch node_modules/.bin/tsc\n')
            fake.chmod(0o755)
            command = ['node', str(BASE / 'scripts/ensure-node-deps.mjs'), str(package)]
            environment = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH']}
            def install():
                subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
                return len((package / 'installs.txt').read_text().splitlines())
            self.assertEqual(install(), 1); self.assertEqual(install(), 1)
            (package / 'package-lock.json').write_text('{"changed": true}')
            self.assertEqual(install(), 2)
            (package / 'node_modules/.bin/tsc').unlink()
            self.assertEqual(install(), 3)


if __name__ == '__main__':
    unittest.main()
