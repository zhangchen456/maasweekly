#!/usr/bin/env python3
"""Refresh local official icons. Failed downloads retain the last verified asset.
Run from any directory: python3 site/scripts/refresh-logos.py [--platform NAME]
Only run deliberately when refreshing branding; daily reports use the local registry.
"""
import argparse, concurrent.futures, datetime, hashlib, html, json, pathlib, re, subprocess, xml.etree.ElementTree as ET
ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'src/data/platform-logos.json'
DEST = ROOT / 'public/logos/official'

def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'png'
    if data.startswith(b'\x00\x00\x01\x00'): return 'ico'
    if data.startswith(b'\xff\xd8\xff'): return 'jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return 'webp'
    try:
        tree = ET.fromstring(data)
        if tree.tag.split('}')[-1] != 'svg': return None
        for el in tree.iter():
            if el.tag.split('}')[-1] in ('script', 'foreignObject'): return None
            for key, val in el.attrib.items():
                if key.lower().startswith('on'): return None
                if key.split('}')[-1] == 'href' and not val.startswith('#'): return None
        return 'svg'
    except ET.ParseError: return None

def refresh(row):
    errors = []
    for url in row['candidates']:
        result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--max-time', '25', '--max-filesize', '2097152', '--proto', '=https', '--proto-redir', '=https', '--user-agent', 'Mozilla/5.0', url], capture_output=True)
        payload = result.stdout
        if row.get('svg_marker') and result.returncode == 0:
            page = payload.decode('utf-8', 'replace')
            start = page.find(row['svg_marker'])
            match = re.search(r'<svg\b[\s\S]*?</svg>', page[start:]) if start >= 0 else None
            payload = match[0].encode() if match else b''
        ext = image_extension(payload) if result.returncode == 0 else None
        if not ext:
            errors.append(f'{url}: {result.stderr.decode().strip() or "not a supported image"}')
            continue
        sha = hashlib.sha256(payload).hexdigest()
        filename = f'{row["id"]}-{sha[:12]}.{ext}'
        (DEST / filename).write_bytes(payload)
        row.update(file=f'/logos/official/{filename}', source_url=url, sha256=sha, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), bytes=len(payload))
        row.pop('last_error', None)
        print(f'OK {row["name"]}: {filename}', flush=True)
        return True
    row['last_error'] = errors
    print(f'FAILED {row["name"]}: {errors}', flush=True)
    return False


def write_gallery(rows):
    cards = []
    for row in rows:
        if not row.get('file'): continue
        esc = html.escape
        cards.append(f'<article><img src="{esc(row["file"])}" alt="{esc(row["name"])}"><h2>{esc(row["name"])}</h2><p>{esc(row["id"])}</p><a href="{esc(row["source_url"])}">官方资源 ↗</a></article>')
    dates = sorted({r['checked_at'][:10] for r in rows if r.get('checked_at')})
    markup = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>平台 Logo 资源库</title><style>body{margin:32px;background:#f4f6f2;color:#243024;font:14px/1.6 sans-serif}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}article{background:white;padding:24px;border:1px solid #dce2dc;border-radius:12px}img{width:64px;height:64px;object-fit:contain}h2{font-size:14px}p,a{font-size:12px;color:#52664c}</style><h1>平台 Logo 资源库</h1>'
    markup += f'<p>{len(cards)} 个官方站点 / 产品标识 · 核验日期 {", ".join(dates)} · <a href="/">返回首页</a></p><main>{"".join(cards)}</main></html>'
    (DEST.parent / 'index.html').write_text(markup)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--platform'); args = parser.parse_args()
    rows = json.loads(REGISTRY.read_text())
    chosen = [row for row in rows if not args.platform or args.platform in (row['name'], row['id'], *row['aliases'])]
    if not chosen: parser.error('Unknown platform')
    DEST.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(refresh, chosen))
    temporary = REGISTRY.with_suffix('.tmp'); temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n'); temporary.replace(REGISTRY)
    write_gallery(rows)
    print(f'{sum(results)}/{len(results)} refreshed; failed entries keep existing assets')
    return 0 if all(results) else 1

if __name__ == '__main__': raise SystemExit(main())
