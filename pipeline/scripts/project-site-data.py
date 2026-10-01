#!/usr/bin/env python3
"""Rebuild legacy site outputs from standard authoritative inputs and immutable facts."""
import argparse
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'pipeline'))
from data_store import project_site
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--input-root', type=Path, default=BASE)
    args = parser.parse_args(); project_site(args.input_root.resolve()); print('site compatibility projection complete')
