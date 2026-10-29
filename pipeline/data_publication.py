"""Crash-recoverable public cache activation. PostgreSQL candidates precede visibility.

The manifest is the reader's atomic publication boundary. A durable prepared audit
precedes rename; a crash after rename is reconciled from its exact hash on retry.
No application restart, Astro build, tracked data write, or version deletion.
"""
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from public_export.validator import validate_release_files
from public_export.retention import checked_references


def digest(raw): return hashlib.sha256(raw).hexdigest()


def durable_write(path, raw):
    fd, name = tempfile.mkstemp(prefix='.publication-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(), 0o640)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def no_links(path):
    path = Path(path).absolute()
    for parent in [path, *path.parents]:
        if parent.is_symlink(): raise ValueError('publication symlink refused')
    return path.resolve()


def verified(root):
    no_links(root / 'publication.json')
    value = json.loads((root / 'publication.json').read_bytes())
    if not re.fullmatch('ds_[0-9a-f]{64}', value.get('datasetVersion', '')):
        raise ValueError('invalid candidate version')
    version=value['datasetVersion']
    expected={f'releases/{version}/{n}.json' for n in ['changes','items','prices','evidence','weekly','status','model-identities']}
    files=value.get('files',[])
    if len(files)!=7 or {f.get('path') for f in files}!=expected:
        raise ValueError('incomplete candidate file membership')
    for entry in files:
        if not re.fullmatch('[0-9a-f]{64}',entry.get('sha256','')) or not isinstance(entry.get('bytes'),int) or entry['bytes']<1:
            raise ValueError('invalid candidate file metadata')
    datetime.fromisoformat(value['generatedAt'].replace('Z','+00:00'))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value['dataThrough']):raise ValueError('invalid data date')
    errors = validate_release_files(root, value)
    if errors: raise ValueError('candidate failed public integrity validation')
    return value


def same_candidate(a, b):
    return all(a.get(k) == b.get(k) for k in ['datasetVersion','site','files','coverage','dataThrough'])


