"""One writer, unique executions and durable staged observations. No external queue."""
from __future__ import annotations
import fcntl
import json
import re
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from input_snapshot import POINTER, PENDING, InputView, atomic, capture, digest, put_json, restore_mutable, safe, role_files, IMMUTABLE, prune_checkpoints


_ACTIVE = None

def current_journal(): return _ACTIVE

def utc(): return datetime.now(timezone.utc).isoformat()
def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9:_-]{1,128}', value): raise ValueError('invalid run/source identifier')
    return value


class RunJournal:
    def __init__(self, root: Path, family: str, run_id=None, recover=False):
        self.root = root.resolve(); self.family = identifier(family); self.run_id = identifier(run_id or family + '_' + uuid.uuid4().hex)
        namespace = 'price-runs' if family == 'prices' else 'pipeline-runs'
        self.relative = f'data/{namespace}/staging/{self.run_id}/journal.json'
        self.path = safe(self.root, self.relative)
        self.recover = recover; self.lock = None; self.data = None; self.finalized = False
    def save(self): put_json(self.root, self.relative, self.data)
    def __enter__(self):
        global _ACTIVE
        lock = safe(self.root, 'data/.pipeline.lock'); lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock = lock.open('a+b'); fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            pending = safe(self.root, PENDING)
            if pending.exists():
                active = json.loads(pending.read_text())
                if not self.recover or active['runId'] != self.run_id or active['family'] != self.family:
                    raise ValueError('pending pipeline run: ' + active['runId'] + '; recover or discard first')
                if active['journalPath'] != self.relative: raise ValueError('pending journal mismatch')
                self.data = json.loads(self.path.read_text())
                pointer = json.loads(safe(self.root, POINTER).read_text())
                if self.data.get('commitPointer') == pointer:
                    self._complete(); self.finalized = True
                else:
                    restore_mutable(self.root, InputView(self.root, self.data['baselinePointer']))
                    self.data['state'] = 'recovering'; self.save()
            else:
                if self.recover: raise ValueError('no pending run to recover')
                if self.path.exists(): raise ValueError('execution runId already exists; use a new runId')
                capture(self.root, self.run_id + '_baseline')
                pointer = json.loads(safe(self.root, POINTER).read_text())
                self.data = {'schemaVersion': 1, 'runId': self.run_id, 'family': self.family, 'state': 'running',
                             'startedAt': utc(), 'runDate': datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'),
                             'baselinePointer': pointer, 'sources': {}, 'rawBackups': {}}
                self.save(); put_json(self.root, PENDING, {'runId': self.run_id, 'family': self.family, 'journalPath': self.relative})
            _ACTIVE = self
            return self
        except BaseException:
            self.lock.close(); self.lock = None; raise
    def backup_raw(self, relative):
        if relative in self.data['rawBackups']: return
        p = safe(self.root, relative)
        if p.exists():
            raw = p.read_bytes(); target = f'data/snapshots/content/{digest(raw)}.raw'; q = safe(self.root, target)
            if not q.exists(): atomic(q, raw)
            self.data['rawBackups'][relative] = target
        else: self.data['rawBackups'][relative] = None
        self.save()
    def stage_snapshot(self, source, snapshot, attempt_id):
        from dataclasses import asdict
        value = asdict(snapshot); content = value.pop('content'); raw = content.encode('utf-8')
        if digest(raw) != snapshot.sha256: raise ValueError('snapshot content hash mismatch')
        relative = f'data/snapshots/content/{snapshot.sha256}.html'
        p = safe(self.root, relative)
        if p.exists():
            if p.read_bytes() != raw: raise ValueError('source content collision')
        else: atomic(p, raw)
        state = self.data['sources'].setdefault(identifier(source), {})
        state.update({'snapshot': value, 'contentPath': relative, 'attemptId': attempt_id, 'phase': 'fetched'})
        self.save()
    def snapshot(self, source):
        from pricing.base import ContentSnapshot
        state = self.data['sources'].get(source, {})
        if 'snapshot' not in state: return None
        meta = state['snapshot']; raw = safe(self.root, state['contentPath']).read_bytes()
        if digest(raw) != meta['sha256']: raise ValueError('staged source content hash mismatch')
        return ContentSnapshot(**meta, content=raw.decode('utf-8'))
    def source_result(self, source, value):
        state = self.data['sources'].setdefault(identifier(source), {}); state.update(value); self.save()
    def _complete(self):
        self.data['state'] = 'committed'; self.save()
        namespace = 'price-runs' if self.family == 'prices' else 'pipeline-runs'
        record = {**self.data, 'run_id': self.run_id, 'date': self.data['runDate']}
        put_json(self.root, f'data/{namespace}/{self.data["runDate"]}/{self.run_id}.json', record)
        pending = safe(self.root, PENDING)
        if pending.exists(): pending.unlink()
        prune_checkpoints(self.root, self.data['commitPointer'])
    def finish(self, outcome, accepted_versions=()):
        version = capture(self.root, self.run_id, publish=False)
        pointer = {'schemaVersion': 1, 'inputVersion': version, 'manifestPath': f'data/input-manifests/{version}.json'}
        baseline = self.data['baselinePointer']
        previous = baseline['inputVersion'] if baseline['inputVersion'] != version else baseline.get('previousInputVersion')
        if previous: pointer['previousInputVersion'] = previous
        self.data.update({'state': 'committing', 'outcome': outcome, 'completedAt': utc(), 'inputVersion': version,
                          'accepted_versions': list(accepted_versions), 'commitPointer': pointer})
        self.save()
        # This atomic pointer is the commit point. Recovery only completes bookkeeping afterwards.
        put_json(self.root, POINTER, pointer)
        self._complete()
        return version
    def discard(self):
        if self.finalized: raise ValueError('run already committed; discard is forbidden')
        pointer = self.data['baselinePointer']; baseline = InputView(self.root, pointer)
        for logical in baseline.files:
            if logical.startswith(IMMUTABLE): baseline.path(logical)
        # New archival leaves belong to this uncommitted run. Quarantine them, retaining bytes.
        # Leaving new revisions in the active archive would violate the existing current/chain contract.
        quarantined = []
        for logical, path in role_files(self.root).items():
            if not logical.startswith(IMMUTABLE) or logical in baseline.files: continue
            target = safe(self.root, str(Path(self.relative).parent / 'discarded' / logical))
            target.parent.mkdir(parents=True, exist_ok=True); path.replace(target); quarantined.append(logical)
            if logical.startswith(('data/record-revisions/', 'data/price-record-revisions/')) and not any(path.parent.iterdir()): path.parent.rmdir()
        self.data['quarantined'] = quarantined
        restore_mutable(self.root, baseline)
        for relative, backup in self.data['rawBackups'].items():
            target = safe(self.root, relative)
            if backup: atomic(target, safe(self.root, backup).read_bytes())
            elif target.exists(): target.unlink()
        put_json(self.root, POINTER, pointer)
        self.data.update({'state': 'discarded', 'completedAt': utc()}); self.save(); safe(self.root, PENDING).unlink()
    def __exit__(self, exc_type, exc, traceback):
        global _ACTIVE
        _ACTIVE = None
        try:
            if exc is not None and self.data and self.data['state'] != 'committed':
                self.data.update({'state': 'interrupted', 'errorCode': type(exc).__name__}); self.save()
        finally:
            if self.lock: self.lock.close(); self.lock = None


