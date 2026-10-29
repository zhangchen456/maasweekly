import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runtime_package',BASE/'ops/runtime-package.py');package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
class RuntimePackageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.source=self.root/'incoming';self.source.mkdir();self.dest=self.root/'runtime';self.dest.mkdir()
 def manifest(self,files):
  (self.source/'metadata').mkdir(exist_ok=True)
  (self.source/'metadata/runtime-manifest.json').write_text(json.dumps({'codeCommit':'a'*40,'dataIncluded':False,'pageFormatVersion':1,'files':files}))
 def file(self,name,body=b'code'):
  file=self.source/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body)
  return {'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
 def test_installs_verified_copy_not_deployer_owned_inode(self):
  row=self.file('agent-api/dist/server.js');self.manifest([row]);root,_=package.install(self.source,self.dest)
  (self.source/row['path']).write_bytes(b'changed');self.assertEqual((root/row['path']).read_bytes(),b'code')
 def test_tamper_and_parent_symlinks_cannot_read_external_files(self):
  row=self.file('agent-api/dist/server.js');self.manifest([row]);(self.source/row['path']).write_bytes(b'bad')
  with self.assertRaises(ValueError):package.install(self.source,self.dest)
  outside=self.root/'outside';outside.mkdir();(outside/'secret').write_bytes(b'secret')
  (self.source/'escape').symlink_to(outside,target_is_directory=True);self.manifest([{'path':'escape/secret','bytes':6,'sha256':hashlib.sha256(b'secret').hexdigest()}])
  with self.assertRaises(OSError):package.install(self.source,self.dest)
  self.assertFalse((self.dest/('a'*40)).exists())
 def test_rejects_path_escape_and_declared_external_link(self):
  for row in [{'path':'../escape','bytes':1,'sha256':'a'*64},{'path':'bin/link','symlink':'../../outside'}]:
   self.manifest([row])
   with self.assertRaises(ValueError):package.install(self.source,self.dest)
if __name__=='__main__':unittest.main()