def activate(connection, candidate, root, expected_hash, *, allow_rollback=False, failpoint=lambda _: None):
    candidate, root = no_links(candidate), no_links(root)
    if candidate == root or candidate.is_relative_to(root) or root.is_relative_to(candidate):
        raise ValueError('candidate and cache roots must be separate')
    if expected_hash != 'empty' and not re.fullmatch('[0-9a-f]{64}', expected_hash):
        raise ValueError('expected pointer hash required')
    manifest = verified(candidate)
    site = manifest.get('site', {})
    if set(site) != {'inputVersion','codeCommit','formatVersion'} or site['formatVersion'] != 1:
        raise ValueError('candidate lacks compatible page binding')
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", ['publication:' + str(root)])
    connection.commit()
    try:
        root.mkdir(parents=True, exist_ok=True)
        no_links(root / '.publish.lock')
        with (root / '.publish.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            pointer = root / 'publication.json'
            no_links(pointer)
            raw = pointer.read_bytes() if pointer.exists() else None
            current_hash = digest(raw) if raw is not None else 'empty'
            current = json.loads(raw) if raw is not None else None
            # Initial shared-cache bootstrap retains the legacy cursor snapshots.
            if current is None and (root/'manifest.json').exists():
                no_links(root/'manifest.json')
                current=json.loads((root/'manifest.json').read_bytes())
            with connection:
                with connection.cursor() as cursor:
                    # Resolve a previous crash, without guessing from dates or versions.
                    cursor.execute("SELECT manifest_sha256,previous_manifest_sha256 FROM maas_data.data_publications WHERE root=%s AND state='prepared'", [str(root)])
                    for wanted, previous in cursor.fetchall():
                        if current_hash not in (wanted, previous):
                            raise ValueError('publication audit requires operator reconciliation')
                        cursor.execute("UPDATE maas_data.data_publications SET state=%s,published_at=CASE WHEN %s THEN now() ELSE NULL END WHERE root=%s AND manifest_sha256=%s",
                                       ['published' if current_hash == wanted else 'aborted', current_hash == wanted, str(root), wanted])
            if current and validate_release_files(root,current):raise ValueError('active data cache integrity')
            if current and same_candidate(current, manifest):
                return {'status':'already_active','manifestSha256':current_hash,'datasetVersion':manifest['datasetVersion']}
            if expected_hash != current_hash: raise ValueError('publication compare-and-swap failed')
            if current and manifest['dataThrough'] < current['dataThrough'] and not allow_rollback:
                raise ValueError('older data requires explicit rollback')
            # Only a committed, byte-matching candidate with intact page projections can activate.
            with connection.cursor() as cursor:
                cursor.execute("SELECT files,page_format_version FROM maas_data.data_candidates WHERE dataset_version=%s AND input_version=%s AND code_commit=%s",
                               [manifest['datasetVersion'],site['inputVersion'],site['codeCommit']])
                row = cursor.fetchone()
                if not row or row[0] != manifest['files'] or row[1] != 1: raise ValueError('unverified database candidate')
                cursor.execute('SELECT name,payload_json,sha256,bytes FROM maas_data.page_projections WHERE input_version=%s AND code_commit=%s', [site['inputVersion'],site['codeCommit']])
                names = set()
                for name, body, sha, size in cursor:
                    if digest(body.encode()) != sha or len(body.encode()) != size: raise ValueError('page projection integrity')
                    json.loads(body); names.add(name)
                if not {'site/src/data/'+n for n in ['daily_changes.json','weekly-digest.json','translations-en.json','record-index.json','price-record-index.json']} <= names:
                    raise ValueError('incomplete page projections')
            connection.commit()
            version = manifest['datasetVersion']
            releases = root / 'releases'; no_links(releases); releases.mkdir(mode=0o2750, exist_ok=True)
            target = no_links(releases / version)
            if target.exists():
                old = json.loads((target / 'manifest.json').read_bytes())
                if old['files'] != manifest['files'] or validate_release_files(root, old): raise ValueError('immutable release conflict')
            else:
                staging = releases / ('.candidate-' + uuid.uuid4().hex)
                # mkdir inherits the reader group and setgid from releases.
                # chmod by a non-member owner would clear that inherited bit.
                staging.mkdir(mode=0o750)
                try:
                    for entry in manifest['files']:
                        name = Path(entry['path']).name
                        source = no_links(candidate / entry['path'])
                        if not source.is_relative_to(candidate): raise ValueError('source path escape')
                        body = source.read_bytes()
                        if digest(body) != entry['sha256'] or len(body) != entry['bytes']: raise ValueError('candidate changed')
                        durable_write(staging / name, body)
                    release_manifest = {**manifest,'retainedVersions':[]}; release_manifest.pop('site',None)
                    durable_write(staging / 'manifest.json', (json.dumps(release_manifest,ensure_ascii=False,indent=2)+'\n').encode())
                    os.rename(staging, target)
                    directory=os.open(releases,os.O_RDONLY)
                    try: os.fsync(directory)
                    finally: os.close(directory)
                finally:
                    if staging.exists(): shutil.rmtree(staging)
            retained=[{'datasetVersion':version,'generatedAt':manifest['generatedAt']}]
            if current:
                previous=[r for r in current.get('retainedVersions',[]) if r['datasetVersion'] != version]
                if current['datasetVersion'] != version and not any(r['datasetVersion']==current['datasetVersion'] for r in previous):
                    previous.insert(0,{'datasetVersion':current['datasetVersion'],'generatedAt':current['generatedAt']})
                cutoff=datetime.now(timezone.utc)-timedelta(days=7)
                retained += [r for n,r in enumerate(previous) if n==0 or datetime.fromisoformat(r['generatedAt'].replace('Z','+00:00')) >= cutoff]
            checked_references(root, retained, version)
            output={**manifest,'retainedVersions':retained}
            body=(json.dumps(output,ensure_ascii=False,indent=2)+'\n').encode(); wanted=digest(body)
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("INSERT INTO maas_data.data_publications(root,manifest_sha256,previous_manifest_sha256,dataset_version,input_version,code_commit,state) VALUES (%s,%s,%s,%s,%s,%s,'prepared') ON CONFLICT(root,manifest_sha256) DO UPDATE SET state='prepared',previous_manifest_sha256=excluded.previous_manifest_sha256",
                                   [str(root),wanted,current_hash,version,site['inputVersion'],site['codeCommit']])
            failpoint('after_prepare')
            public_manifest={k:v for k,v in output.items() if k!='site'}
            durable_write(root/'manifest.json',(json.dumps(public_manifest,ensure_ascii=False,indent=2)+'\n').encode())
            failpoint('after_public_manifest')
            durable_write(pointer,body)
            failpoint('after_pointer')
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE maas_data.data_publications SET state='published',published_at=now() WHERE root=%s AND manifest_sha256=%s",[str(root),wanted])
            return {'status':'activated','manifestSha256':wanted,'datasetVersion':version,'site':site}
    finally:
        connection.rollback()
        with connection.cursor() as cursor: cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", ['publication:' + str(root)])
        connection.commit()
