"""Pure verification contracts; PostgreSQL fault cases live in test_shadow_store."""
import sys,unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
from shadow_store import _jsonb_safe,_verify_files,_timed
from input_snapshot import canonical_digest
class VerificationTests(unittest.TestCase):
 def test_unicode_equivalence_and_nested_exceptional_values(self):
  # Exhaustively preserve the old per-character acceptance boundary.
  for cp in range(0x110000):
   if _jsonb_safe(chr(cp)) != (cp!=0 and not 0xd800<=cp<=0xdfff):self.fail(hex(cp))
  self.assertTrue(_jsonb_safe({'normal':['中文','😀','x'*100000,1,None,False]}))
  self.assertFalse(_jsonb_safe({'nested':[{'key':'x\x00y'}]}))
  self.assertFalse(_jsonb_safe({'\udfff':'value'}))
 def test_timing_preserves_machine_readable_stdout(self):
  import contextlib,io,json
  out,err=io.StringIO(),io.StringIO()
  with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
   self.assertEqual(_timed('fixture',lambda:42),42)
  self.assertEqual(out.getvalue(),'');self.assertEqual(json.loads(err.getvalue())['stage'],'database.fixture')
 def test_conflicting_alias_sizes_cannot_hide_behind_deduplication(self):
  sha='a'*64
  files={'data/derived/a.json':{'path':'data/input-objects/'+sha+'.json','sha256':sha,'bytes':1},'data/derived/b.json':{'path':'data/input-objects/'+sha+'.json','sha256':sha,'bytes':2}}
  version='in_'+canonical_digest(files)
  connection=MagicMock();store=MagicMock()
  with self.assertRaisesRegex(ValueError,'inconsistent size'):_verify_files(connection,version,files,store)
  connection.cursor.assert_not_called();store.get.assert_not_called()
if __name__=='__main__':unittest.main()
