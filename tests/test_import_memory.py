"""Memory bounds must preserve canonical identity and batch every document."""
import hashlib,json,sys,tracemalloc,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from input_snapshot import canonical,canonical_digest
import shadow_store

class ImportMemoryTests(unittest.TestCase):
 def test_streamed_hash_has_identical_bytes(self):
  for value in [{}, {'中文': ['é', '\x00', '\\', 1.25, True, None], 'a': {'z': 1, 'a': 2}}, list(range(1000))]:
   self.assertEqual(canonical_digest(value),hashlib.sha256(canonical(value).encode()).hexdigest())
 def test_large_inventory_does_not_allocate_full_serialization(self):
  value={f'data/{i:06}.json':{'path':f'data/objects/{i:064}.json','sha256':'a'*64,'bytes':1024} for i in range(50000)}
  expected=hashlib.sha256(canonical(value).encode()).hexdigest()
  tracemalloc.start()
  self.assertEqual(canonical_digest(value),expected)
  _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
  self.assertLess(peak,8*1024*1024)
 def test_batches_bound_bytes_and_count_without_dropping_large_files(self):
  metadata={str(i):{'bytes':size} for i,size in enumerate([4,4,4,30,1,1,1,1])}
  with patch.object(shadow_store,'DOCUMENT_BATCH_BYTES',10),patch.object(shadow_store,'DOCUMENT_BATCH_COUNT',3):
   batches=list(shadow_store.document_batches(metadata))
  self.assertEqual([x for b in batches for x in b],list(metadata))
  for b in batches:
   self.assertLessEqual(len(b),3)
   self.assertTrue(len(b)==1 or sum(metadata[x]['bytes'] for x in b)<=10)
  self.assertIn(['3'],batches)
if __name__=='__main__':unittest.main()
