"""Verified local dump retention, called under the data publisher's release lock.

No CAS, account data, migration bundles or unknown files are deleted. Pins are
explicit operator decisions; changing them requires another reviewed change.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pipeline_monitor import write_json

ZONE = ZoneInfo('Asia/Shanghai')
NAME = re.compile(r'maas_data-(\d{8}T\d{6}Z)\.dump')
PINS = frozenset(['maas_data-20261029T045733Z.dump',
                 'maas_data-20261029T163600Z.dump',
                 'maas_data-20261107T085212Z.dump'])
EXCLUDED = {'cutover-final-20261029T163617Z', 'legacy-metadata-inventory.json', 'legacy-metadata.tar.gz'}
SOFT_BUDGET = 4 * 1024**3
MIGRATION_DUMP = 'maas_data-20261029T163600Z.dump'


def stamp(name):
    match = NAME.fullmatch(name)
    if not match:
        raise ValueError('unexpected backup name')
    return datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()


def fingerprint(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_nlink]


def regular(path, *, links=1):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != links:
        os.close(fd)
        raise ValueError('backup is not a single regular file')
    return fd, info


def inspect_file(path, now, *, toc=None):
    created = stamp(path.name)
    if not datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp() <= created <= now:
        raise ValueError('backup timestamp anomaly')
    # The approved migration bundle contains a hard link to its pinned dump.
    # Recognize exactly that existing pair; every other linked file fails closed.
    paired = None
    if path.name == MIGRATION_DUMP and path.lstat().st_nlink == 2:
        paired = path.parent/'cutover-final-20261029T163617Z'/path.name
        if MIGRATION_DUMP not in PINS or paired.resolve() != paired:
            raise ValueError('unsafe migration pair')
        paired_before = paired.lstat()
        original = path.lstat()
        if (not stat.S_ISREG(paired_before.st_mode) or paired_before.st_nlink != 2 or
            (paired_before.st_dev, paired_before.st_ino) != (original.st_dev, original.st_ino)):
            raise ValueError('unexpected migration hard link')
    fd, before = regular(path, links=2 if paired else 1)
    try:
        if before.st_mtime > now or before.st_size == 0:
            raise ValueError('backup timestamp or size anomaly')
        h = hashlib.sha256()
        with os.fdopen(os.dup(fd), 'rb') as stream:
            while block := stream.read(1024*1024):
                h.update(block)
        side = path.with_name(path.name+'.sha256')
        side_fd, side_before = regular(side)
        try:
            if side_before.st_size > 1024:
                raise ValueError('oversized checksum')
            checksum = os.read(side_fd, 1025).decode('ascii').strip().split(maxsplit=1)
            if len(checksum) != 2 or checksum[0] != h.hexdigest() or checksum[1].lstrip('*') != str(path):
                raise ValueError('checksum mismatch')
            if toc is None:
                subprocess.run(['pg_restore', '--list', str(path)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            else:
                toc(path)
            if (fingerprint(before) != fingerprint(os.fstat(fd)) or
                fingerprint(before) != fingerprint(path.lstat()) or
                fingerprint(side_before) != fingerprint(os.fstat(side_fd)) or
                fingerprint(side_before) != fingerprint(side.lstat())):
                raise ValueError('backup changed during verification')
            if paired and fingerprint(paired.lstat()) != fingerprint(paired_before):
                raise ValueError('migration pair changed during verification')
        finally:
            os.close(side_fd)
        return dict(name=path.name, createdAt=created, modifiedAt=before.st_mtime,
                    bytes=before.st_size, sidecarBytes=side_before.st_size, sha256=h.hexdigest(),
                    fingerprint=fingerprint(before), sidecarFingerprint=fingerprint(side_before))
    finally:
        os.close(fd)


def select(rows, now, pins=PINS):
    """Calendar windows are Shanghai dates; weeks are completed Monday-Sunday."""
    ordered = sorted(rows, key=lambda r: r['createdAt'])
    names = {r['name'] for r in ordered}
    if len(names) != len(ordered) or not set(pins).issubset(names) or len(ordered) < 2:
        raise ValueError('missing protected backup or insufficient recovery points')
    keep = {name: ['manual_pin'] for name in pins}
    def protect(row, why):
        keep.setdefault(row['name'], []).append(why)
    for row in ordered[-2:]:
        protect(row, 'latest_two')
    today = datetime.fromtimestamp(now, ZONE).date()
    monday = today-timedelta(days=today.weekday())
    daily, weekly = {}, {}
    for row in ordered:
        if row['createdAt'] > now:
            raise ValueError('future backup')
        if now-max(row['createdAt'], row.get('modifiedAt', row['createdAt'])) < 86400:
            protect(row, 'within_24_hours')
        day = datetime.fromtimestamp(row['createdAt'], ZONE).date()
        if today-timedelta(days=6) <= day <= today:
            daily[day] = row
        week = day-timedelta(days=day.weekday())
        if monday-timedelta(weeks=4) <= week < monday:
            weekly[week] = row
    for row in daily.values():
        protect(row, 'daily')
    for row in weekly.values():
        protect(row, 'completed_week')
    return keep


def inventory(base, now, *, toc=None):
    if base.resolve() != base or not base.is_dir():
        raise ValueError('unsafe backup directory')
    rows, review = [], []
    entries = sorted(p.name for p in base.iterdir())
    for name in entries:
        if NAME.fullmatch(name):
            try:
                rows.append(inspect_file(base/name, now, toc=toc))
            except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
                review.append(name)
        elif name in EXCLUDED:
            if (base/name).is_symlink():
                review.append(name)
        elif not (name.endswith('.sha256') and NAME.fullmatch(name[:-7]) and name[:-7] in entries):
            review.append(name)
    return rows, review


def make_plan(base, now, *, frozen=None, toc=None):
    rows, review = inventory(base, now, toc=toc)
    # A damaged new backup must never evict the previous recoverable generation.
    if review:
        raise ValueError('backup inventory requires manual review')
    protected = select(rows, now)
    candidates = [r for r in rows if r['name'] not in protected]
    if frozen is not None:
        actual = {r['name']: r for r in rows}
        for old in frozen['files']:
            if old['name'] not in actual or any(actual[old['name']][k] != old[k] for k in ['bytes', 'sha256', 'sidecarBytes']):
                raise ValueError('approved inventory changed')
        allowed = {r['name']: r for r in frozen['files'] if r['action'] == 'delete'}
        candidates = [r for r in candidates if r['name'] in allowed]
        if {r['name'] for r in candidates} != set(allowed):
            raise ValueError('approved deletion set changed')
        for row in candidates:
            if any(row[k] != allowed[row['name']][k] for k in ['bytes', 'sha256', 'sidecarBytes']):
                raise ValueError('approved backup changed')
        if not {r['name'] for r in frozen['files'] if r['action'] == 'keep'}.issubset({r['name'] for r in rows}-set(allowed)):
            raise ValueError('approved protected file missing')
    return dict(checkedAt=now, rows=rows, protected=protected, delete=candidates,
                bytes=sum(r['bytes'] for r in rows), softBudgetBytes=SOFT_BUDGET)


def require_restore_proof(directory, rows):
    proof_path = directory/'restore-proof.json'
    if proof_path.is_symlink():
        raise ValueError('unsafe restore proof')
    proof = json.loads(proof_path.read_text())
    if proof.get('status') != 'passed' or not proof.get('isolated'):
        raise ValueError('isolated restore proof required')
    tested = {r['name']: r for r in proof['restores'] if r.get('restored') and r.get('temporaryDatabaseRemoved')}
    actual = {r['name']: r for r in rows}
    for name in PINS:
        if name not in tested or name not in actual or tested[name]['sha256'] != actual[name]['sha256']:
            raise ValueError('protected restore proof mismatch')


def apply_plan(base, value, directory, gid=None):
    """Caller holds release.lock. Persist intent before unlinking reviewed pairs."""
    if base.resolve() != base or directory.resolve() != directory:
        raise ValueError('unsafe retention directory')
    expected = {r['name'] for r in value['rows']}
    if {p.name for p in base.iterdir() if NAME.fullmatch(p.name)} != expected:
        raise ValueError('backup inventory changed')
    for row in value['rows']:
        for suffix, key in [('', 'fingerprint'), ('.sha256', 'sidecarFingerprint')]:
            if fingerprint((base/(row['name']+suffix)).lstat()) != row[key]:
                raise ValueError('backup changed after verification')
    # Recompute protections so a malformed plan cannot delete a protected row.
    protected = select(value['rows'], value['checkedAt'])
    by_name = {r['name']: r for r in value['rows']}
    for row in value['delete']:
        if row['name'] in protected or row != by_name.get(row['name']) or row['fingerprint'][-1] != 1:
            raise ValueError('unsafe deletion selection')
    audit = directory/('audit-'+str(time.time_ns())+'.json')
    value = {**value, 'status': 'started', 'removed': []}
    write_json(audit, value, gid)
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for row in value['delete']:
            for suffix, key in [('', 'fingerprint'), ('.sha256', 'sidecarFingerprint')]:
                if fingerprint(os.stat(row['name']+suffix, dir_fd=fd, follow_symlinks=False)) != row[key]:
                    raise ValueError('backup changed before deletion')
            os.unlink(row['name'], dir_fd=fd)
            os.unlink(row['name']+'.sha256', dir_fd=fd)
            os.fsync(fd)
            value['removed'].append(row['name'])
            write_json(audit, value, gid)
    finally:
        os.close(fd)
    value['status'] = 'completed'
    write_json(audit, value, gid)
    remaining = [r for r in value['rows'] if r['name'] not in value['removed']]
    summary = dict(checkedAt=time.time(), status='completed', deleted=len(value['removed']),
                   releasedBytes=sum(r['bytes']+r['sidecarBytes'] for r in value['delete']),
                   retained=len(remaining), retainedBytes=sum(r['bytes'] for r in remaining),
                   softBudgetBytes=SOFT_BUDGET, audit=str(audit))
    summary['overBudget'] = summary['retainedBytes'] > SOFT_BUDGET
    write_json(directory/'current.json', summary, gid)
    return summary


def after_success(root, journal, error=None):
    """Only the successful daily publisher calls this, still inside release.lock.

    Housekeeping errors do not rewrite successful publication receipts. The
    separate failed state is consumed by the independent operations watchdog.
    """
    if (error is not None or journal.mode != 'update' or not journal.published or
        journal.validation != 'passed' or not getattr(journal, 'runtime_accepted', False)):
        return {'status': 'skipped'}
    directory = root/'shared/backup-retention'
    now = time.time()
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('retention must be initialized by operator')
        value = make_plan(root/'shared/data-store/backups', now)
        latest = max(value['rows'], key=lambda r: r['createdAt'])
        if latest['createdAt'] < journal.started/1000-1:
            raise ValueError('successful job did not create a fresh verified backup')
        require_restore_proof(directory, value['rows'])
        return apply_plan(root/'shared/data-store/backups', value, directory, journal.gid)
    except Exception as failure:
        summary = dict(checkedAt=now, status='failed', errorCode=type(failure).__name__)
        write_json(directory/'current.json', summary, journal.gid)
        return summary
