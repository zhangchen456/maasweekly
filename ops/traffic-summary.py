#!/usr/bin/env python3
"""Aggregate dedicated nginx JSON logs. No identities, no inferred human counts."""
import argparse, collections, datetime, gzip, json, re
BOT = re.compile(r'bot|spider|crawler|slurp|facebookexternalhit|meta-external|chatgpt|claude|curl|wget|python|httpx|headless|playwright|uptime|monitor', re.I)

def aggregate(lines):
    days = collections.defaultdict(collections.Counter)
    invalid = 0
    for line in lines:
        try:
            row = json.loads(line)
            if row['host'] not in ('daily.maas.click', 'week.maas.click', 'mw.zhangchen456.xyz'):
                continue
            day = datetime.datetime.fromisoformat(row['time']).astimezone(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
            status = int(row['status'])
            if not 100 <= status <= 599: raise ValueError('status')
            agent = row.get('agent', '')
            category = 'identified_automation' if BOT.search(agent) else 'unclassified'
            if row['path'].startswith('/api/'): category = 'api_requests'
            days[day]['requests'] += 1
            days[day][category] += 1
            days[day]['server_errors'] += int(status >= 500)
            days[day]['redirects'] += int(300 <= status < 400)
        except (ValueError, TypeError, KeyError):
            invalid += 1
    return {'timezone': 'Asia/Shanghai', 'unit': 'requests_not_visitors', 'invalidLines': invalid,
            'days': [{'date': d, **dict(c)} for d,c in sorted(days.items())]}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+')
    args=parser.parse_args()
    def lines():
        for name in args.files:
            with (gzip.open(name, 'rt') if name.endswith('.gz') else open(name)) as stream:
                yield from stream
    print(json.dumps(aggregate(lines()), ensure_ascii=False, indent=2))
