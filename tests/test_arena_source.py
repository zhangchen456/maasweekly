import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pyarrow as pa
import pyarrow.parquet as pq
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
import arena_source as arena


def rows(count=2):
    return [{'model_name':'model-'+str(i),'category':'overall','rating':1500-i,
             'rating_lower':1499-i,'rating_upper':1501-i,'vote_count':100,'rank':i+1,
             'leaderboard_publish_date':'2026-10-28','organization':'fixture','license':'fixture'} for i in range(count)]


class ArenaDatasetTests(unittest.TestCase):
    def fetch(self, data):
        return arena.fetch_dataset(arena.URL,load=lambda:(data,'a'*40,'b'*64),today=date(2026,10,31))

    def test_publication_and_numeric_fields_preserved(self):
        text=self.fetch(rows(101));self.assertIn('Leaderboard published: 2026-10-28',text)
        self.assertIn('CC BY 4.0',text);output=[json.loads(r) for r in text.splitlines()[6:]]
        self.assertEqual(len(output),101);self.assertEqual(output[-1]['model_name'],'model-100')
        self.assertEqual(output[0]['rating'],1500);self.assertNotIn('leaderboard_publish_date',output[0])

    def test_invalid_or_mixed_rows_do_not_become_success(self):
        cases=[[],rows(1001)]
        for key,value in [('category','coding'),('rating',None),('rank',0),('leaderboard_publish_date','2026-12-31'),('model_name','')]:
            d=rows();d[0][key]=value;cases.append(d)
        d=rows();d[1]['leaderboard_publish_date']='2026-10-27';cases.append(d)
        d=rows();d[1]['model_name']='model-0';cases.append(d)
        for data in cases:
            with self.subTest(data=data[:2]),self.assertRaises(ValueError):self.fetch(data)
        with self.assertRaises(ValueError):arena.fetch_dataset(arena.URL+'?unknown',load=lambda:None)

    def test_pinned_complete_file_and_checksum_before_decode(self):
        raw=b'fixture publication';sha=hashlib.sha256(raw).hexdigest();revision='a'*40
        listing=[{'type':'file','path':'text/latest-00000-of-00001.parquet','size':len(raw),'lfs':{'oid':sha}}]
        responses=[json.dumps({'sha':revision}).encode(),json.dumps(listing).encode(),raw]
        with patch.object(arena,'get_bytes',side_effect=responses) as get,patch.object(arena,'read_overall',return_value=rows()) as read:
            data,actual_revision,actual_sha=arena.load_publication();self.assertEqual(data,rows());self.assertEqual((actual_revision,actual_sha),(revision,sha));read.assert_called_once()
            self.assertIn('/tree/'+revision+'/text',get.call_args_list[1].args[0]);self.assertIn('/resolve/'+revision+'/',get.call_args_list[2].args[0])
        for corrupt in [raw[:-1],b'x'*len(raw)]:
            with patch.object(arena,'get_bytes',side_effect=[responses[0],responses[1],corrupt]),patch.object(arena,'read_overall') as read:
                with self.assertRaises(ValueError):arena.load_publication()
                read.assert_not_called()
        with patch.object(arena,'get_bytes',side_effect=[responses[0],json.dumps(listing+listing).encode()]):
            with self.assertRaises(ValueError):arena.load_publication()

    def test_streamed_parquet_selects_only_overall_and_rejects_wrong_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'latest.parquet';data=rows()+[{**rows()[0],'category':'coding'}]
            pq.write_table(pa.Table.from_pylist(data),path)
            self.assertEqual(arena.read_overall(path),rows())
            pq.write_table(pa.table({'unexpected':[1]}),path)
            with self.assertRaises(ValueError):arena.read_overall(path)


if __name__=='__main__':unittest.main()
