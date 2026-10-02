"""Durable synchronous observations for source and leaderboard collectors.
The caller owns serial normalization/projection; only transport errors are retried.
"""
from __future__ import annotations
import hashlib
import json
import time
import uuid
from pricing.base import ContentSnapshot
from run_protocol import current_journal, source_event


def source_key(url): return 'http_' + hashlib.sha256(url.encode()).hexdigest()[:24]

def wanted(url):
    run = current_journal()
    return not run or not run.data.get('selectedSources') or source_key(url) in run.data['selectedSources']


def publish_state(run, key, state):
    if run.data.get('offline'): return
    from data_store import read, write
    relative = 'data/normalized/source-runtime.json'
    states = read(run.root, relative, {})
    old = states.get(key, {})
    stamp = state.get('lastSuccessAt') if state.get('outcome') in ('success', 'unchanged') else state.get('latestAttemptAt', time.time())
    if stamp < old.get('latestAttemptAt', 0): return
    count = state.get('parsedCount', 0)
    if state.get('outcome') == 'success' and state.get('processingKey') == old.get('processingKey'): state['outcome'] = 'unchanged'
    previous_count = old.get('lastSuccessCount')
    state['countRatio'] = count / previous_count if previous_count else None
    last = state.get('lastSuccessAt') or old.get('lastSuccessAt')
    if last: state.update(lastSuccessAt=last, successAgeHours=max(0, (time.time() - last) / 3600))
    states[key] = {'sourceId': state.get('sourceId', key), 'outcome': state['outcome'], 'latestAttemptAt': stamp,
                   'lastSuccessAt': last, 'lastSuccessCount': count if state['outcome'] in ('success', 'unchanged') else previous_count, 'processingKey': state.get('processingKey') or old.get('processingKey')}
    write(run.root, relative, states)


def fetch(url, callback, *, version, source_id=None, retries=1, count=None):
    run = current_journal(); key = source_key(url); started = time.monotonic()
    if not run: return callback()
    previous = run.data['sources'].get(key, {})
    snapshot = run.snapshot(key) if run.recover or run.data.get('offline') else None
    if snapshot:
        if snapshot.fetcher_version != version: raise ValueError('saved processing version differs')
        if previous.get('snapshotErrorCode'):
            state = {**previous, 'outcome': 'failed', 'phase': 'failed', 'errorCode': 'schema_failed',
                     'parsedCount': 0, 'latestAttemptAt': snapshot.fetched_at}
            if not run.data.get('offline'):
                publish_state(run, key, state); run.source_result(key, state)
            source_event(run, source_id or key, {**state, 'outcome': 'not_run'} if run.data.get('offline') else state)
            return None, 'JSON 结构非法'
        sha = hashlib.sha256(snapshot.content.encode()).hexdigest()
        state = {**previous, 'outcome': previous.get('outcome', 'success'), 'phase': 'parsed',
                 'extractorVersion': version, 'sourceId': source_id or key,
                 'parsedCount': count(snapshot.content) if count else len(snapshot.content.splitlines()),
                 'lastSuccessAt': snapshot.fetched_at, 'latestAttemptAt': snapshot.fetched_at,
                 'processingKey': hashlib.sha256((sha + ':' + version).encode()).hexdigest(), 'outputSha256': sha,
                 'successAgeHours': max(0, (time.time() - snapshot.fetched_at) / 3600)}
        publish_state(run, key, state)
        if not run.data.get('offline'): run.source_result(key, state)
        source_event(run, source_id or key, {**state, 'outcome': 'not_run'} if run.data.get('offline') else state)
        return snapshot.content, None
    if run.data.get('offline'): return None, 'no_saved_snapshot'
    attempts = list(previous.get('attempts', [])); value = None; error = None
    for index in range(retries + 1):
        attempt = 'attempt_' + uuid.uuid4().hex
        run.source_result(key, {'attemptId': attempt, 'phase': 'fetching', 'sourceId': source_id or key,
                               'extractorVersion': version, 'attempts': attempts, 'snapshotErrorCode': None})
        value, error = callback()
        attempts.append({'attemptId': attempt, 'outcome': 'failed' if error else 'success', 'completedAt': time.time()})
        if not error or error in ('JSON 解析失败', '响应 data 为空', '响应缺 meta.as_of', 'JSON 结构非法'): break
        if index < retries: time.sleep(2 ** index)
    state = {'attemptId': attempt, 'attempts': attempts, 'outcome': 'failed' if error else 'success',
             'phase': 'failed' if error else 'parsed', 'extractorVersion': version, 'sourceId': source_id or key, 'latestAttemptAt': time.time(),
             'elapsedMs': (time.monotonic() - started) * 1000, 'retries': index, 'parsedCount': (count(value) if count else len(value.splitlines())) if value else 0}
    if not error:
        raw = value.encode(); sha = hashlib.sha256(raw).hexdigest(); fetched_at = time.time()
        snapshot = ContentSnapshot(snapshot_id='transport_' + sha, source_key=key, url=url, fetched_at=fetched_at,
                                   http_status=200, content_type='text/plain', sha256=sha, content=value, fetcher_version=version)
        run.stage_snapshot(key, snapshot, attempt)
        state.update(lastSuccessAt=fetched_at, successAgeHours=0, processingKey=hashlib.sha256((sha + ':' + version).encode()).hexdigest(), outputSha256=sha)
    else: state['errorCode'] = run.data['sources'].get(key, {}).get('snapshotErrorCode') or 'fetch_failed'
    publish_state(run, key, state)
    run.source_result(key, state); source_event(run, source_id or key, state)
    return value, error


def json_fetch(url, callback):
    def transport():
        value, error = callback()
        return (json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else None), error
    raw, error = fetch(url, transport, version='leaderboard-json-1', source_id='openrouter-' + url.split('/datasets/')[-1].split('?')[0], count=lambda raw: len(json.loads(raw)['data']))
    return (json.loads(raw) if raw is not None else None), error
