#!/usr/bin/env python3
"""Import formal drafts and structured projections as one committed input generation."""
import importlib.util
import re
import sys
from pathlib import Path
SITE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE_DIR.parent / 'pipeline'))
from data_store import EDITORIAL
SRC_DIR = SITE_DIR.parent / 'data/weekly'
DST_DIR = SITE_DIR.parent / EDITORIAL


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for md_file in sorted(SRC_DIR.glob('*.md')):
        text = md_file.read_text(encoding='utf-8')
        title_match = re.match(r'^#\s+(.+)$', text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md_file.stem
        date_str = md_file.stem
        period_match = re.search(r'追踪周期.*?(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})', text)
        period = f'{period_match.group(1)} ~ {period_match.group(2)}' if period_match else ''
        body = re.sub(r'^#\s+.+\n', '', text, count=1)
        frontmatter = f'---\ntitle: "{title}"\ndate: "{date_str}"\nperiod: "{period}"\n---\n\n'
        (DST_DIR / md_file.name).write_text(frontmatter + body, encoding='utf-8'); count += 1
    spec = importlib.util.spec_from_file_location('weekly_structured', Path(__file__).with_name('extract-structured.py'))
    extractor = importlib.util.module_from_spec(spec); spec.loader.exec_module(extractor)
    extractor.configure_root(SITE_DIR.parent); extractor.main()
    print(f'Done: {count} formal reports imported with structured projections')


def configure_root(root):
    global SITE_DIR, SRC_DIR, DST_DIR
    SITE_DIR = root / 'site'; SRC_DIR = root / 'data/weekly'; DST_DIR = root / EDITORIAL


if __name__ == '__main__':
    from run_protocol import managed_entry
    sys.exit(managed_entry(main, SITE_DIR.parent, 'weekly-import', configure_root))
