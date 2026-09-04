#!/usr/bin/env python3
"""
MaaS 平台信源每日抓取脚本

工作流程:
1. 读取信源配置 maas_official_sources.json
2. 抓取所有 P0 页面（model_list / pricing / changelog）
3. 提取文本内容
4. 存原始快照到 data/snapshots/YYYY-MM-DD/
5. 与最近一次快照做 diff，提取变化
6. 输出变化清单到 data/diff/YYYY-MM-DD.md + .json

依赖: curl（系统自带）, Python 3.10+
用法: python3 pipeline/scripts/fetch_sources.py [--max-sources N] [--platform 名称]
"""

import json
import os
import sys
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

# 路径配置（以仓库根目录为基准，脚本可从任意位置运行）
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root
SOURCES_FILE = BASE_DIR / "pipeline" / "config" / "maas_official_sources.json"
SNAPSHOT_DIR = BASE_DIR / "data" / "snapshots"
DIFF_DIR = BASE_DIR / "data" / "diff"

# 抓取优先级: P0 必抓
P0_KEYS = ["model_list", "pricing", "changelog"]
# P1 可选抓取（博客也抓，发现产品公告）
P1_KEYS = ["blog"]


def load_sources():
    """加载信源配置"""
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_page(url):
    """
    抓取页面内容。curl 抓取 + HTML 文本提取。
    返回 (content, error)
    """
    # HuggingFace API 用 curl 直接抓 JSON
    if "huggingface.co/api" in url:
        return fetch_via_curl(url)

    content, err = fetch_via_curl(url)
    if content and len(content.strip()) > 100:
        return content, None

    return None, err if err else "内容过短"


def fetch_via_curl(url):
    """用 curl 抓取页面/API，返回文本内容"""
    import subprocess
    import re
    
    # Google ai.google.dev 不带自定义 UA 效果更好
    if "ai.google.dev" in url:
        headers = []
    else:
        headers = ["-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
    
    try:
        cmd = ["curl", "-sL", "--max-time", "30"] + headers + [
             "-H", "Accept: text/html,application/json,*/*",
             url]
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=35
        )
        content = result.stdout.strip()
        if not content or len(content) < 10:
            return None, f"curl 返回空 (stderr: {result.stderr[:200]})"
        
        # JSON API 响应
        if url.endswith("/api/models") or "/api/" in url:
            try:
                data = json.loads(content)
                content = json.dumps(data, ensure_ascii=False, indent=2)
                return content, None
            except json.JSONDecodeError:
                pass  # 非 JSON，继续处理为 HTML
        
        # HTML 页面：做简单文本提取
        content = extract_text_from_html(content)
        
        if not content or len(content.strip()) < 50:
            return None, f"提取后内容过短 (raw_len={len(result.stdout)})"
        
        return content, None
    except subprocess.TimeoutExpired:
        return None, "curl 超时 (30s)"
    except Exception as e:
        return None, f"curl 失败: {e}"


def extract_text_from_html(html):
    """从 HTML 中提取可读文本（轻量级，不依赖外部库）"""
    import re
    
    # 移除 script/style 标签及内容
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    # 移除 HTML 注释
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    
    # 将表格单元格转换为文本（保留定价表数据）
    html = re.sub(r'<t[dh][^>]*>', ' | ', html, flags=re.IGNORECASE)
    html = re.sub(r'</t[dh]>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<tr[^>]*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</tr>', '', html, flags=re.IGNORECASE)
    
    # 将 <br> <p> <div> 等转为换行
    html = re.sub(r'<(?:br|p|div|h[1-6]|li|ul|ol|section|article)[^>]*>', '\n', html, flags=re.IGNORECASE)
    
    # 移除所有其他 HTML 标签
    text = re.sub(r'<[^>]+>', '', html)
    
    # HTML 实体解码
    import html as html_module
    text = html_module.unescape(text)
    
    # 清理多余空白
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line:
            # 合并多个空格
            line = re.sub(r' {2,}', ' ', line)
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def content_hash(content):
    """计算内容 hash，用于去重和变化检测"""
    # 去除首尾空白后 hash
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()[:16]


def save_snapshot(platform_name, source_type, content, today):
    """保存单页快照"""
    # 文件名: 平台名_信源类型_日期.md
    safe_name = platform_name.replace("/", "-").replace(" ", "_")
    filename = f"{safe_name}__{source_type}__{today}.md"
    filepath = SNAPSHOT_DIR / today / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"<!-- url: see sources config -->\n<!-- fetched: {datetime.now().isoformat()} -->\n\n")
        f.write(content)
    return filepath


