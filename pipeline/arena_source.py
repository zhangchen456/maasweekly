"""Read Arena's official latest Text/overall release (CC BY 4.0).
The website links this dataset: https://arena.ai/blog/arena-leaderboard-dataset.
Pin the Hub revision and verify the complete Parquet file before decoding it.
"""
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen

DATASET = 'lmarena-ai/leaderboard-dataset'
URL = SOURCE_URL = 'https://huggingface.co/datasets/' + DATASET
FORMAT = 'Arena official dataset: Text Arena overall (latest); format=1'
MAX_BYTES = 16 * 1024 * 1024
COLUMNS = ['model_name','organization','license','rating','rating_lower','rating_upper',
           'vote_count','rank','category','leaderboard_publish_date']


def get_bytes(url, limit):
    with urlopen(Request(url, headers={'Accept': '*/*'}), timeout=45) as response:
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('dataset response exceeds limit')
        return raw


def read_overall(path):
    import pyarrow.parquet as pq
    source = pq.ParquetFile(path)
    if not 1 <= source.metadata.num_rows <= 50000 or not set(COLUMNS) <= set(source.schema_arrow.names):
        raise ValueError('unexpected leaderboard schema or size')
    rows = []
    for batch in source.iter_batches(batch_size=1000, columns=COLUMNS, use_threads=False):
        rows.extend(r for r in batch.to_pylist() if r['category'] == 'overall')
        if len(rows) > 1000:
            raise ValueError('overall leaderboard exceeds limit')
    return rows


def load_publication():
    info = json.loads(get_bytes('https://huggingface.co/api/datasets/' + DATASET, 1048576))
    revision = info.get('sha', '')
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('invalid dataset revision')
    listing = json.loads(get_bytes('https://huggingface.co/api/datasets/' + DATASET + '/tree/' + revision + '/text', 1048576))
    files = [r for r in listing if r.get('type') == 'file' and re.fullmatch(r'text/latest-\d{5}-of-\d{5}\.parquet', r.get('path',''))]
    if len(files) != 1 or not files[0]['path'].endswith('-of-00001.parquet'):
        raise ValueError('unexpected latest release shards')
    item = files[0]; size = item.get('size'); sha = item.get('lfs',{}).get('oid','')
    if type(size) is not int or not 1 <= size <= MAX_BYTES or not re.fullmatch('[a-f0-9]{64}',sha):
        raise ValueError('invalid dataset file inventory')
    raw = get_bytes(SOURCE_URL + '/resolve/' + revision + '/' + item['path'], MAX_BYTES)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('dataset file checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='arena-dataset-') as folder:
        path = Path(folder)/'latest.parquet'; path.write_bytes(raw)
        return read_overall(path), revision, sha


def fetch_dataset(url, *, load=load_publication, today=None):
    if url != URL:
        raise ValueError('unsupported Arena dataset')
    rows, revision, sha = load()
    if not 1 <= len(rows) <= 1000:
        raise ValueError('empty or oversized leaderboard')
    seen = set(); published = None
    for row in rows:
        name = row.get('model_name')
        if not isinstance(name,str) or not name.strip() or len(name)>300 or name in seen or row.get('category')!='overall':
            raise ValueError('invalid or duplicate model')
        stamp = date.fromisoformat(row['leaderboard_publish_date'])
        if stamp > (today or date.today()) + timedelta(days=1) or published is not None and stamp != published:
            raise ValueError('mixed or future leaderboard publication')
        published = stamp; seen.add(name)
        for key in ['rating','rating_lower','rating_upper','vote_count','rank']:
            value=row.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError('invalid leaderboard number')
        if not row['rating_lower']<=row['rating']<=row['rating_upper'] or row['vote_count']<0 or row['rank']<1:
            raise ValueError('invalid leaderboard bounds')
    return '\n'.join([FORMAT, 'Source: '+SOURCE_URL, 'License: CC BY 4.0; attribution: Arena',
                      'Leaderboard published: '+published.isoformat(),
                      'Coverage: text / overall; not other arenas. Rank changes are not model releases or retirements.',
                      'Release: '+revision+'; file sha256: '+sha,
                      *[json.dumps({k:v for k,v in r.items() if k!='leaderboard_publish_date'},sort_keys=True,ensure_ascii=False,allow_nan=False)
                        for r in sorted(rows,key=lambda r:(r['rank'],r['model_name']))]])
