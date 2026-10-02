#!/usr/bin/env python3
"""Evaluate a bounded resource snapshot; never change production state."""
import argparse
import json
import math
from pathlib import Path


def evaluate(snapshot, policy):
    if policy.get('schemaVersion') != 1 or policy.get('mode') != 'advisory':
        raise ValueError('unsupported budget policy')
    results = []
    for name, rule in policy['metrics'].items():
        value = snapshot.get('metrics', {}).get(name)
        if value is None:
            results.append({'metric': name, 'state': 'unmeasured'})
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid metric: ' + name)
        if rule['direction'] == 'high':
            if not 0 <= rule['warning'] < rule['critical']: raise ValueError('invalid high budget')
            state = 'critical' if value >= rule['critical'] else 'warning' if value >= rule['warning'] else 'ok'
        elif rule['direction'] == 'low':
            if not 0 <= rule['critical'] < rule['warning']: raise ValueError('invalid low budget')
            state = 'critical' if value <= rule['critical'] else 'warning' if value <= rule['warning'] else 'ok'
        else:
            raise ValueError('invalid budget direction')
        results.append({'metric': name, 'value': value, 'state': state})
    return {'schemaVersion': 1, 'observedAt': snapshot.get('observedAt'), 'mode': 'advisory',
            'results': results, 'alerts': [r for r in results if r['state'] in ('warning', 'critical')]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--policy', type=Path, default=Path(__file__).resolve().parents[1] / 'ops/resource-budget.json')
    args = parser.parse_args()
    report = evaluate(json.loads(args.snapshot.read_text()), json.loads(args.policy.read_text()))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if any(r['state'] == 'critical' for r in report['results']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
