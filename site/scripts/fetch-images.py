#!/usr/bin/env python3
"""抓取各平台 blog/changelog 文章配图,存成数据源供首页卡片使用。

输出: src/data/article_images.json
结构: [{"platform": "Anthropic", "image": "https://...", "title": "...", "url": "..."}]

能抓到的(SSR)用真实文章图,抓不到的(CSR/反爬)跳过。
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# 代理可选：设置 FETCH_IMAGES_PROXY 环境变量启用（如 http://127.0.0.1:7897），
# 不设置则直连（CI 环境用）。
_proxy = os.environ.get("FETCH_IMAGES_PROXY", "")
PROXY_ENV = {"https_proxy": _proxy, "http_proxy": _proxy, "all_proxy": _proxy} if _proxy else {}

# 平台 blog 列表页 + 文章链接提取规则
PLATFORMS = [
    {
        "platform": "Anthropic",
        "list_url": "https://www.anthropic.com/news",
        "link_pattern": r'href="(/news/[^"]+)"',
        "base": "https://www.anthropic.com",
        "max": 4,
    },
    {
        "platform": "DeepSeek",
        "list_url": "https://api-docs.deepseek.com/zh-cn/news/",
        "link_pattern": r'href="(/zh-cn/news/[^"]+)"',
        "base": "https://api-docs.deepseek.com",
        "max": 3,
    },
    {
        "platform": "Mistral",
        "list_url": "https://mistral.ai/news/",
        "link_pattern": r'href="(/news/[^"]+)"',
        "base": "https://mistral.ai",
        "max": 3,
    },
    {
        "platform": "Google",
        "list_url": "https://blog.google/technology/ai/",
        "link_pattern": r'href="(https://blog\.google/technology/ai/[^"]+)"',
        "base": "",
        "max": 3,
    },
    {
        "platform": "Qwen",
        "list_url": "https://qwenlm.github.io/blog/",
        "link_pattern": r'href="(/blog/[^"]+)"',
        "base": "https://qwenlm.github.io",
        "max": 3,
    },
]

# 平台级 og:image (作为 fallback)
PLATFORM_OG = {
    "DeepSeek": "https://api-docs.deepseek.com/img/deepseek-social-card.jpeg",
    "Anthropic": "https://cdn.sanity.io/images/4zrzovbb/website/54b7ab1d2c2521f83ae5d2da5f9d99321c370d24-2880x1620.png",
    "Google": "https://ai.google.dev/static/site-assets/images/share-ai-dev.png",
    "Mistral": "https://mistral.ai/cms-media/api/media/file/OG-mistral-main_1x.jpg",
}


def fetch(url, timeout=15):
    """带代理的 curl 抓取。"""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
            env={**os.environ, **PROXY_ENV},
        )
        return result.stdout
    except Exception:
        return ""


def extract_og_image(html):
    """从 HTML 提取 og:image。"""
    patterns = [
        r'property="og:image"[^>]*content="([^"]+)"',
        r'content="([^"]+)"[^>]*property="og:image"',
        r'name="og:image"[^>]*content="([^"]+)"',
        r'twitter:image[^>]*content="([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            img = m.group(1).replace("&amp;", "&")
            if img.startswith("http"):
                return img
    return None


def extract_title(html):
    """提取 og:title 或 <title>。"""
    m = re.search(r'property="og:title"[^>]*content="([^"]+)"', html)
    if m:
        return m.group(1)[:80]
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        return m.group(1).strip()[:80]
    return ""


def main():
    results = []

    for plat in PLATFORMS:
        print(f"  抓取 {plat['platform']} 文章列表...")
        html = fetch(plat["list_url"])
        if not html:
            print(f"    [SKIP] 列表页无内容")
            continue

        # 提取文章链接
        links = re.findall(plat["link_pattern"], html)
        seen = set()
        article_links = []
        for link in links:
            url = link if link.startswith("http") else plat["base"] + link
            if url not in seen and "/news/" in url or "/blog/" in url:
                seen.add(url)
                article_links.append(url)
                if len(article_links) >= plat["max"]:
                    break

        print(f"    找到 {len(article_links)} 篇文章")

        for article_url in article_links[: plat["max"]]:
            time.sleep(1)  # 限速
            article_html = fetch(article_url)
            if not article_html:
                continue

            img = extract_og_image(article_html)
            title = extract_title(article_html)

            if img:
                results.append({
                    "platform": plat["platform"],
                    "image": img,
                    "title": title,
                    "url": article_url,
                })
                print(f"    OK: {title[:40]}")
            else:
                print(f"    [无图] {title[:40]}")

    # 补充平台级 fallback 图片
    for platform, img in PLATFORM_OG.items():
        if not any(r["platform"] == platform for r in results):
            results.append({
                "platform": platform,
                "image": img,
                "title": "",
                "url": "",
                "fallback": True,
            })
            print(f"  Fallback: {platform} -> 平台级图")

    # 国产平台 logo/封面 (CSR 抓不到 blog,用公开静态资源)
    CN_LOGOS = {
        "智谱": "https://static.bigmodel.cn/wd-paas-front/static/images/favicon.png",
        "腾讯混元": "https://cloud.tencent.com/static/assets/img/favicon.ico",
        "阿里百炼": "https://img.alicdn.com/imgextra/i1/O1CN01Kzf8wS1oqkUxM4M8L_!!6000000005284-2-tps-200-200.png",
        "Kimi": "https://statics.moonshot.cn/kimi-chat/favicon.ico",
        "MiniMax": "https://www.minimaxi.com/favicon.ico",
        "百度千帆": "https://qianfan.bj.bcebos.com/files-static/icon/favicon.ico",
        "火山方舟": "https://www.volcengine.com/favicon.ico",
        "硅基流动": "https://siliconflow.cn/favicon.ico",
    }
    for platform, img in CN_LOGOS.items():
        if not any(r["platform"] == platform for r in results):
            results.append({
                "platform": platform,
                "image": img,
                "title": "",
                "url": "",
                "fallback": True,
            })
            print(f"  Logo: {platform}")

    out_path = BASE / "src" / "data" / "article_images.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成: {len(results)} 张图片 -> {out_path.name}")


if __name__ == "__main__":
    main()
