#!/usr/bin/env python3
"""Check formal publication age, independently of rolling-summary job success."""
import argparse
from datetime import date
import json
import urllib.request


def check(rows, today, max_age_days=10):
    if not isinstance(rows, list) or not rows:
        raise ValueError('no formal weekly reports')
    dates = [date.fromisoformat(row['date']) for row in rows]
    latest = max(dates)
    age = (today - latest).days
    if age < 0:
        raise ValueError('formal report period is in the future')
    if age > max_age_days:
        raise ValueError(f'formal weekly overdue: latest={latest}, ageDays={age}, limit={max_age_days}')
    return {'latestFormalPeriod': latest.isoformat(), 'ageDays': age, 'maxAgeDays': max_age_days}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='https://daily.maas.click/api/v1/')
    args = parser.parse_args()
    def load(relative):
        with urllib.request.urlopen(args.root.rstrip('/')+'/'+relative, timeout=30) as response:
            return json.load(response)
    payload = load('weekly?limit=1')
    rows = payload['items']
    if not rows or rows[0]['date'] != payload['coverage']['weekly']['latestId']:
        raise ValueError('formal weekly API coverage mismatch')
    from zoneinfo import ZoneInfo
    from datetime import datetime
    result = check(rows, datetime.now(ZoneInfo('Asia/Shanghai')).date())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
