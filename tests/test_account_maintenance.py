import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location('maintenance', Path(__file__).resolve().parents[1] / 'ops/account-maintenance.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AccountMaintenanceTests(unittest.TestCase):
    def test_backup_includes_live_wal_and_restore_and_retention(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = root / 'accounts.sqlite'
            with sqlite3.connect(source) as writer:
                writer.executescript('PRAGMA journal_mode=WAL; CREATE TABLE users(id PRIMARY KEY,email); CREATE TABLE mail_jobs(status,created);')
                writer.execute('INSERT INTO users VALUES(?,?)', ('u1', 'private@example.test'))
                writer.commit()
                for _ in range(3):
                    report = module.backup(source, root / 'backups', 2)
                    self.assertEqual(report['restore'], 'ok')
                snapshots = list((root / 'backups').glob('*.sqlite'))
                self.assertEqual(len(snapshots), 2)
                with module.connect(snapshots[0]) as restored:
                    self.assertEqual(restored.execute('SELECT * FROM users').fetchall(), [('u1', 'private@example.test')])
                self.assertEqual(snapshots[0].stat().st_mode & 0o777, 0o600)
                self.assertEqual(module.health(source, root / 'backups')['alerts'], [])

    def test_health_reports_old_pending_review_and_missing_backup_without_private_data(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = root / 'accounts.sqlite'
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE mail_jobs(status,created)')
                db.executemany('INSERT INTO mail_jobs VALUES(?,?)', [('pending', (time.time()-7200)*1000), ('review', time.time()*1000)])
            result = module.health(source, root / 'missing')
            self.assertEqual(result['alerts'], ['backup_missing_or_stale', 'mail_pending_over_1h', 'mail_review'])

    def test_notifications_only_on_transition_and_failure_preserves_state(self):
        with tempfile.TemporaryDirectory() as work:
            state = Path(work) / 'health.json'
            env = {'MAAS_ACCOUNT_ALERT_TO':'maintainer@example.test', 'MAAS_MAIL_FROM':'sender@example.test', 'RESEND_API_KEY':'test-key'}
            with patch.dict(module.os.environ, env), patch.object(module.urllib.request, 'urlopen') as send:
                send.return_value = MagicMock()
                module.notify({'alerts': []}, state)
                self.assertEqual(send.call_count, 0)
                module.notify({'alerts': ['mail_review']}, state)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(send.call_args.args[0].get_header('User-agent'), 'MaaSWeekly-account-operations/1.0')
                module.notify({'alerts': ['mail_review']}, state)
                self.assertEqual(send.call_count, 1)
                before = state.read_text()
                send.side_effect = RuntimeError('provider unavailable')
                with self.assertRaises(RuntimeError): module.notify({'alerts': []}, state)
                self.assertEqual(state.read_text(), before)
                send.side_effect = None
                module.notify({'alerts': []}, state)
                self.assertEqual(state.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__': unittest.main()
