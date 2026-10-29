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
 def test_browser_does_not_inherit_provider_credentials(self):
  with patch.dict(os.environ,{'LLM_API_KEY':'secret','TRANSLATION_API_KEY':'secret2','OPENROUTER_API_KEY':'secret3'}),patch.object(writer.subprocess,'run') as run:
   run.return_value.returncode=0;writer.step('pipeline/scripts/fetch_sources.py')
   self.assertFalse(writer.ALLOWED.intersection(run.call_args.kwargs['env']))
   writer.step('pipeline/scripts/llm-digest.py',credentials={'LLM_API_KEY':'scoped'})
   env=run.call_args.kwargs['env'];self.assertEqual(env['LLM_API_KEY'],'scoped');self.assertNotIn('TRANSLATION_API_KEY',env)
if __name__=='__main__':unittest.main()
