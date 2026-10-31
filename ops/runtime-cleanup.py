#!/usr/bin/env python3
"""Retain current/rollback/latest-three runtimes and reclaim installed uploads.

Fixed production roots; shared business data and legacy releases are outside scope.
Use the same release lock as deployment and data publication. Default is a plan.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import time

ROOT = Path('/srv/maasweekly')
CODE = re.compile(r'[a-f0-9]{40}')
UPLOAD = re.compile(r'rl_([a-f0-9]{10})_000000000000')
YOUNG_SECONDS = 3600
MANIFEST = 'metadata/runtime-manifest.json'


def plain_directory(path):
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('directory symlink rejected: ' + str(part))
    if not path.is_dir():
        raise ValueError('directory missing: ' + str(path))


def source_file(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith('/') or any(p in ('.', '..') for p in parts):
        raise ValueError('unsafe package path')
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        if not stat.S_ISREG(os.fstat(file).st_mode):
            os.close(file); raise ValueError('non-regular package file')
        return os.fdopen(file, 'rb')
    finally:
        os.close(fd)


def metadata(path):
    plain_directory(path)
    with source_file(path, MANIFEST) as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('manifest too large')
    value = json.loads(raw)
    if (value.get('format') != 'maas-runtime-candidate-v1' or not CODE.fullmatch(value.get('codeCommit', ''))
            or value.get('dataIncluded') is not False or value.get('pageFormatVersion') != 1):
        raise ValueError('not a code-only runtime')
    files = value.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 30000:
        raise ValueError('invalid file inventory')
    seen = set(); total = 0
    for item in files:
        name = item['path']; parts = PurePosixPath(name).parts
        if (not parts or name.startswith('/') or any(p in ('.', '..') for p in parts)
                or parts[0] not in {'agent-api', 'site', 'scripts', 'tooling'} or name in seen):
            raise ValueError('unsafe/duplicate code path')
        seen.add(name)
        if 'symlink' in item:
            target = posixpath.normpath(str(PurePosixPath(name).parent / item['symlink']))
            if item['symlink'].startswith('/') or target == '..' or target.startswith('../'):
                raise ValueError('package link escape')
        else:
            size = item.get('bytes')
            if type(size) is not int or not 0 <= size <= 256 * 1024 * 1024 or not re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')):
                raise ValueError('invalid file metadata')
            total += size
    if total > 512 * 1024 * 1024:
        raise ValueError('package exceeds size budget')
    return {'path': path, 'manifest': value, 'sha256': hashlib.sha256(raw).hexdigest(),
            'mtime': (path / MANIFEST).stat().st_mtime_ns, 'bytes': total}


def tree(path):
    result = {}
    for folder, dirs, files in os.walk(path, followlinks=False):
        for p in [Path(folder), *(Path(folder) / n for n in [*dirs, *files])]:
            s = p.lstat()
            result[p.relative_to(path).as_posix()] = (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns)
    return result


def verify(package, root, *, upload=False):
    path = package['path']; declared = {f['path'] for f in package['manifest']['files']}
    expected = declared | {MANIFEST}; snapshot = tree(path)
    actual = {n for n, s in snapshot.items() if not stat.S_ISDIR(s[2])}
    link = path / 'data/public/v1'
    if not upload and link.is_symlink() and link.resolve() == (root / 'shared/public-data/v1').resolve():
        actual.discard('data/public/v1')
    if actual != expected:
        raise ValueError('unmanaged or missing files: ' + path.name)
    for item in package['manifest']['files']:
        p = path / item['path']
        if 'symlink' in item:
            if not p.is_symlink() or str(p.readlink()) != item['symlink']:
                raise ValueError('package link changed')
        else:
            with source_file(path, item['path']) as stream:
                h = hashlib.sha256(); size = 0
                while chunk := stream.read(1024 * 1024):
                    h.update(chunk); size += len(chunk)
            if size != item['bytes'] or h.hexdigest() != item['sha256']:
                raise ValueError('package bytes changed: ' + path.name)
    # Re-check metadata after traversal, including incoming files owned by the uploader.
    if metadata(path)['sha256'] != package['sha256']:
        raise ValueError('manifest changed during validation')
    if tree(path) != snapshot:
        raise ValueError('package changed during validation')
    return snapshot


def plan(root, now=None):
    now = time.time() if now is None else now
    for name in ['', 'runtime', 'incoming', 'shared']:
        plain_directory(root / name)
    shared = root / 'shared'
    if (shared / 'runtime-switch-pending.json').exists():
        raise ValueError('deployment recovery pending')
    protected = set(); required = set(); packages = {}; skipped = []
    for name in ['runtime.json', 'runtime-previous.json', 'runtime-candidate.json']:
        p = shared / name
        if not p.exists():
            if name in {'runtime.json', 'runtime-previous.json'}: raise ValueError('current/rollback state missing')
            continue
        with source_file(shared, name) as stream: state = json.load(stream)
        code = state.get('code')
        if name == 'runtime-previous.json' and code is None and 'legacy' not in state:
            raise ValueError('rollback state is invalid')
        if code is not None:
            if not isinstance(code, str) or not CODE.fullmatch(code): raise ValueError('invalid protected code')
            protected.add(code)
            if name != 'runtime-candidate.json': required.add(code)
    with source_file(shared, 'runtime.json') as stream: current = json.load(stream)['code']
    pointer = root / 'current'
    if not pointer.is_symlink() or pointer.resolve() != root / 'runtime' / current:
        raise ValueError('active pointer/state mismatch')
    for slot in ['blue', 'green']:
        p = shared / 'slots' / (slot + '.env')
        if p.exists():
            with source_file(shared, 'slots/' + p.name) as stream: lines = stream.read().decode().splitlines()
            for line in lines:
                if line.startswith('MAAS_RELEASE_DIR='):
                    release = Path(line.split('=', 1)[1])
                    if release.parent == root / 'runtime' and CODE.fullmatch(release.name): protected.add(release.name)
    for p in (root / 'runtime').iterdir():
        if not CODE.fullmatch(p.name) or p.is_symlink() or not p.is_dir(): continue
        try:
            if p.stat().st_uid != os.geteuid(): raise ValueError('runtime is not owned by cleanup operator')
            entry = metadata(p)
            if entry['manifest']['codeCommit'] != p.name: raise ValueError('directory/code mismatch')
            packages[p.name] = entry
        except (OSError, ValueError, KeyError, TypeError) as error:
            skipped.append({'path': str(p), 'reason': str(error)})
    if not required <= packages.keys(): raise ValueError('current/rollback runtime missing or invalid')
    latest = sorted(packages, key=lambda c: (packages[c]['mtime'], c), reverse=True)[:3]
    protected.update(latest)
    uploads = []
    for p in (root / 'incoming').iterdir():
        match = UPLOAD.fullmatch(p.name)
        if not match or p.is_symlink() or not p.is_dir(): continue
        candidates = [c for c in packages if c.startswith(match[1])]
        if len(candidates) != 1: continue
        code = candidates[0]
        # Keep its installed counterpart until this upload is safely old enough.
        age = now - max(p.stat().st_mtime, (p / MANIFEST).stat().st_mtime if (p / MANIFEST).exists() else now)
        if age < YOUNG_SECONDS:
            protected.add(code); continue
        try:
            entry = metadata(p)
            if entry['sha256'] != packages[code]['sha256']: raise ValueError('upload differs from installed manifest')
            uploads.append(entry)
        except (OSError, ValueError, KeyError, TypeError) as error:
            skipped.append({'path': str(p), 'reason': str(error)})
    public = {'status': 'planned', 'protected': sorted(protected), 'latestThree': latest,
              'removeRuntime': sorted(packages.keys() - protected),
              'removeUploads': [p['path'].name for p in uploads], 'skipped': skipped,
              'estimatedPackageBytes': sum(packages[c]['bytes'] for c in packages.keys() - protected) + sum(p['bytes'] for p in uploads)}
    return public, packages, uploads


def apply(root, public, packages, uploads):
    if not shutil.rmtree.avoids_symlink_attacks: raise ValueError('safe directory deletion unavailable')
    # Validate every retained package before removing any sibling or upload copy.
    fingerprints = {}
    for code in public['protected']:
        if code in packages: fingerprints[str(packages[code]['path'])] = verify(packages[code], root)
    candidates = set(public['removeRuntime']) | {p['manifest']['codeCommit'] for p in uploads}
    verified = set(public['protected']) & packages.keys()
    for code in sorted(candidates - verified):
        try:
            fingerprints[str(packages[code]['path'])] = verify(packages[code], root); verified.add(code)
        except (OSError, ValueError) as error: public['skipped'].append({'path': str(packages[code]['path']), 'reason': str(error)})
    good_uploads = []
    for p in uploads:
        if p['manifest']['codeCommit'] not in verified: continue
        try:
            fingerprints[str(p['path'])] = verify(p, root, upload=True); good_uploads.append(p)
        except (OSError, ValueError) as error: public['skipped'].append({'path': str(p['path']), 'reason': str(error)})
    plain_directory(root / 'shared')
    audit_dir = root / 'shared/runtime-cleanup'; audit_dir.mkdir(mode=0o700, exist_ok=True)
    plain_directory(audit_dir)
    if audit_dir.stat().st_uid != os.geteuid() or audit_dir.stat().st_mode & 0o022:
        raise ValueError('unsafe audit directory owner or permissions')
    parent = os.open(audit_dir.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(parent)
    finally: os.close(parent)
    audit = audit_dir / (datetime.now(timezone.utc).strftime('%Y-%m-%d') + '.jsonl')
    def event(value):
        fd = os.open(audit, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or s.st_uid != os.geteuid() or s.st_mode & 0o022:
            os.close(fd); raise ValueError('invalid audit file')
        with os.fdopen(fd, 'a') as stream:
            stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **value}) + '\n'); stream.flush(); os.fsync(stream.fileno())
        directory = os.open(audit_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)
    before = shutil.disk_usage(root).free; removed = []
    targets = good_uploads + [packages[c] for c in public['removeRuntime'] if c in verified]
    event(public)
    for p in targets:
        path = p['path']; plain_directory(path)
        if metadata(path)['sha256'] != p['sha256'] or tree(path) != fingerprints[str(path)]:
            raise ValueError('delete target changed')
        event({'action': 'remove', 'path': str(path), 'manifestSha256': p['sha256']})
        shutil.rmtree(path); removed.append(str(path))
        event({'action': 'removed', 'path': str(path)})
    result = {**public, 'status': 'completed_with_skips' if public['skipped'] else 'completed',
              'removed': removed, 'freedBytes': shutil.disk_usage(root).free - before}
    event(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true'); mode.add_argument('--plan', action='store_true'); args = parser.parse_args()
    if os.geteuid() != 0: raise ValueError('root required')
    plain_directory(ROOT / 'locks')
    with (ROOT / 'locks/release.lock').open('a+b') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'deferred', 'reason': 'deployment/data job holds release lock'})); return
        public, packages, uploads = plan(ROOT)
        result = apply(ROOT, public, packages, uploads) if args.apply else public
        print(json.dumps(result), flush=True)
        if args.apply and result['skipped']: raise SystemExit(3)


if __name__ == '__main__': main()
