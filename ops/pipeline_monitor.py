"""Durable, credential-free pipeline receipts for the unprivileged monitor relay."""
import hashlib
import importlib.util
import json
import os
import pwd
import re
import tempfile
import time
import uuid
from pathlib import Path


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
        self.code, self.mode, self.sequence = code, mode, 0
        self.started = self.now()
        self.validation, self.published = 'not_run', False
        self.input_version = self.dataset_version = None
        self.trigger = {'schedule': 'schedule', 'workflow_dispatch': 'manual', 'workflow_call': 'workflow'}.get((context or {}).get('GITHUB_EVENT_NAME'), 'unknown')
        repo, run = (context or {}).get('GITHUB_REPOSITORY', ''), (context or {}).get('GITHUB_RUN_ID', '')
        self.link = f'https://github.com/{repo}/actions/runs/{run}' if re.fullmatch(r'[\w.-]+/[\w.-]+', repo) and re.fullmatch(r'\d+', run) else None
        try: self.process_start = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError: self.process_start = None
        self.current('starting', 'running')

    def current(self, stage, state, error=None):
        write_json(self.root / 'current.json', {
            'schemaVersion': 1, 'id': self.id, 'mode': self.mode, 'codeCommit': self.code,
            'pid': os.getpid(), 'processStart': self.process_start,
            'startedAt': self.started, 'updatedAt': self.now(), 'stage': stage, 'state': state,
            'inputVersion': self.input_version, 'datasetVersion': self.dataset_version,
            'errorCode': error,
        }, self.gid)

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
    collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)
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
