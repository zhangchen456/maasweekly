#!/usr/bin/env python3
"""Offline internal JSONL aggregation; no notification side effects."""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def aggregate(events, previous=None):
    routes = defaultdict(list)
    counts = defaultdict(lambda: defaultdict(int))
    previous = previous or {}
    alerts = dict(previous.get('activeAlerts', {}))
    source_failures = dict(previous.get('sourceFailures', {}))
    seen_attempts = set(tuple(x) for x in previous.get('seenAttempts', []))
    for event in events:
        kind = event.get('kind')
        if kind == 'api.request':
            route = event.get('route', 'unknown')
            # Reject dynamic labels even when input is not from the internal logger.
            if route not in {'/api/mcp', 'unknown', *('/api/v1/' + x for x in ('changes', 'prices', 'models', 'status', 'weekly', 'items/{id}', 'evidence/{id}', 'weekly/{id}'))}:
                route = 'unknown'
            elapsed = event.get('elapsedMs')
            if isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed >= 0:
                routes[route].append(elapsed)
            status = event.get('statusCode', 0)
            counts[route]['requests'] += 1
            if isinstance(status, int):
                if status in (409, 429): counts[route][str(status)] += 1
                if status >= 500: counts[route]['5xx'] += 1
        elif kind == 'pipeline.source':
            source = event.get('sourceId')
            if not isinstance(source, str) or not source: continue
            attempt = (event.get('runId'), source, event.get('attemptId'))
            if attempt in seen_attempts: continue
            seen_attempts.add(attempt)
            outcome = 'success' if event.get('outcome') == 'unchanged' else event.get('outcome')
            if outcome == 'success': source_failures[source] = 0
            elif outcome == 'failed': source_failures[source] = source_failures.get(source, 0) + 1
            # not_run is not a success and does not clear previous failures.
            key = 'source:' + source
            if source_failures.get(source, 0) >= 2: alerts[key] = 'two_failed_attempts'
            elif outcome == 'success': alerts.pop(key, None)
            age = event.get('successAgeHours')
            if isinstance(age, (int, float)) and age > event.get('freshnessBudgetHours', 48): alerts[key] = 'stale'
            ratio = event.get('countRatio')
            if outcome == 'success' and isinstance(ratio, (int, float)) and ratio < 0.5:
                alerts['count:' + source] = 'candidate_drop'
            elif outcome == 'success': alerts.pop('count:' + source, None)
        elif kind == 'runtime.sample':
            health = event.get('health', {})
            if not health.get('ready'): alerts['api:ready'] = 'no_dataset'
            else: alerts.pop('api:ready', None)
            if health.get('freshness') == 'stale': alerts['data:freshness'] = 'stale'
            elif health.get('freshness') == 'fresh': alerts.pop('data:freshness', None)
        elif kind == 'dataset.load':
            if event.get('result') == 'failed': alerts['data:load'] = 'load_failed'
            elif event.get('result') == 'changed': alerts.pop('data:load', None)
        elif kind == 'release.result':
            operation = event.get('operation', 'candidate')
            if operation not in ('candidate', 'preflight', 'build', 'activate', 'rollback'): continue
            key = 'release:' + operation
            if event.get('outcome') == 'failed': alerts[key] = 'candidate_failed'
            elif event.get('outcome') == 'success': alerts.pop(key, None)
    report = {}
    for route, values in counts.items():
        timings = sorted(routes[route])
        report[route] = dict(values)
        for p in (50, 95, 99):
            report[route]['p%dMs' % p] = timings[max(0, math.ceil(len(timings) * p / 100) - 1)] if timings else None
        if values.get('5xx', 0) >= 3: alerts['api:5xx:' + route] = 'three_errors_in_window'
        elif values.get('5xx', 0) == 0 and values['requests'] >= 3: alerts.pop('api:5xx:' + route, None)
    old = (previous or {}).get('activeAlerts', {})
    return {'schemaVersion': 1, 'routes': report, 'activeAlerts': alerts, 'sourceFailures': source_failures,
            'seenAttempts': [list(x) for x in sorted(seen_attempts, key=str)][-10000:],
            'transitions': [{'key': key, 'state': 'triggered', 'reason': alerts[key]} for key in sorted(alerts) if key not in old]
            + [{'key': key, 'state': 'recovered'} for key in sorted(old) if key not in alerts]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--mixed', action='store_true', help='extract internal JSON objects from CI text logs')
    parser.add_argument('--max-events', type=int, default=100000, help='bounded aggregation window; reject overflow without updating state')
    parser.add_argument('--state', type=Path, help='optional previous alert state, atomically replaced')
    args = parser.parse_args()
    previous = json.loads(args.state.read_text()) if args.state and args.state.exists() else None
    events = []
    with args.log.open() as stream:
        for line in stream:
            if args.mixed and not line.startswith('{'): continue
            if len(line) > 8192: raise ValueError('oversized diagnostic line')
            if line.strip():
                try: event = json.loads(line)
                except ValueError:
                    if args.mixed: continue
                    raise
                if not isinstance(event, dict) or not isinstance(event.get('kind'), str): continue
                events.append(event)
                if len(events) > args.max_events: raise ValueError('diagnostic window exceeds max-events')
    result = aggregate(events, previous)
    result['generatedAt'] = datetime.now(timezone.utc).isoformat()
    if args.state:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        temp = args.state.with_suffix(args.state.suffix + '.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n'); temp.replace(args.state)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
