#!/usr/bin/env python3
"""把 data/weekly 的周报 Markdown 拷贝到 Astro content collection，并添加 frontmatter。"""
import os
import re
import shutil
from pathlib import Path

# 以仓库结构为基准，脚本可从任意位置运行
SITE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = SITE_DIR.parent / "data" / "weekly"
DST_DIR = SITE_DIR / "src" / "content" / "weekly"

DST_DIR.mkdir(parents=True, exist_ok=True)

count = 0
for md_file in sorted(SRC_DIR.glob("*.md")):
    text = md_file.read_text(encoding="utf-8")
    
    # 提取标题（第一行 # ...）
    title_match = re.match(r'^#\s+(.+)$', text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_file.stem
    
    # 从文件名提取日期 (2026-09-01.md -> 2026-09-01)
    date_str = md_file.stem  # e.g. "2026-09-01"
    
    # 尝试从内容提取追踪周期
    period_match = re.search(r'追踪周期.*?(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})', text)
    period = f"{period_match.group(1)} ~ {period_match.group(2)}" if period_match else ""
    
    # 去掉原有的第一行标题（Astro 会用 frontmatter title 渲染）
    body = re.sub(r'^#\s+.+\n', '', text, count=1)
    
    # 构建 frontmatter
    frontmatter = f"""---
title: "{title}"
date: "{date_str}"
period: "{period}"
---

"""
    
    out_path = DST_DIR / md_file.name
    out_path.write_text(frontmatter + body, encoding="utf-8")
    count += 1
    print(f"  {md_file.name} -> OK")

print(f"\nDone: {count} reports copied to {DST_DIR}")
