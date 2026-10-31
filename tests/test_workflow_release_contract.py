"""Current publishing contract: daily data updates never build or commit code."""
import unittest,yaml
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
def doc(name):return yaml.load((BASE/'.github/workflows'/name).read_text(),Loader=yaml.BaseLoader)
class IndependentPublicationTests(unittest.TestCase):
 def test_data_workflows_have_readonly_git_and_no_build_or_commit(self):
  for name in ['daily-update.yml','weekly-update.yml']:
   workflow=doc(name);self.assertEqual(workflow['permissions']['contents'],'read')
   text=(BASE/'.github/workflows'/name).read_text()
   for forbidden in ['git add','git commit','git push','npm run build','release-deploy.yml','build-release.sh']:
    self.assertNotIn(forbidden,text,name)
   jobs=list(workflow['jobs'].values());self.assertEqual(len(jobs),1)
   self.assertEqual(jobs[0]['concurrency'],{'group':'maas-data-write-main','cancel-in-progress':'false','queue':'max'})
   self.assertIn('ops/request-data-update.py',text)
 def test_data_client_only_sends_fixed_action_and_credentials_over_stdin(self):
  source=(BASE/'ops/request-data-update.py').read_text()
  self.assertIn("'data-update'",source);self.assertIn('input=body',source)
  self.assertNotIn('shell=True',source);self.assertNotIn('git commit',source)
 def test_skip_fetch_rebuilds_published_data_without_code_deployment(self):
  source=(BASE/'.github/workflows/daily-update.yml').read_text()
  self.assertIn('MODE=rebuild',source);self.assertIn('SKIP_FETCH',source)
 def test_code_workflow_builds_no_business_archive_and_checks_linux_before_switch(self):
  text=(BASE/'.github/workflows/release-deploy.yml').read_text()
  self.assertIn('build-runtime-release.sh',text);self.assertNotIn('scripts/build-release.sh',text)
  self.assertIn('runtime-activate',text);self.assertIn('workflow-policy.py candidate',text)
  source=(BASE/'ops/runtime-control.py').read_text()
  self.assertLess(source.index('verify-runtime-site.mjs'),source.index("stage(manifest['codeCommit'])"))
 def test_weekly_import_follows_successful_code_deployment(self):
  jobs=doc('deploy.yml')['jobs'];self.assertEqual(jobs['import-weekly']['needs'],['changes','deploy'])
  self.assertEqual(jobs['import-weekly']['with']['mode'],'import')
  self.assertIn("needs.deploy.result == 'skipped'",jobs['import-weekly']['if'])
 def test_server_keeps_data_visibility_atomic_and_requires_exact_old_pointer(self):
  source=(BASE/'pipeline/data_publication.py').read_text()
  self.assertIn('publication compare-and-swap failed',source)
  self.assertLess(source.index("failpoint('after_prepare')"),source.index('durable_write(pointer,body)'))
  source=(BASE/'ops/data-writer/launch.py').read_text()
  self.assertLess(source.index('verify-runtime-site.mjs'),source.index("journal.phase('publication'"))
if __name__=='__main__':unittest.main()
