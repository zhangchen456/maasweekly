"""Bounded fetching + pure parsing. Archive writes remain in one caller after gather."""
from __future__ import annotations
import asyncio
import dataclasses
import hashlib
import json
import time
import uuid
from urllib.parse import urlsplit
from .base import SourceSpec
from .extractors import get_extractor
from .normalize import normalize_and_validate
from .providers import provider_for, PlaywrightSourceProvider


async def collect(entries, *, journal=None, concurrency=2, offline=None, timeout=120, retries=1, backoff=1, domain_interval=1):
    if concurrency not in (1, 2, 3): raise ValueError('concurrency must be 1, 2 or 3')
    gate = asyncio.Semaphore(concurrency); domains = {}; last_start = {}
    async def one(entry):
        async with gate:
            started = time.monotonic(); source = entry.source_key; extractor = get_extractor(source)
            state = journal.data['sources'].get(source, {}) if journal else {}
            attempt = state.get('attemptId') if journal and journal.recover and state.get('snapshot') else 'attempt_' + uuid.uuid4().hex
            version = extractor.version
            if state.get('snapshot') and state.get('extractorVersion') not in (None, version):
                raise ValueError('staged extractor version differs; use the matching implementation')
            if journal: journal.source_result(source, {'attemptId': attempt, 'phase': 'fetching', 'extractorVersion': version, 'rulesVersion': 'normalize-1', 'schemaVersion': 1})
            failure_phase = 'fetch'
            snap = offline.get(source) if offline else None
            if snap is None and journal and journal.recover: snap = journal.snapshot(source)
            tried = 0
            attempts = list(state.get('attempts', []))
            try:
                if snap is None:
                    domain = urlsplit(entry.url).hostname or source
                    lock = domains.setdefault(domain, asyncio.Lock())
                    for tried in range(retries + 1):
                        attempt = 'attempt_' + uuid.uuid4().hex
                        if journal: journal.source_result(source, {'attemptId': attempt, 'attempts': attempts})
                        try:
                            async with lock:
                                delay = domain_interval - (time.monotonic() - last_start.get(domain, 0))
                                if delay > 0: await asyncio.sleep(delay)
                                last_start[domain] = time.monotonic()
                                spec = SourceSpec(source_key=source, provider_id=entry.provider_id, url=entry.url, fetcher_version=entry.fetcher_version)
                                snap = await asyncio.wait_for(provider_for(source).fetch(spec), timeout)
                            attempts.append({'attemptId': attempt, 'outcome': 'success', 'completedAt': time.time()})
                            break
                        except Exception:
                            attempts.append({'attemptId': attempt, 'outcome': 'failed', 'completedAt': time.time()})
                            if journal: journal.source_result(source, {'attempts': attempts})
                            if tried == retries: raise
                            await asyncio.sleep(backoff * (2 ** tried))
                if snap.source_key != source: raise ValueError('offline source mismatch')
                if hashlib.sha256(snap.content.encode()).hexdigest() != snap.sha256: raise ValueError('snapshot content hash mismatch')
                if journal: journal.stage_snapshot(source, snap, attempt)
                failure_phase = 'parse'
                # Parsing failures do not trigger another HTTP request.
                result = extractor.extract(snap); report = normalize_and_validate(result)
                if not report.accepted: raise ValueError('all facts rejected; probable structure drift')
                raw = json.dumps(dataclasses.asdict(result), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                value = {'attemptId': attempt, 'attempts': attempts, 'outcome': 'success', 'phase': 'parsed', 'extractorVersion': version,
                         'elapsedMs': (time.monotonic() - started) * 1000, 'retries': tried, 'parsedCount': len(report.accepted),
                         'validation': 'passed' if report.ok else 'failed', 'rejectedCount': len(report.rejected),
                         'outputSha256': hashlib.sha256(raw.encode()).hexdigest(), 'processingKey': hashlib.sha256((snap.sha256 + ':' + version + ':normalize-1').encode()).hexdigest(),
                         'observationKey': hashlib.sha256((snap.sha256 + ':' + version + ':' + str(snap.fetched_at)).encode()).hexdigest(),
                         'lastSuccessAt': snap.fetched_at, 'successAgeHours': max(0, (time.time() - snap.fetched_at) / 3600)}
                if journal: journal.source_result(source, value)
                return entry, snap, result, report, None, value
            except Exception as error:
                value = {'attemptId': attempt, 'attempts': attempts, 'outcome': 'failed', 'phase': 'failed', 'extractorVersion': version,
                         'elapsedMs': (time.monotonic() - started) * 1000, 'retries': tried, 'errorCode': type(error).__name__, 'failurePhase': failure_phase, 'parsedCount': 0}
                if journal: journal.source_result(source, value)
                return entry, snap, None, None, error, value
    try:
        results = await asyncio.gather(*(one(entry) for entry in entries), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException): raise result
        return results
    finally:
        await PlaywrightSourceProvider.shutdown()
