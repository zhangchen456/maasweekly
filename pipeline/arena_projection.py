"""Materialize the board from the same committed official source observation."""
from datetime import datetime, timezone
import json
import re
from arena_source import FORMAT, URL, fetch_dataset


def from_snapshot(text):
    lines = text.splitlines()
    if FORMAT not in lines:
        return None  # Historical website snapshots are not official dataset rows.
    start = lines.index(FORMAT)
    normalized = lines[start:]
    published = normalized[3].removeprefix('Leaderboard published: ')
    release = re.fullmatch(r'Release: ([a-f0-9]{40}); file sha256: ([a-f0-9]{64})', normalized[5])
    if not release:
        raise ValueError('invalid Arena release attribution')
    rows = [{**json.loads(line), 'leaderboard_publish_date': published} for line in normalized[6:]]
    revision, sha = release.groups()
    if fetch_dataset(URL, load=lambda: (rows, revision, sha)) != '\n'.join(normalized):
        raise ValueError('invalid Arena normalized snapshot')
    fetched = re.search(r'^<!-- fetched: ([^>]+) -->$', text, re.M)
    if not fetched:
        raise ValueError('missing Arena collection timestamp')
    stamp = fetched[1]
    observed = (datetime.fromtimestamp(float(stamp), timezone.utc) if re.fullmatch(r'[\d.]+', stamp)
                else datetime.fromisoformat(stamp.replace('Z', '+00:00')))
    if observed.tzinfo is None:
        raise ValueError('Arena collection timestamp lacks timezone')
    collected = observed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    ordered = sorted(rows, key=lambda r: (r['rank'], r['model_name']))
    count = len(rows); shown = min(10, count)
    return {
        'source': 'Arena official dataset · Text / overall', 'source_url': URL,
        'snapshot_date': published, 'collected_at': collected, 'manual': False,
        'row_count': count, 'release_revision': revision, 'file_sha256': sha,
        'citation': f'Source: Arena · CC BY 4.0 · Collected {collected}',
        'note': f'官方 Text Arena 总榜，展示 {count} 条记录中的前 {shown} 条。日期为上游榜单发布日期；分数与其他评测不可直接比较。',
        'note_en': f'Official Text Arena overall leaderboard. Showing the first {shown} of {count} records. The date is the upstream publication date; scores are not comparable across benchmarks.',
        'top': [{'rank': r['rank'], 'model': r['model_name'], 'vendor': r['organization'],
                 'elo': round(r['rating'], 1), 'rating': r['rating'], 'votes': r['vote_count']} for r in ordered[:10]],
    }


def from_view(view):
    if not hasattr(view, 'iter_raw_snapshots'):
        return None
    for _, text in view.iter_raw_snapshots('data/snapshots/*/LMArena__industry__*.md'):
        board = from_snapshot(text)
        if board is not None:
            return board
    return None
