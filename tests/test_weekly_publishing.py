import hashlib,importlib.util,json,os,sys,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(BASE/'pipeline'),str(BASE/'tests')]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,BASE/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
editorial=module('weekly_editorial','ops/weekly-editorial.py')
writer=module('weekly_writer','ops/data-writer/run.py')
importer=module('weekly_importer','site/scripts/import-weekly.py')
class WeeklyPublishingTests(unittest.TestCase):
 def test_complete_tuesday_period_never_includes_today(self):
  for day in ['2026-10-28','2026-10-31','2026-11-03']:
   self.assertEqual(editorial.period(date.fromisoformat(day)),(date(2026,10,21),date(2026,10,27)))
  self.assertEqual(editorial.period(date(2026,11,4))[1],date(2026,11,3))
 def test_pagination_preserves_version_and_inclusive_last_day(self):
  calls=[]
  def fetch(url):
   calls.append(url)
   return {'datasetVersion':'ds_fixture','coverage':{},'items':[{'id':str(len(calls)),'observationDate':'2026-10-27'}],'page':{'nextCursor':'next' if len(calls)==1 else None}}
  result=editorial.collect('https://example.test',date(2026,10,21),date(2026,10,27),fetch)
  self.assertEqual(len(result['observations']),2);self.assertIn('to=2026-10-28',calls[0]);self.assertEqual(calls[1],'https://example.test/changes?cursor=next')
  pages=iter([{'datasetVersion':'a','coverage':{},'items':[],'page':{'nextCursor':'x'}},{'datasetVersion':'b','coverage':{},'items':[],'page':{'nextCursor':None}}])
  with self.assertRaisesRegex(ValueError,'dataset changed'):editorial.collect('https://example.test',date(2026,10,21),date(2026,10,27),lambda _:next(pages))
 def test_review_is_bound_to_exact_draft_and_required_checks(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'2026-10-27.md';p.write_bytes((BASE/'data/weekly/2026-10-27.md').read_bytes());r=Path(temp)/'receipt.json';meta=json.loads((BASE/'docs/weekly-reviews/2026-10-27.json').read_text());r.write_text(json.dumps(meta))
   self.assertEqual(editorial.check(p,r,date(2026,10,31))['evidenceCount'],5)
   p.write_text(p.read_text()+'\nchanged')
   with self.assertRaisesRegex(ValueError,'changed since'):editorial.check(p,r,date(2026,10,31))
   meta['draftSha256']=hashlib.sha256(p.read_bytes()).hexdigest();meta['checks']['englishPrivate']=False;r.write_text(json.dumps(meta))
   with self.assertRaisesRegex(ValueError,'incomplete'):editorial.check(p,r,date(2026,10,31))
 def test_unfinished_period_and_placeholder_are_rejected(self):
  p=BASE/'data/weekly/2026-10-27.md';r=BASE/'docs/weekly-reviews/2026-10-27.json'
  with self.assertRaisesRegex(ValueError,'unfinished observation'):editorial.check(p,r,date(2026,10,27))
  with tempfile.TemporaryDirectory() as temp:
   target=Path(temp)/p.name;target.write_text(p.read_text()+'\nTODO');meta=json.loads(r.read_text());meta['draftSha256']=hashlib.sha256(target.read_bytes()).hexdigest();receipt=Path(temp)/'review.json';receipt.write_text(json.dumps(meta))
   with self.assertRaisesRegex(ValueError,'placeholder'):editorial.check(target,receipt,date(2026,10,31))
 def test_formal_import_skips_summary_and_zero_pending_translation_writes(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(writer,'WORK',Path(temp)),patch.object(writer,'step',return_value=0) as step:
   writer.import_formal([],{'LLM_API_KEY':'not-used'})
   self.assertEqual([c.args[0] for c in step.call_args_list],['site/scripts/import-weekly.py','pipeline/scripts/translate-dynamic-en.py'])
   self.assertTrue(step.call_args_list[0].kwargs['pinned']);self.assertEqual(step.call_args_list[1].args[1],['--check'])
 def test_pending_translation_must_finish_and_errors_fail_closed(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(writer,'WORK',Path(temp)),patch.object(writer,'step',side_effect=[0,1,0,0]) as step:
   writer.import_formal([],{'TRANSLATION_API_KEY':'scoped'});self.assertEqual(step.call_count,4)
  for result in [1,2]:
   with tempfile.TemporaryDirectory() as temp,patch.object(writer,'WORK',Path(temp)),patch.object(writer,'step',side_effect=[0,result]):
    with self.assertRaises((ValueError,RuntimeError)):writer.import_formal([],{})
 def test_cache_restore_limits_mutation_to_mutable_inputs_and_keeps_final_archive_checks(self):
  from test_public_export import FixtureRepo
  from input_snapshot import capture,load_view,restore_mutable,role_files
  fx=FixtureRepo();self.addCleanup(fx.cleanup);root=fx.root
  record=fx.add_obs();capture(root,'baseline');view=load_view(root)
  archive=root/f"data/record-revisions/{record['id']}/{record['revision']}.json";before=archive.read_bytes()
  mutable=root/'data/normalized/source-streams.json';expected=mutable.read_bytes();mutable.write_text('{}')
  stray=root/'data/derived/uncommitted.json';stray.write_text('{}')
  restore_mutable(root,view)
  self.assertEqual(mutable.read_bytes(),expected);self.assertFalse(stray.exists());self.assertEqual(archive.read_bytes(),before)
  self.assertNotIn(str(archive.relative_to(root)),role_files(root,mutable_only=True))
  archive.write_text('{}')
  with self.assertRaisesRegex(ValueError,'current record differs'):capture(root,'must-not-publish-corruption')
 def test_actual_import_cli_commits_new_draft_and_projection_together(self):
  import subprocess
  from test_public_export import FixtureRepo
  from input_snapshot import capture,load_view
  fx=FixtureRepo();self.addCleanup(fx.cleanup);capture(fx.root,'baseline')
  with tempfile.TemporaryDirectory() as temp:
   raw=json.dumps([{'date':'2026-10-27','markdown':(BASE/'data/weekly/2026-10-27.md').read_text()}]).encode();request=Path(temp)/(hashlib.sha256(raw).hexdigest()+'.json');request.write_bytes(raw)
   result=subprocess.run([sys.executable,str(BASE/'site/scripts/import-weekly.py'),'--input-root',str(fx.root),'--drafts-file',str(request)],env={**os.environ,'MAAS_PIPELINE_PINNED_BASELINE':'1'},capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   view=load_view(fx.root);report=json.loads(view.path('data/derived/weekly-structured/2026-10-27.json').read_text())
   self.assertEqual(len(report['platforms']),4);self.assertEqual(len(report['headline']),5)
   self.assertEqual(view.path('data/weekly/2026-10-27.md').read_bytes(),(BASE/'data/weekly/2026-10-27.md').read_bytes())
 def test_interrupted_draft_injection_recovers_from_committed_baseline(self):
  from test_public_export import FixtureRepo
  from input_snapshot import capture,load_view
  from run_protocol import RunJournal
  fx=FixtureRepo();self.addCleanup(fx.cleanup);root=fx.root
  source=root/'data/weekly/2026-10-27.md';source.parent.mkdir(parents=True,exist_ok=True);source.write_text('old')
  capture(root,'baseline')
  with tempfile.TemporaryDirectory() as temp:
   raw=json.dumps([{'date':'2026-10-27','markdown':'new'}]).encode();request=Path(temp)/(hashlib.sha256(raw).hexdigest()+'.json');request.write_bytes(raw)
   with patch.object(importer,'SITE_DIR',root/'site'),patch.object(importer,'SRC_DIR',source.parent),patch.dict(os.environ,{'MAAS_PIPELINE_PINNED_BASELINE':'1'}):
    with self.assertRaisesRegex(RuntimeError,'interrupted'):
     with RunJournal(root,'weekly-import','crashed'):
      importer.inject_drafts(request,'a'*40);raise RuntimeError('interrupted')
    self.assertEqual(load_view(root).path('data/weekly/2026-10-27.md').read_text(),'old')
    with RunJournal(root,'weekly-import','crashed',recover=True) as journal:
     self.assertEqual(source.read_text(),'old');self.assertFalse((root/'data/derived/import-provenance'/('a'*40+'.json')).exists());importer.inject_drafts(request,'a'*40);journal.finish('success')
    self.assertEqual(load_view(root).path('data/weekly/2026-10-27.md').read_text(),'new')
    request.write_text('tampered')
    with self.assertRaisesRegex(ValueError,'checksum'):importer.inject_drafts(request)
 def test_pinned_import_checks_mutations_and_pending_work_without_recapturing(self):
  from test_public_export import FixtureRepo
  from input_snapshot import capture,load_view,POINTER
  fx=FixtureRepo();self.addCleanup(fx.cleanup);root=fx.root
  record=fx.add_obs();version=capture(root,'baseline')
  path=root/'data/normalized/source-streams.json';original=path.read_bytes()
  with patch.object(writer,'CODE',root),patch.object(writer,'capture',side_effect=AssertionError('must reuse committed snapshot')):
   self.assertEqual(writer.select_ingest_input(pinned_version=version),version)
   for mutation in ['change','delete','add','pending','pointer','archive-add','archive-delete']:
    with self.subTest(mutation=mutation):
     archive=root/f"data/record-revisions/{record['id']}/{record['revision']}.json";archive_raw=archive.read_bytes();archive_extra=archive.parent/'999.json'
     extra=root/'data/derived/unexpected.json';pending=root/'data/pipeline-pending.json';pointer=root/POINTER;old_pointer=pointer.read_bytes()
     if mutation=='change':path.write_text('{}')
     elif mutation=='delete':path.unlink()
     elif mutation=='add':extra.write_text('{}')
     elif mutation=='pending':pending.write_text('{}')
     elif mutation=='archive-add':archive_extra.write_text('{}')
     elif mutation=='archive-delete':archive.unlink()
     else:
      value=json.loads(old_pointer);value['inputVersion']='in_'+'0'*64;pointer.write_text(json.dumps(value))
     with self.assertRaises((ValueError,FileNotFoundError)):writer.select_ingest_input(pinned_version=version)
     archive.write_bytes(archive_raw);archive_extra.unlink(missing_ok=True)
     path.write_bytes(original);extra.unlink(missing_ok=True);pending.unlink(missing_ok=True);pointer.write_bytes(old_pointer)
 def test_deferred_projection_and_provenance_are_committed_and_recoverable(self):
  import subprocess
  from test_public_export import FixtureRepo
  from input_snapshot import capture,load_view
  from data_store import project_site
  fx=FixtureRepo();self.addCleanup(fx.cleanup);capture(fx.root,'baseline')
  with tempfile.TemporaryDirectory() as temp:
   raw=json.dumps([{'date':'2026-10-27','markdown':(BASE/'data/weekly/2026-10-27.md').read_text()}]).encode();request=Path(temp)/(hashlib.sha256(raw).hexdigest()+'.json');request.write_bytes(raw)
   args=[sys.executable,str(BASE/'site/scripts/import-weekly.py'),'--input-root',str(fx.root),'--drafts-file',str(request),'--source-commit','a'*40,'--defer-site-projection']
   result=subprocess.run(args,env={**os.environ,'MAAS_PIPELINE_PINNED_BASELINE':'1'},capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   view=load_view(fx.root);provenance='data/derived/import-provenance/'+'a'*40+'.json'
   self.assertEqual(json.loads(view.path(provenance).read_text())['drafts'][0]['sha256'],hashlib.sha256((BASE/'data/weekly/2026-10-27.md').read_bytes()).hexdigest())
   with patch.object(writer,'CODE',fx.root):self.assertEqual(writer.select_ingest_input(pinned_version=view.version),view.version)
   project_site(fx.root)
   self.assertEqual((fx.root/'site/src/content/weekly/2026-10-27.md').read_bytes(),view.path('data/editorial/weekly/2026-10-27.md').read_bytes())
   # The normal CLI still produces the identical site projection.
   expected={str(p.relative_to(fx.root/'site')):p.read_bytes() for p in (fx.root/'site').rglob('*') if p.is_file()}
   result=subprocess.run(args[:-1],env={**os.environ,'MAAS_PIPELINE_PINNED_BASELINE':'1'},capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   actual={str(p.relative_to(fx.root/'site')):p.read_bytes() for p in (fx.root/'site').rglob('*') if p.is_file()}
   self.assertEqual(actual,expected)
if __name__=='__main__':unittest.main()
