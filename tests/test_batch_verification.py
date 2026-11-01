import hashlib,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from blob_store import FilesystemBlobStore,verified_batch_reader,BlobIntegrityError

class BatchVerificationTests(unittest.TestCase):
 def test_serial_parallel_same_bytes_and_repeat_detects_tampering(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=FilesystemBlobStore(Path(tmp));batch=[];expected=[]
   for n in range(130):
    raw=('sample'+str(n)).encode();sha=hashlib.sha256(raw).hexdigest();store.putIfAbsent(sha,raw);batch.append((sha,len(raw)));expected.append(raw)
   for workers in [1,4]:
    with verified_batch_reader(store,workers) as read:self.assertEqual(list(read(batch)),expected)
   with verified_batch_reader(store) as read:
    self.assertEqual(list(read(batch)),expected)
    store.path(batch[30][0]).write_bytes(b'corrupt')
    with self.assertRaises(BlobIntegrityError):list(read(batch))
 def test_missing_link_and_wrong_size_refuse(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=FilesystemBlobStore(Path(tmp));raw=b'yes';sha=hashlib.sha256(raw).hexdigest();store.putIfAbsent(sha,raw)
   with verified_batch_reader(store) as read:
    with self.assertRaises(BlobIntegrityError):list(read([(sha,4)]))
    store.path(sha).unlink()
    with self.assertRaises(FileNotFoundError):list(read([(sha,3)]))
    store.path(sha).symlink_to('/etc/passwd')
    with self.assertRaises(BlobIntegrityError):list(read([(sha,3)]))

if __name__=='__main__':unittest.main()
