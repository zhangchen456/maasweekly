"""Durable, credential-free pipeline receipts for the unprivileged monitor relay."""
import hashlib
import importlib.util
import json
import os
import pwd
import re
import stat
import tempfile
import time
import uuid
from pathlib import Path


def boot_id():
    try:
        value=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return value if re.fullmatch(r'[a-f0-9-]{36}',value) else None
    except OSError:return None


def process_alive(job):
    try:
        if job.get('bootId') and job['bootId']!=boot_id():return False
        if not job.get('bootId'):
            started=job.get('startedAt')
            boot=next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
            if type(started) is int and started<boot*1000:return False
        pid=job['pid']
        if type(pid) is not int or pid<=1 or not re.fullmatch(r'\d+',job['processStart']):return False
        actual=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        return actual==job['processStart']
    except (OSError,KeyError,TypeError,ValueError,StopIteration):return False


def _read_metadata(path,limit=4*1024*1024):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('invalid monitor metadata')
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('monitor metadata too large')
        return json.loads(raw)
    finally:os.close(fd)


def reconcile_interrupted(shared,*,stop_orphan,gid=None,now=None,alive=process_alive):
    """Caller holds release.lock. Close dead attempts without discarding checkpoints.

    Unknown exit times are recorded at detection, without an invented elapsedMs.
    A durable final receipt wins over an interrupted final metadata write.
    """
    root=Path(shared)/'pipeline-monitor';observed=int(time.time()*1000) if now is None else now
    if root.resolve()!=root or (root/'inbox').resolve()!=root/'inbox':raise ValueError('unsafe monitor root')
    candidates={}
    for name in ['current.json','daily.json']:
        path=root/name
        if not path.exists():continue
        value=_read_metadata(path,65536)
        if value.get('state')!='running':continue
        if (value.get('schemaVersion')!=1 or not re.fullmatch(r'pipeline_[a-f0-9]{32}',value.get('id',''))
                or not re.fullmatch(r'[a-f0-9]{40}',value.get('codeCommit',''))
                or not re.fullmatch(r'[-a-z]+',value.get('mode',''))
                or not re.fullmatch(r'[-a-z]+',value.get('stage',''))
                or type(value.get('pid')) is not int or value['pid']<=1
                or type(value.get('startedAt')) is not int or value['startedAt']>observed):
            raise ValueError('invalid interrupted job metadata')
        candidates[value['id']]=value
    recovered=[]
    for identifier,original in candidates.items():
        if alive(original):continue
        terminal=None;stages=[]
        for path in (root/'inbox').glob('report_*.json'):
            value=_read_metadata(path)
            for run in value.get('batch',{}).get('runs',[]):
                if str(run.get('id','')).startswith(identifier+'_s'):stages.append(run)
                if run.get('id')==identifier+'_job':
                    if terminal is not None and terminal!=run:raise ValueError('conflicting terminal receipts')
                    terminal=run
        audit={'observedAt':observed,'original':original,
               'actualExitTimeUnknown':terminal is None,'existingTerminalReceipt':terminal is not None}
        write_json(root/'reconciled'/(identifier+'.json'),audit,gid)
        audit['orphanCleanup']=stop_orphan(original)
        if terminal is None:
            attempted=original['stage'] in ['publication','runtime-acceptance'] or any(r.get('stage')=='publication' for r in stages)
            validated=any(r.get('stage')=='ssr-validation' and r.get('state')=='succeeded' and r.get('validation')=='passed' for r in stages)
            published=False;publication=Path(shared)/'public-data/v1/publication.json'
            if attempted and validated and publication.exists():
                actual=_read_metadata(publication)
                published=(actual.get('datasetVersion')==original.get('datasetVersion')
                    and actual.get('site',{}).get('inputVersion')==original.get('inputVersion')
                    and actual.get('site',{}).get('codeCommit')==original['codeCommit'])
            audit['publishedPointerMatchesInterruptedTarget']=published
            run={'id':identifier+'_job','kind':'data-pipeline','trigger':original.get('trigger','unknown'),
                 'state':'succeeded' if published else 'failed','stage':original['mode'],'startedAt':original['startedAt'],
                 'finishedAt':observed,'observedAt':observed,'inputVersion':original.get('inputVersion'),
                 'outputVersion':original.get('inputVersion'),'result':'partial' if published else 'failed','validation':'passed' if validated else 'not_run',
                 'publication':'completed' if published else 'not_run','errorCode':'interrupted','runLink':original.get('runLink'),'sources':[]}
            name,value=report({'schemaVersion':1,'batchId':identifier+'_interrupted','sources':[],'runs':[run]})
            write_json(root/'inbox'/name,value,gid);terminal=run
        succeeded=terminal.get('state')=='succeeded' and terminal.get('result') in ['success','unchanged']
        if terminal.get('state') not in ['succeeded','failed','cancelled'] or type(terminal.get('finishedAt')) is not int:
            raise ValueError('invalid existing terminal receipt')
        final={**original,'state':'succeeded' if succeeded else 'failed','stage':'finished',
               'updatedAt':terminal['finishedAt'],'failureStage':None if succeeded else original.get('failureStage') or original['stage'],
               'errorCode':None if succeeded else terminal.get('errorCode') or 'interrupted'}
        # Persist the evidence before replacing either pointer; replay is idempotent.
        write_json(root/'reconciled'/(identifier+'.json'),audit,gid)
        for name in ['current.json','daily.json']:
            path=root/name
            if path.exists():
                current=_read_metadata(path,65536)
                if current.get('id')==identifier and current.get('state')=='running':write_json(path,final,gid)
        recovered.append({'id':identifier,'state':final['state']})
    return recovered