def source_event(journal, source_id, state):
    # Fixed internal fields, no source URL, credential, request body or exception text.
    event = {'timestamp': utc(), 'kind': 'pipeline.source', 'runId': journal.run_id, 'sourceId': source_id,
             'attemptId': state.get('attemptId'), 'extractorVersion': state.get('extractorVersion'),
             'outcome': state.get('outcome'), 'elapsedMs': state.get('elapsedMs'),
             'retries': state.get('retries', 0), 'parsedCount': state.get('parsedCount', 0),
             'lastSuccessAt': state.get('lastSuccessAt'), 'successAgeHours': state.get('successAgeHours'),
             'countRatio': state.get('countRatio'), 'freshnessBudgetHours': state.get('freshnessBudgetHours', 48)}
    print(json.dumps(event, ensure_ascii=False), flush=True)


def managed_entry(callback, root, family, configure=None, *, allow_dry=False):
    """CLI lifecycle for synchronous writers. Imported pure/fixture entrypoints remain callable."""
    global _ACTIVE
    import argparse
    import sys
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--input-root', type=Path, default=root)
    lifecycle = parser.add_mutually_exclusive_group()
    lifecycle.add_argument('--run-id'); lifecycle.add_argument('--recover'); lifecycle.add_argument('--discard-run')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--retry-failed', type=Path); parser.add_argument('--offline-snapshot', type=Path)
    args, rest = parser.parse_known_args()
    if '--help' in rest or '-h' in rest:
        parser.print_help(); return 0
    if (args.recover or args.discard_run) and args.dry_run: parser.error('dry-run cannot recover/discard')
    selected = args.input_root.resolve()
    if configure: configure(selected)
    sys.argv = [sys.argv[0], *rest]
    if args.dry_run:
        if allow_dry:
            sys.argv.append('--dry-run')
            if args.offline_snapshot:
                record = json.loads(args.offline_snapshot.read_text())
                if record.get('family') != family or record.get('state') != 'committed': raise ValueError('saved run family/state mismatch')
                run = RunJournal(selected, family); run.data = {**record, 'offline': True}; _ACTIVE = run
                try: return callback()
                finally: _ACTIVE = None
            return callback()
        print('dry-run: managed writer skipped; no canonical files changed'); return 0
    # Read-only checks/debug archive injection keep their established isolated semantics.
    if '--check' in rest or '--archive-root' in rest: return callback()
    if family in ('daily-summary', 'weekly-summary'):
        import os
        if not os.environ.get('LLM_API_KEY'): return callback()
    run_id = args.recover or args.discard_run or args.run_id
    with RunJournal(selected, family, run_id, recover=bool(args.recover or args.discard_run)) as journal:
        if args.discard_run: journal.discard(); return 0
        if journal.finalized: return 0
        if journal.recover and journal.data.get('argv') != rest: raise ValueError('recovery arguments differ from the original run')
        journal.data['argv'] = rest
        previous = args.retry_failed or args.offline_snapshot
        if previous and not journal.recover:
            record = json.loads(previous.read_text())
            if record.get('family') != family or record.get('state') != 'committed': raise ValueError('saved run family/state mismatch')
            journal.data['retrySources'] = record['sources']
            journal.data['selectedSources'] = [key for key, state in record['sources'].items() if args.offline_snapshot or state.get('outcome') == 'failed']
            if args.retry_failed and not journal.data['selectedSources']:
                journal.finish('not_run'); return 0
            if args.offline_snapshot:
                journal.data.update({'offline': True, 'sources': record['sources'], 'runDate': record['runDate'], 'startedAt': record['startedAt'], 'comparisonPaths': record.get('comparisonPaths', {})})
        journal.save()
        value = callback(); code = int(value or 0)
        journal.finish(journal.data.get('outcome') or ('failed' if code else 'partial' if any(s.get('outcome') == 'failed' for s in journal.data['sources'].values()) else 'unchanged' if journal.data['sources'] and all(s.get('outcome') == 'unchanged' for s in journal.data['sources'].values()) else 'success'))
        return code
