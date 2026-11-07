import hashlib,json,os,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import cache_retention as c
class CacheTests(unittest.TestCase):
 def fixture(self,root):
  shared=root/'shared';base=shared/'public-data/candidates';canonical=shared/'public-data/v1';base.mkdir(parents=True);canonical.mkdir(parents=True);(shared/'data-store/writer').mkdir(parents=True)
  copies=[]
  for n in range(6):
   ds='ds_'+str(n)*64;p=base/(str(n)*32);path='releases/'+ds+'/changes.json';data=b'[]';m={'datasetVersion':ds,'files':[{'path':path,'bytes':2,'sha256':hashlib.sha256(data).hexdigest()}]}
   for d in [p,canonical]:
    (d/path).parent.mkdir(parents=True,exist_ok=True);(d/path).write_bytes(data)
   (p/'publication.json').write_text(json.dumps(m));(p/'manifest.json').write_text('{}');(p/'releases'/ds/'manifest.json').write_text('{}');os.utime(p,(time.time()-200000+n,time.time()-200000+n));copies.append(p)
  (canonical/'publication.json').write_text(json.dumps({'datasetVersion':'ds_'+'4'*64,'retainedVersions':[{'datasetVersion':'ds_'+'1'*64}]}));(shared/'data-store/writer/candidate.json').write_text(json.dumps({'candidate':'/public/candidates/'+copies[0].name}));return copies,canonical
 def test_exact_copy_only_protects_current_rollback_receipt_and_latest_three(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t).resolve();copies,canonical=self.fixture(root);p=c.plan(root)
   self.assertEqual([r['name'] for r in p['copies']],[copies[2].name]);c.apply(root,p)
   self.assertFalse(copies[2].exists());self.assertTrue(all(x.exists() for i,x in enumerate(copies) if i!=2));self.assertTrue((canonical/('releases/ds_'+'2'*64)/'changes.json').exists());self.assertEqual(c.plan(root)['copies'],[])
 def test_corruption_extra_files_symlinks_and_post_plan_change_are_preserved(self):
  for case in ['corrupt','extra','link','changed']:
   with self.subTest(case=case),tempfile.TemporaryDirectory() as t:
    root=Path(t).resolve();copies,canonical=self.fixture(root);p=copies[2];f=p/('releases/ds_'+'2'*64)/'changes.json'
    if case=='corrupt':f.write_bytes(b'!!')
    if case=='extra':(p/'unknown').write_text('retain')
    if case=='link':f.unlink();f.symlink_to(canonical/('releases/ds_'+'2'*64)/'changes.json')
    os.utime(p,(time.time()-200000+2,time.time()-200000+2))
    plan=c.plan(root)
    if case=='changed':f.write_bytes(b'!!');self.assertRaises(ValueError,c.apply,root,plan)
    else:self.assertEqual(plan['copies'],[])
    self.assertTrue(p.exists())
