import importlib.util,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'pipeline'))
spec=importlib.util.spec_from_file_location('database_writer',BASE/'ops/data-writer/run.py');writer=importlib.util.module_from_spec(spec);spec.loader.exec_module(writer)
class WriterEnvelopeTests(unittest.TestCase):
 def test_request_rejects_arbitrary_environment_or_mode(self):
  for value in [{'mode':'update','secrets':{'PATH':'evil'}},{'mode':'shell'},{'mode':'update','secrets':{'LLM_API_KEY':'bad\0value'}},{'mode':'update','command':'rm'}]:
   with self.assertRaises(ValueError):writer.request(json.dumps(value).encode())
  self.assertEqual(writer.request(b'{"mode":"validate"}')['mode'],'validate')
 def test_ready_cache_reconstructs_mutable_files_from_committed_view(self):
  sys.path.insert(0,str(BASE/'tests'))
  from test_public_export import FixtureRepo
  from input_snapshot import capture
  fixture=FixtureRepo();self.addCleanup(fixture.cleanup)
  version=capture(fixture.root,'writer-cache-fixture')
  mutable=fixture.root/'data/normalized/source-streams.json';original=mutable.read_bytes();mutable.unlink()
  with patch.object(writer,'CODE',fixture.root),patch.object(writer,'WORK',fixture.root):writer.initialize(None,{'site':{'inputVersion':version}},None)
  self.assertEqual(mutable.read_bytes(),original)
 def test_browser_does_not_inherit_provider_credentials(self):
  with patch.dict(os.environ,{'LLM_API_KEY':'secret','TRANSLATION_API_KEY':'secret2','OPENROUTER_API_KEY':'secret3'}),patch.object(writer.subprocess,'run') as run:
   run.return_value.returncode=0;writer.step('pipeline/scripts/fetch_sources.py')
   self.assertFalse(writer.ALLOWED.intersection(run.call_args.kwargs['env']))
   writer.step('pipeline/scripts/llm-digest.py',credentials={'LLM_API_KEY':'scoped'})
   env=run.call_args.kwargs['env'];self.assertEqual(env['LLM_API_KEY'],'scoped');self.assertNotIn('TRANSLATION_API_KEY',env)

@unittest.skipUnless(os.environ.get('MAAS_SHADOW_TEST_DSN'),'isolated PostgreSQL DSN required')
class WriterIngestTests(unittest.TestCase):
 from test_shadow_store import ShadowTests as _Fixture
 setUp=_Fixture.setUp
 tearDown=_Fixture.tearDown
 write=_Fixture.write
 def test_completed_logs_do_not_replace_raw_recovery_manifest(self):
  log=self.root/'data/price-runs/2026-10-29/fixture.json';log.parent.mkdir(parents=True);log.write_text('{"state":"committed","runId":"fixture"}\n')
  with patch.object(writer,'CODE',self.root),patch.object(writer,'WORK',self.root),patch.object(writer,'STORE',self.base),patch.dict(os.environ,{'MAAS_DATA_DSN':os.environ['MAAS_SHADOW_TEST_DSN']}):
   writer.ingest(self.version,'a'*40)
  with self.connection.cursor() as cursor:
   cursor.execute('SELECT manifest FROM maas_data.input_raw_manifests WHERE input_version=%s',[self.version]);manifest=cursor.fetchone()[0]
   self.assertEqual(manifest['scope'],'raw-snapshots-local-drill')
   cursor.execute('SELECT payload_json FROM maas_data.writer_run_logs WHERE logical_path=%s',[str(log.relative_to(self.root))]);self.assertEqual(cursor.fetchone()[0],log.read_text())
  self.assertEqual(json.loads((self.root/'ingestion.json').read_text())['inputVersion'],self.version)

if __name__=='__main__':unittest.main()
