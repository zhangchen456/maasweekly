#!/usr/bin/env python3
"""Private account backups and count-only health checks; never prints user records."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import urllib.request


def connect(filename):
    return sqlite3.connect(Path(filename).resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


def validate(db):
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise RuntimeError('backup integrity failed')
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise RuntimeError('backup foreign keys failed')


def backup(source, root, keep=14):
    if keep < 1:
        raise ValueError('keep must be positive')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    with tempfile.TemporaryDirectory(prefix='.backup-', dir=root) as work:
        candidate = Path(work) / 'accounts.sqlite'
        with closing(connect(source)) as src, closing(sqlite3.connect(candidate)) as dst:
            src.backup(dst, pages=256, sleep=0.05)
            validate(dst)
            dst.execute('PRAGMA journal_mode=DELETE')
            # A second independent database simulates restore without touching live state.
            with closing(sqlite3.connect(Path(work) / 'restored.sqlite')) as restored:
                dst.backup(restored)
                validate(restored)
                tables = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                for table in tables:
                    quoted = '"' + table.replace('"', '""') + '"'
                    if dst.execute('SELECT * FROM ' + quoted).fetchall() != restored.execute('SELECT * FROM ' + quoted).fetchall():
                        raise RuntimeError('restore contents differ')
        os.chmod(candidate, 0o600)
        name = 'accounts-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + os.urandom(4).hex() + '.sqlite'
        candidate.replace(root / name)
    snapshots = sorted(root.glob('accounts-*.sqlite'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[keep:]:
        old.unlink()
    return {'backup': name, 'integrity': 'ok', 'restore': 'ok', 'retained': min(len(snapshots), keep)}


def health(source, root, now=None):
    now = time.time() if now is None else now
    alerts = []
    with closing(connect(source)) as db:
        counts = dict(db.execute('SELECT status,COUNT(*) FROM mail_jobs GROUP BY status'))
        oldest = db.execute("SELECT MIN(created) FROM mail_jobs WHERE status='pending'").fetchone()[0]
    if counts.get('review', 0): alerts.append('mail_review')
    if oldest is not None and now - oldest / 1000 > 3600: alerts.append('mail_pending_over_1h')
    snapshots = list(root.glob('accounts-*.sqlite'))
    age = now - max((p.stat().st_mtime for p in snapshots), default=0)
    if not snapshots or age > 26 * 3600: alerts.append('backup_missing_or_stale')
    return {'counts': counts, 'alerts': sorted(alerts)}


def notify(result, state):
    previous = json.loads(state.read_text()) if state.exists() else {'alerts': []}
    if previous['alerts'] == result['alerts']:
        return
    recipient = os.environ['MAAS_ACCOUNT_ALERT_TO']
    fingerprint = hashlib.sha256(json.dumps([previous['alerts'], result['alerts']]).encode()).hexdigest()[:24]
    # Include time epoch in saved state to distinguish a later recurrence from a duplicate retry.
    epoch = previous.get('epoch', 0) + 1
    body = json.dumps({'from': os.environ['MAAS_MAIL_FROM'], 'to': [recipient],
        'subject': 'MaaS Daily · 账号运维异常' if result['alerts'] else 'MaaS Daily · 账号运维已恢复',
        'text': json.dumps(result, ensure_ascii=False)}).encode()
    req = urllib.request.Request('https://api.resend.com/emails', data=body, method='POST', headers={
        'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY'], 'Content-Type': 'application/json', 'User-Agent': 'MaaSWeekly-account-operations/1.0',
        'Idempotency-Key': 'account-health-%s-%s' % (epoch, fingerprint)})
    with urllib.request.urlopen(req, timeout=15) as response:
        response.read()
    state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = state.with_suffix('.tmp')
    temporary.write_text(json.dumps({'alerts': result['alerts'], 'epoch': epoch}))
    os.chmod(temporary, 0o600)
    temporary.replace(state)


def admin_records(root, action, succeeded, result=None):
    # Only actual invocation creates receipts. Never infer restore from backup file existence/mtime.
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    now = int(time.time() * 1000)
    kinds = [('backup', 'account-maintenance.backup'), ('restore', 'account-maintenance.restore')] if action == 'backup' else [('api', 'account-maintenance.health')]
    for kind, source in kinds:
        status = 'normal' if succeeded else 'abnormal' if kind != 'restore' else 'unknown'
        if action == 'health' and result and result.get('alerts'):
            status = 'abnormal'
        value = 'isolated-sqlite-copy-integrity-and-content' if kind == 'restore' and succeeded else None
        record = {'id': 'maintenance_' + os.urandom(12).hex(), 'kind': kind, 'status': status,
                  'checkedAt': now, 'budgetSeconds': 26 * 3600, 'source': source, 'value': value}
        target = root / (record['id'] + '.json')
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(record))
        os.chmod(temporary, 0o600)
        temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'health'])
    parser.add_argument('--db', type=Path, default=os.environ.get('MAAS_ACCOUNT_DB'))
    parser.add_argument('--backups', type=Path, default=Path('/srv/maasweekly/shared/state/accounts/backups'))
    parser.add_argument('--keep', type=int, default=14)
    parser.add_argument('--notify-state', type=Path)
    parser.add_argument('--systemd', action='store_true')
    parser.add_argument('--admin-records', type=Path, help='Optional private T06 inbox for actual execution receipts')
    args = parser.parse_args()
    if not args.db or not args.db.is_file(): parser.error('existing account database required')
    os.umask(0o077)
    try:
        result = backup(args.db, args.backups, args.keep) if args.action == 'backup' else health(args.db, args.backups)
    except Exception:
        if args.admin_records:
            admin_records(args.admin_records, args.action, False)
        raise
    if args.systemd and args.action == 'health':
        for unit in ('maas-account-digest', 'maas-account-digest-retry', 'maas-account-backup'):
            active = subprocess.run(['systemctl', 'is-active', unit + '.timer'], capture_output=True, text=True).stdout.strip()
            outcome = subprocess.run(['systemctl', 'show', unit + '.service', '-p', 'Result', '--value'], capture_output=True, text=True).stdout.strip()
            if active != 'active': result['alerts'].append(unit + '_timer_inactive')
            if outcome != 'success': result['alerts'].append(unit + '_service_failed')
        result['alerts'].sort()
    if args.admin_records:
        admin_records(args.admin_records, args.action, True, result)
    if args.notify_state: notify(result, args.notify_state)
    print(json.dumps(result))
    if result.get('alerts'): raise SystemExit(1)


if __name__ == '__main__':
    main()
