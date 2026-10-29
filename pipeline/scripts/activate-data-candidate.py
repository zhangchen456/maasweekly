#!/usr/bin/env python3
"""Activate a verified external data cache. Does not change code or restart services."""
import argparse,json,os,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BASE/'pipeline'))
from data_publication import activate,no_links

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate-dir',type=Path,required=True)
    p.add_argument('--public-root',type=Path,required=True)
    p.add_argument('--expected-publication-sha256',required=True,help='current pointer SHA-256, or empty for initial activation')
    p.add_argument('--allow-rollback',action='store_true')
    a=p.parse_args()
    for path in [a.candidate_dir,a.public_root]:
        if no_links(path).is_relative_to(BASE):p.error('data directories must be outside the code checkout')
    import psycopg2
    with psycopg2.connect(os.environ['MAAS_DATA_DSN']) as connection:
        print(json.dumps(activate(connection,a.candidate_dir,a.public_root,a.expected_publication_sha256,allow_rollback=a.allow_rollback)))
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('data activation failed: '+type(e).__name__,file=sys.stderr);sys.exit(2)
