#!/usr/bin/env python3
"""把 maas_official_sources.json 拆成单个平台 JSON 文件供 Astro collection 用。"""
import json
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent.parent
SRC_FILE = SITE_DIR.parent / "pipeline" / "config" / "maas_official_sources.json"
DST_DIR = SITE_DIR / "src" / "content" / "platforms"

DST_DIR.mkdir(parents=True, exist_ok=True)

# 清空旧文件
for f in DST_DIR.glob("*.json"):
    f.unlink()

data = json.loads(SRC_FILE.read_text(encoding="utf-8"))

# 写每个平台，用 vendor + 区分词做文件名
seen_vendors = {}
for p in data.get("platforms", []):
    vendor = p.get("vendor", "unknown")
    seen_vendors[vendor] = seen_vendors.get(vendor, 0) + 1
    if seen_vendors[vendor] > 1:
        # 同 vendor 第二个用 name_en 的关键词
        name_en = p.get("name_en", "").lower().replace(" ", "-").replace("/", "-")
        fname = f"{vendor}-{name_en}.json"
    else:
        fname = f"{vendor}.json"
    out = DST_DIR / fname
    out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {fname}")

# 行业数据源不进 platforms collection（是数组，schema 不匹配），
# 站点从 src/data/industry_sources.json 读取
industry = data.get("industry_sources", [])
industry_out = SITE_DIR / "src" / "data" / "industry_sources.json"
industry_out.parent.mkdir(parents=True, exist_ok=True)
if industry:
    industry_out.write_text(json.dumps(industry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  src/data/industry_sources.json ({len(industry)} sources)")

print(f"\nDone: {len(data.get('platforms',[]))} platforms + {len(industry)} industry sources")
