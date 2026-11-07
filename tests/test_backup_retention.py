import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ops'))
import backup_retention as b

def epoch(value):
    return datetime.fromisoformat(value).timestamp()

NOW=epoch('2026-11-07T20:00:00+08:00')
OLD='maas_data-20261031T010000Z.dump'
LATEST='maas_data-20261107T100000Z.dump'

def row(value):
    ts=epoch(value)
    return dict(name='maas_data-'+datetime.fromtimestamp(ts, timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.dump',createdAt=ts)

class BackupRetentionTests(unittest.TestCase):
    def fixture(self, root):
        base=root/'shared/data-store/backups';base.mkdir(parents=True)
        directory=root/'shared/backup-retention';directory.mkdir()
        for name in sorted(b.PINS | {OLD,LATEST,'maas_data-20261101T051025Z.dump'}):
            self.backup(base, name)
        rows,_=b.inventory(base,NOW,toc=lambda p:None)
        proof=dict(status='passed',isolated=True,restores=[dict(name=r['name'],sha256=r['sha256'],restored=True,temporaryDatabaseRemoved=True) for r in rows])
        (directory/'restore-proof.json').write_text(json.dumps(proof))
        return base,directory

    def backup(self, base, name):
        p=base/name;p.write_bytes(name.encode())
        p.with_name(name+'.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p)+'\n')
        os.utime(p,(b.stamp(name),b.stamp(name)))
        return p

    def test_shanghai_daily_and_completed_week_boundaries(self):
        dates=['2026-10-04T23:59:59+08:00','2026-10-05T00:00:00+08:00',
               '2026-10-11T23:59:59+08:00','2026-10-18T23:59:59+08:00',
               '2026-10-25T23:59:59+08:00','2026-11-01T12:00:00+08:00',
               '2026-11-01T23:59:59+08:00','2026-11-02T00:00:00+08:00',
               '2026-11-02T12:00:00+08:00','2026-11-06T19:59:59+08:00',
               '2026-11-06T20:00:00+08:00','2026-11-06T20:00:01+08:00',
               '2026-11-06T23:00:00+08:00','2026-11-07T19:00:00+08:00']
        rows=list(map(row,dates));keep=b.select(rows,NOW,pins=[])
        self.assertEqual({i for i,r in enumerate(rows) if r['name'] in keep},{2,3,4,6,8,11,12,13})
        self.assertEqual(sum('completed_week' in why for why in keep.values()),4)
        self.assertIn('daily',keep[rows[6]['name']])

    def test_latest_two_and_pins_survive_old_age_without_fabricated_coverage(self):
        rows=list(map(row,['2020-01-01T00:00:00Z','2020-01-02T00:00:00Z','2020-01-03T00:00:00Z','2020-01-04T00:00:00Z']))
        keep=b.select(rows,NOW,pins=[rows[0]['name']])
        self.assertEqual(set(keep),{rows[i]['name'] for i in [0,2,3]})
        self.assertTrue(all('daily' not in why and 'completed_week' not in why for why in keep.values()))
        self.assertRaises(ValueError,b.select,rows,NOW,pins=['missing'])

    def test_frozen_set_never_expands_and_known_inventory_must_match(self):
        with tempfile.TemporaryDirectory() as t:
            base,d=self.fixture(Path(t).resolve());plan=b.make_plan(base,NOW,toc=lambda p:None)
            frozen={'files':[{**r,'action':'delete' if r in plan['delete'] else 'keep'} for r in plan['rows']]}
            self.backup(base,'maas_data-20261030T020000Z.dump')
            selected=b.make_plan(base,NOW,frozen=frozen,toc=lambda p:None)
            self.assertEqual([r['name'] for r in selected['delete']],[OLD])
            proposal=copy.deepcopy(frozen);proposal['files'][0]['action']='proposed_delete'
            self.assertRaises(ValueError,b.make_plan,base,NOW,frozen=proposal,toc=lambda p:None)
            wrong_count={**frozen,'summary':{'candidateCount':99}}
            self.assertRaises(ValueError,b.make_plan,base,NOW,frozen=wrong_count,toc=lambda p:None)
            frozen['files'][0]['sha256']='0'*64
            self.assertRaises(ValueError,b.make_plan,base,NOW,frozen=frozen,toc=lambda p:None)

    def test_bad_backup_unknown_file_symlink_hardlink_missing_pin_block_deletion(self):
        for failure in ['corrupt','missing_checksum','link','hardlink','future','unknown','missing_pin','toc']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as t:
                base,d=self.fixture(Path(t).resolve());p=base/OLD
                toc=lambda p:None
                if failure=='corrupt':p.write_bytes(b'changed')
                if failure=='missing_checksum':p.with_name(p.name+'.sha256').unlink()
                if failure=='link':p.unlink();p.symlink_to(base/LATEST)
                if failure=='hardlink':os.link(p,base/'other')
                if failure=='future':self.backup(base,'maas_data-20261108T000000Z.dump')
                if failure=='unknown':(base/'.dump.pending').write_text('partial')
                if failure=='missing_pin':(base/next(iter(b.PINS))).unlink()
                if failure=='toc':
                    def toc(p):raise ValueError('invalid archive')
                self.assertRaises(ValueError,b.make_plan,base,NOW,toc=toc)
                self.assertTrue(p.exists())

    def test_mutation_during_verification_or_before_apply_preserves_all(self):
        for stage in ['during','after','newfile','protected_selection']:
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as t:
                base,d=self.fixture(Path(t).resolve())
                def toc(p):
                    if stage=='during' and p.name==OLD:p.write_bytes(b'mutated')
                if stage=='during':
                    self.assertRaises(ValueError,b.make_plan,base,NOW,toc=toc)
                    continue
                plan=b.make_plan(base,NOW,toc=toc)
                if stage=='after':(base/LATEST).write_bytes(b'mutated protected point')
                if stage=='newfile':self.backup(base,'maas_data-20261107T110000Z.dump')
                if stage=='protected_selection':plan['delete'].append(next(r for r in plan['rows'] if r['name']==LATEST))
                self.assertRaises(ValueError,b.apply_plan,base,plan,d)
                self.assertTrue((base/OLD).exists())

    def test_verified_deletion_audits_pairs_preserves_excluded_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            base,d=self.fixture(Path(t).resolve())
            for name in b.EXCLUDED:(base/name).write_text('preserve')
            plan=b.make_plan(base,NOW,toc=lambda p:None);b.require_restore_proof(d,plan['rows'])
            result=b.apply_plan(base,plan,d)
            self.assertEqual(result['deleted'],1);self.assertEqual(result['retained'],5)
            self.assertFalse((base/OLD).exists());self.assertFalse((base/(OLD+'.sha256')).exists())
            self.assertTrue(all((base/name).read_text()=='preserve' for name in b.EXCLUDED))
            audit=json.loads(Path(result['audit']).read_text());self.assertEqual(audit['removed'],[OLD])
            self.assertEqual(audit['status'],'completed')
            self.assertEqual(b.make_plan(base,NOW,toc=lambda p:None)['delete'],[])

    def test_soft_budget_does_not_remove_protected_points(self):
        with tempfile.TemporaryDirectory() as t:
            base,d=self.fixture(Path(t).resolve());plan=b.make_plan(base,NOW,toc=lambda p:None)
            with patch.object(b,'SOFT_BUDGET',1):result=b.apply_plan(base,plan,d)
            self.assertTrue(result['overBudget']);self.assertTrue(all((base/name).exists() for name in plan['protected']))

    def test_only_exact_pinned_migration_hardlink_pair_is_accepted_and_never_deleted(self):
        for case in ['known','wrong_inode','extra_link','symlink_bundle']:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as t:
                base,d=self.fixture(Path(t).resolve());bundle=base/'cutover-final-20261029T163617Z';bundle.mkdir()
                original=base/b.MIGRATION_DUMP;paired=bundle/b.MIGRATION_DUMP
                os.link(original,paired)
                if case=='wrong_inode':
                    paired.unlink();paired.write_bytes(original.read_bytes());os.link(original,base/'unexpected_link')
                if case=='extra_link':os.link(original,base/'unexpected_link')
                if case=='symlink_bundle':
                    moved=base.parent/'moved_bundle';bundle.rename(moved);bundle.symlink_to(moved)
                if case!='known':
                    self.assertRaises(ValueError,b.make_plan,base,NOW,toc=lambda p:None)
                else:
                    plan=b.make_plan(base,NOW,toc=lambda p:None)
                    self.assertIn(b.MIGRATION_DUMP,plan['protected'])
                    result=b.apply_plan(base,plan,d)
                    self.assertEqual(result['deleted'],1)
                    self.assertEqual(original.stat().st_ino,paired.stat().st_ino)
                    self.assertEqual(original.stat().st_nlink,2)

    def test_only_accepted_successful_daily_job_with_fresh_backup_runs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();base,d=self.fixture(root)
            journal=SimpleNamespace(mode='update',published=True,validation='passed',runtime_accepted=True,started=(NOW-3*3600)*1000,gid=None)
            for field,value in [('mode','rebuild'),('published',False),('validation','failed'),('runtime_accepted',False)]:
                changed=copy.copy(journal);setattr(changed,field,value)
                self.assertEqual(b.after_success(root,changed)['status'],'skipped')
            self.assertEqual(b.after_success(root,journal,RuntimeError())['status'],'skipped')
            with patch.object(b.time,'time',return_value=NOW),patch.object(b.subprocess,'run'):
                stale=copy.copy(journal);stale.started=NOW*1000
                self.assertEqual(b.after_success(root,stale)['status'],'failed')
                self.assertTrue((base/OLD).exists())
                result=b.after_success(root,journal)
            self.assertEqual(result['status'],'completed');self.assertEqual(result['deleted'],1)

    def test_missing_or_mismatched_restore_proof_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();base,d=self.fixture(root)
            rows,_=b.inventory(base,NOW,toc=lambda p:None)
            proof=json.loads((d/'restore-proof.json').read_text());proof['restores'][0]['sha256']='0'*64
            (d/'restore-proof.json').write_text(json.dumps(proof))
            self.assertRaises(ValueError,b.require_restore_proof,d,rows)
            (d/'restore-proof.json').unlink()
            self.assertRaises(FileNotFoundError,b.require_restore_proof,d,rows)

if __name__=='__main__':unittest.main()
