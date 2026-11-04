"""Production packets keep full-week evidence without using a visitor query."""
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('weekly_evidence',BASE/'ops/weekly-editorial.py')
editorial=importlib.util.module_from_spec(spec);spec.loader.exec_module(editorial)
START,END=date(2026,10,28),date(2026,11,3)

class WeeklyEvidenceTests(unittest.TestCase):
    def fixture(self,root,rows):
        version='ds_'+'a'*64;name=f'releases/{version}/changes.json'
        file=root/name;file.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(rows).encode();file.write_bytes(raw)
        manifest={'datasetVersion':version,'dataThrough':'2026-11-04',
            'coverage':{'changes':{'from':'2026-09-04','to':'2026-11-04','count':len(rows)}},
            'files':[{'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]}
        (root/'publication.json').write_text(json.dumps(manifest))
        return file,manifest

    def test_includes_first_and_last_days_and_preserves_source_content(self):
        rows=[{'id':str(i),'observationDate':day,'status':state,'original':'full evidence'}
            for i,(day,state) in enumerate([('2026-10-27','active'),('2026-10-28','active'),
                ('2026-11-03','active'),('2026-11-04','active'),('2026-11-02','withdrawn')])]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.fixture(root,rows)
            packet=editorial.collect_published(root,START,END)
            self.assertEqual(packet['observations'],[rows[1],rows[2]])
            self.assertEqual(packet['periodStart'],'2026-10-28')
            self.assertEqual(packet['periodEnd'],'2026-11-03')

    def test_rejects_corruption_duplicates_incomplete_coverage_and_unsafe_version(self):
        row={'id':'one','observationDate':'2026-10-28','status':'active'}
        for failure in ['hash','count','duplicate','from','through','version','missing','duplicate-file']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);file,manifest=self.fixture(root,[row,row] if failure=='duplicate' else [row])
                if failure=='hash':file.write_text('[]')
                elif failure=='count':manifest['coverage']['changes']['count']=2
                elif failure=='from':manifest['coverage']['changes']['from']='2026-10-29'
                elif failure=='through':manifest['dataThrough']='2026-11-02'
                elif failure=='version':manifest['datasetVersion']='../../outside'
                elif failure=='missing':manifest['files']=[]
                elif failure=='duplicate-file':manifest['files']*=2
                (root/'publication.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):editorial.collect_published(root,START,END)

    def test_production_uses_only_fixed_ssh_command_and_checks_period(self):
        packet={'periodStart':str(START),'periodEnd':str(END)}
        with patch.object(editorial.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(packet).encode())) as run:
            self.assertEqual(editorial.collect_production(START,END),packet)
            command=run.call_args.args[0]
            self.assertEqual(command[-2:],['maasdeploy@47.237.135.97','weekly-evidence'])
            self.assertIn('StrictHostKeyChecking=yes',command)
            with self.assertRaisesRegex(ValueError,'period mismatch'):editorial.collect_production(date(2026,10,29),END)

    def test_restricted_shell_refuses_arguments_and_arbitrary_commands(self):
        import os
        for command in ['weekly-evidence /etc/shadow','weekly-evidence; id','weekly-evidence\nid']:
            result=subprocess.run(['bash',str(BASE/'ops/server/maasweekly-deploy-shell')],
                env={**os.environ,'SSH_ORIGINAL_COMMAND':command},capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('不允许的命令',result.stderr)

if __name__=='__main__':unittest.main()