def write_json(path, value, gid=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    if path.parent.is_symlink() or path.parent.resolve() != path.parent:
        raise ValueError('monitor directory must be a real absolute path')
    if gid is not None:
        os.chown(path.parent, 0, gid)
        path.parent.chmod(0o750)
    body = (json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode()
    if len(body) > 4 * 1024 * 1024:
        raise ValueError('monitor report too large')
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body); stream.flush(); os.fsync(stream.fileno())
            if gid is not None: os.fchown(stream.fileno(), 0, gid)
            os.fchmod(stream.fileno(), 0o640)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def report(batch, contexts=()):
    value = {'schemaVersion': 'pipeline-report-v1', 'batch': batch, 'contexts': list(contexts)}
    # Immutable name includes all metadata, so two contexts cannot overwrite one another.
    key = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return 'report_' + key + '.json', value


class RunJournal:
    def __init__(self, shared, code, mode, context=None, *, gid=None, now=None):
        self.shared = Path(shared)
        self.root = self.shared / 'pipeline-monitor'
        self.gid = gid
        self.now = now or (lambda: int(time.time() * 1000))
        self.id = 'pipeline_' + uuid.uuid4().hex
        self.boot = boot_id()
        self.code, self.mode, self.sequence = code, mode, 0
        self.started = self.now()
        self.validation, self.published = 'not_run', False
        self.failure_stage = None
        self.input_version = self.dataset_version = None
        self.trigger = {'server_schedule':'schedule','schedule': 'schedule', 'workflow_dispatch': 'manual', 'workflow_call': 'workflow'}.get((context or {}).get('GITHUB_EVENT_NAME'), 'unknown')
        repo, run = (context or {}).get('GITHUB_REPOSITORY', ''), (context or {}).get('GITHUB_RUN_ID', '')
        self.link = f'https://github.com/{repo}/actions/runs/{run}' if re.fullmatch(r'[\w.-]+/[\w.-]+', repo) and re.fullmatch(r'\d+', run) else None
        try: self.process_start = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError: self.process_start = None
        self.current('starting', 'running')

    def current(self, stage, state, error=None):
        value = {
            'schemaVersion': 1, 'id': self.id, 'mode': self.mode, 'codeCommit': self.code,
            'pid': os.getpid(), 'processStart': self.process_start, 'trigger': self.trigger,
            'bootId': self.boot,
            'startedAt': self.started, 'updatedAt': self.now(), 'stage': stage, 'state': state,
            'inputVersion': self.input_version, 'datasetVersion': self.dataset_version,
            'errorCode': error, 'failureStage': self.failure_stage, 'runLink': self.link,
        }
        write_json(self.root / 'current.json', value, self.gid)
        if self.mode == 'update':
            write_json(self.root / 'daily.json', value, self.gid)

    def receipt(self, stage, started, succeeded, *, final=False, error=None):
        self.sequence += 1
        identifier = self.id + ('_job' if final else f'_s{self.sequence}')
        completed = self.published and final
        run = {'id': identifier, 'kind': 'data-pipeline' if final else 'pipeline-stage',
               'trigger': self.trigger, 'state': 'succeeded' if succeeded or completed else 'failed',
               'stage': stage, 'startedAt': started, 'finishedAt': self.now(), 'observedAt': self.now(),
               'inputVersion': self.input_version, 'outputVersion': self.input_version,
               'result': 'success' if succeeded else 'partial' if completed else 'failed',
               'validation': self.validation, 'publication': 'completed' if completed else 'not_run',
               'errorCode': error, 'runLink': self.link, 'sources': []}
        batch = {'schemaVersion': 1, 'batchId': identifier, 'sources': [], 'runs': [run]}
        context = {'runId': identifier, 'codeCommit': self.code, 'datasetVersion': self.dataset_version,
                   'elapsedMs': run['finishedAt'] - started}
        name, value = report(batch, [context])
        write_json(self.root / 'inbox' / name, value, self.gid)

    def phase(self, stage, action, *args, **kwargs):
        self.current(stage, 'running')
        started = self.now()
        try:
            value = action(*args, **kwargs)
        except BaseException:
            self.failure_stage = self.failure_stage or stage
            if stage == 'ssr-validation': self.validation = 'failed'
            self.receipt(stage, started, False, error='validation_failed' if stage == 'ssr-validation' else 'execution_failed')
            raise
        if stage == 'ssr-validation': self.validation = 'passed'
        self.receipt(stage, started, True)
        return value

    def finish(self, error=None):
        self.receipt(self.mode, self.started, error is None, final=True,
                     error='execution_failed' if error else None)
        self.current('finished', 'failed' if error else 'succeeded', 'execution_failed' if error else None)


def export_sources(shared, package, gid=None):
    """Reuse committed stage receipts, preserving actual fetch times on replays."""
    path = Path(package) / 'tooling/scripts/monitor-collect.py'
    spec = importlib.util.spec_from_file_location('live_monitor_collector', path)
    collector = importlib.util.module_from_spec(spec)
    # Runtime packages are immutable. Source loading must neither consume nor create
    # __pycache__ entries that invalidate their verified file inventory.
    exec(compile(path.read_bytes(), str(path), 'exec'), collector.__dict__)
    batches, skipped = collector.collect(Path(shared) / 'data-store/writer', config_root=Path(package) / 'tooling')
    for batch in batches:
        # This namespace avoids changing the identity/content of pre-migration imports.
        for row in batch['runs']:
            row['id'] = 'live_' + hashlib.sha256(row['id'].encode()).hexdigest()
        key = hashlib.sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()
        batch['batchId'] = 'live_' + key
        name, value = report(batch)
        destination = Path(shared) / 'pipeline-monitor/inbox' / name
        if not destination.exists(): write_json(destination, value, gid)
    return {'batches': len(batches), 'runs': sum(len(b['runs']) for b in batches),
            'skippedWithoutReliableRecord': skipped}