def find_yesterday_snapshot(platform_name, source_type, today_str):
    """查找昨天的同源快照文件"""
    yesterday = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    safe_name = platform_name.replace("/", "-").replace(" ", "_")
    # 也检查前2天（防止隔天漏抓）
    for days_back in [1, 2, 3]:
        check_date = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=days_back)).strftime("%Y-%m-%d")
        filename = f"{safe_name}__{source_type}__{check_date}.md"
        filepath = SNAPSHOT_DIR / check_date / filename
        if filepath.exists():
            return filepath
    return None


def simple_diff(old_content, new_content, platform_name, source_type):
    """
    简单 diff: 按行对比，提取新增和删除的行
    返回 dict: {added: [...], removed: [...], changed: bool}
    """
    old_lines = set(l.strip() for l in old_content.split("\n") if l.strip() and not l.startswith("<!--"))
    new_lines = set(l.strip() for l in new_content.split("\n") if l.strip() and not l.startswith("<!--"))
    
    added = new_lines - old_lines
    removed = old_lines - new_lines
    
    # 过滤掉纯标点/空行
    added = [l for l in added if len(l) > 10]
    removed = [l for l in removed if len(l) > 10]
    
    return {
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": len(added) > 0 or len(removed) > 0
    }


def main():
    # 命令行参数: --max-sources N（调试限流）、--platform 名称（只跑单个平台）
    max_sources = None
    only_platform = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--max-sources" and i + 1 < len(args):
            max_sources = int(args[i + 1])
            i += 2
        elif args[i] == "--platform" and i + 1 < len(args):
            only_platform = args[i + 1]
            i += 2
        else:
            i += 1

    today = date.today().strftime("%Y-%m-%d")
    print(f"=== MaaS 信源每日抓取 {today} ===")

    config = load_sources()
    platforms = config.get("platforms", [])
    industry_sources = config.get("industry_sources", [])
    if only_platform:
        platforms = [p for p in platforms if only_platform in p["name"]]
    
    # 抓取统计
    stats = {"total": 0, "success": 0, "failed": 0, "changed": 0, "unchanged": 0}
    changes_summary = []  # 所有平台变化汇总
    
    # --- 抓取平台信源 ---
    for platform in platforms:
        name = platform["name"]
        sources = platform.get("sources", {})
        print(f"\n--- {name} ---")
        
        all_source_types = P0_KEYS + P1_KEYS
        for source_type in all_source_types:
            if max_sources is not None and stats["total"] >= max_sources:
                break
            url = sources.get(source_type)
            if not url:
                continue
            
            stats["total"] += 1
            print(f"  [{source_type}] {url[:80]}...")
            
            content, err = fetch_page(url)
            if err:
                print(f"    ✗ 失败: {err}")
                stats["failed"] += 1
                changes_summary.append({
                    "platform": name,
                    "source_type": source_type,
                    "url": url,
                    "status": "fetch_failed",
                    "error": err
                })
                continue
            
            stats["success"] += 1
            
            # 保存快照
            snapshot_path = save_snapshot(name, source_type, content, today)
            print(f"    ✓ 保存: {snapshot_path.name} ({len(content)} chars)")
            
            # 与昨天对比
            yesterday_path = find_yesterday_snapshot(name, source_type, today)
            if yesterday_path:
                old_content = yesterday_path.read_text(encoding="utf-8")
                diff = simple_diff(old_content, content, name, source_type)
                
                if diff["changed"]:
                    stats["changed"] += 1
                    added_count = len(diff["added"])
                    removed_count = len(diff["removed"])
                    print(f"    ⚡ 有变化: +{added_count} 行, -{removed_count} 行")
                    changes_summary.append({
                        "platform": name,
                        "source_type": source_type,
                        "url": url,
                        "status": "changed",
                        "added_count": added_count,
                        "removed_count": removed_count,
                        "added_lines": diff["added"][:30],  # 限制数量
                        "removed_lines": diff["removed"][:10]
                    })
                else:
                    stats["unchanged"] += 1
                    print(f"    = 无变化")
                    changes_summary.append({
                        "platform": name,
                        "source_type": source_type,
                        "url": url,
                        "status": "unchanged"
                    })
            else:
                # 首次抓取，无历史对比
                print(f"    ○ 首次抓取，无历史对比")
                stats["changed"] += 1
                changes_summary.append({
                    "platform": name,
                    "source_type": source_type,
                    "url": url,
                    "status": "first_fetch",
                    "content_length": len(content)
                })
    
    # --- 抓取行业数据源 ---
    print(f"\n--- 行业数据源 ---")
    for src in industry_sources:
        if max_sources is not None and stats["total"] >= max_sources:
            print(f"  [调试] 达到 --max-sources {max_sources}，停止抓取")
            break
        name = src["name"]
        url = src.get("api_url") or src.get("url")
        if not url:
            continue
        stats["total"] += 1
        print(f"  [{name}] {url[:80]}...")
        content, err = fetch_page(url)
        if err:
            print(f"    ✗ 失败: {err}")
            stats["failed"] += 1
            changes_summary.append({
                "platform": name,
                "source_type": "industry",
                "url": url,
                "status": "fetch_failed",
                "error": err
            })
            continue
        stats["success"] += 1
        snapshot_path = save_snapshot(name, "industry", content, today)
        print(f"    ✓ 保存: {snapshot_path.name} ({len(content)} chars)")
        
        yesterday_path = find_yesterday_snapshot(name, "industry", today)
        if yesterday_path:
            old_content = yesterday_path.read_text(encoding="utf-8")
            diff = simple_diff(old_content, content, name, "industry")
            if diff["changed"]:
                stats["changed"] += 1
                print(f"    ⚡ 有变化: +{len(diff['added'])} 行")
                changes_summary.append({
                    "platform": name,
                    "source_type": "industry",
                    "url": url,
                    "status": "changed",
                    "added_count": len(diff["added"]),
                    "removed_count": len(diff["removed"]),
                    "added_lines": diff["added"][:30],
                    "removed_lines": diff["removed"][:10]
                })
            else:
                stats["unchanged"] += 1
                print(f"    = 无变化")
                changes_summary.append({
                    "platform": name,
                    "source_type": "industry",
                    "url": url,
                    "status": "unchanged"
                })
        else:
            stats["changed"] += 1
            changes_summary.append({
                "platform": name,
                "source_type": "industry",
                "url": url,
                "status": "first_fetch",
                "content_length": len(content)
            })
    
    # --- 生成 diff 报告 ---
    DIFF_DIR.mkdir(parents=True, exist_ok=True)
    diff_report_path = DIFF_DIR / f"{today}.md"
    
    # 只记录有变化的
    changed_items = [c for c in changes_summary if c["status"] in ("changed", "first_fetch", "fetch_failed")]
    
    with open(diff_report_path, "w", encoding="utf-8") as f:
        f.write(f"# MaaS 信源变化报告 - {today}\n\n")
        f.write(f"**抓取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC+8\n")
        f.write(f"**抓取统计**: 总计 {stats['total']} 个信源 | 成功 {stats['success']} | 失败 {stats['failed']} | 有变化 {stats['changed']} | 无变化 {stats['unchanged']}\n\n")
        f.write("---\n\n")
        
        if not changed_items:
            f.write("## 今日无变化\n\n所有信源与最近一次快照对比，未检测到变化。\n")
        else:
            # 按平台分组
            by_platform = {}
            for item in changed_items:
                p = item["platform"]
                by_platform.setdefault(p, []).append(item)
            
            for platform in by_platform:
                items = by_platform[platform]
                f.write(f"## {platform}\n\n")
                for item in items:
                    st = item["source_type"]
                    url = item["url"]
                    status = item["status"]
                    
                    if status == "fetch_failed":
                        f.write(f"### {st} - ❌ 抓取失败\n")
                        f.write(f"- URL: {url}\n")
                        f.write(f"- 错误: {item.get('error', 'unknown')}\n\n")
                    elif status == "first_fetch":
                        f.write(f"### {st} - 🆕 首次抓取\n")
                        f.write(f"- URL: {url}\n")
                        f.write(f"- 内容长度: {item.get('content_length', 0)} chars\n\n")
                    elif status == "changed":
                        added = item.get("added_lines", [])
                        removed = item.get("removed_lines", [])
                        f.write(f"### {st} - ⚡ 有变化\n")
                        f.write(f"- URL: {url}\n")
                        f.write(f"- 新增 {item['added_count']} 行, 删除 {item['removed_count']} 行\n\n")
                        if added:
                            f.write("**新增内容:**\n")
                            for line in added[:15]:
                                f.write(f"- {line[:200]}\n")
                            if len(added) > 15:
                                f.write(f"- ... 还有 {len(added) - 15} 行\n")
                            f.write("\n")
                        if removed:
                            f.write("**删除内容:**\n")
                            for line in removed[:5]:
                                f.write(f"- {line[:200]}\n")
                            f.write("\n")
                f.write("---\n\n")
        
        # 保存完整 JSON 供 LLM 消费
        json_path = DIFF_DIR / f"{today}.json"
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump({
                "date": today,
                "fetched_at": datetime.now().isoformat(),
                "stats": stats,
                "changes": changes_summary
            }, jf, ensure_ascii=False, indent=2)
        
        f.write(f"## 机器可读数据\n\n完整 JSON 数据见: `{json_path}`\n")
    
    print(f"\n=== 完成 ===")
    print(f"统计: {stats}")
    print(f"Diff 报告: {diff_report_path}")
    print(f"JSON 数据: {DIFF_DIR / f'{today}.json'}")
    
    return stats


if __name__ == "__main__":
    main()
