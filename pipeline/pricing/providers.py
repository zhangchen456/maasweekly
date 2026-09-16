"""Playwright 渲染抓取 provider（迁移自追浪 app-core-service-001 goals/providers.py）。

改造点：
- 去 SSRF/url_guard（maasweekly 是自用抓取脚本，URL 来自仓库内 registry，非用户输入）
- 去 blobstore（ContentSnapshot 直接携带 content 字符串）
- 去 DirectSourceProvider（httpx 通道）——8 家定价页全部需要渲染，只保留 Playwright
- 保留 wait_until 策略 / 水合等待 / Kimi 多子页聚合（源项目 M6 的踩坑结论）

页面等待策略（源项目踩坑结论，勿改）：
- domcontentloaded：deepseek/qwen 文档站，DOM 就绪即取（networkidle 会超时）
- networkidle：SPA 页，等网络空闲确保水合完成
"""
from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urljoin

from .base import ContentSnapshot, SourceSpec

_FETCHER_VERSION_PLAYWRIGHT = "playwright-1"
_MAX_BYTES = 5 * 1024 * 1024  # 5MB 上限
_PLAYWRIGHT_WAIT_STRATEGY: dict[str, str] = {
    "deepseek:pricing": "domcontentloaded",
    "qwen:pricing": "domcontentloaded",
}
_PLAYWRIGHT_HYDRATE_MS = 3000   # goto 后额外等水合
_PLAYWRIGHT_GOTO_TIMEOUT = 35_000  # ms

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class PlaywrightSourceProvider:
    """Playwright 渲染官方价格页 → ContentSnapshot（content 直接携带 HTML）。"""

    fetcher_version = _FETCHER_VERSION_PLAYWRIGHT
    _browser = None   # 类级单例，进程内复用
    _playwright = None

    async def _ensure_browser(self):
        if PlaywrightSourceProvider._browser is not None:
            return PlaywrightSourceProvider._browser
        from playwright.async_api import async_playwright

        PlaywrightSourceProvider._playwright = await async_playwright().start()
        PlaywrightSourceProvider._browser = (
            await PlaywrightSourceProvider._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        )
        return PlaywrightSourceProvider._browser

    def _assemble(self, source: SourceSpec, content: str, fetched_at: float) -> ContentSnapshot:
        raw = content.encode("utf-8")[:_MAX_BYTES]
        sha = hashlib.sha256(raw).hexdigest()
        return ContentSnapshot(
            snapshot_id=f"snap-{sha[:24]}",
            source_key=source.source_key,
            url=source.url,
            fetched_at=fetched_at,
            http_status=200,
            content_type="text/html; charset=utf-8",
            sha256=sha,
            content=raw.decode("utf-8", errors="replace"),
            fetcher_version=self.fetcher_version,
        )

    async def fetch(self, source: SourceSpec) -> ContentSnapshot:
        html = await self._render_url(source.url, source.source_key)
        return self._assemble(source, html, time.time())

    async def _render_url(self, url: str, source_key: str) -> str:
        """渲染单个 URL，返回页面 HTML。Kimi 多子页复用。"""
        browser = await self._ensure_browser()
        context = await browser.new_context(user_agent=_UA, service_workers="block")
        page = await context.new_page()
        try:
            wait_until = _PLAYWRIGHT_WAIT_STRATEGY.get(source_key, "networkidle")
            await page.goto(url, wait_until=wait_until, timeout=_PLAYWRIGHT_GOTO_TIMEOUT)
            await page.wait_for_timeout(_PLAYWRIGHT_HYDRATE_MS)
            return await page.content()
        finally:
            await context.close()

    @classmethod
    async def shutdown(cls) -> None:
        if cls._browser is not None:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright is not None:
            await cls._playwright.stop()
            cls._playwright = None


class KimiPlaywrightProvider(PlaywrightSourceProvider):
    """Kimi 价格页抓取。

    2026-09 迁移：官网从 platform.moonshot.cn 迁到 platform.kimi.com，
    文档结构改版——旧版按模型拆子页（/docs/pricing/chat-k3、chat-k27-code…），
    主页只含导航；新版全部模型集中在 chat 单页（渲染后的 doc-table +
    JS bundle 里各存一份 rows:[[），batch/hosted-agents/websearch 为
    独立功能页（按 billing_mode 区分，不在 realtime chat 采集范围）。

    保留多子页聚合骨架：子页匹配跟随站内实际存在的 /docs/pricing/* 链接，
    结构再变（模型拆分页回归）时自动收集，extractor 只认 chat 模型行。
    """

    _SUBPAGE_PATTERN = r'href="(/docs/pricing/[^"]*)"'

    async def fetch(self, source: SourceSpec) -> ContentSnapshot:
        # 1. 渲染主页，提取子页链接
        index_html = await self._render_url(source.url, source.source_key)
        subpaths = list(dict.fromkeys(re.findall(self._SUBPAGE_PATTERN, index_html)))
        # 排除：chat 本身、.md 源码、非模型功能页（batch/tools/limits/
        # hosted-agents/websearch——按 billing_mode 计费，与 realtime chat
        # 事实分离；全角（Batch）模型名会生成错误 model_key）
        subpaths = [
            s for s in subpaths
            if s != "/docs/pricing/chat" and not s.endswith(".md")
            and "batch" not in s and "tools" not in s and "limits" not in s
            and "hosted-agents" not in s and "websearch" not in s
        ]
        print(f"  kimi 子页 {len(subpaths)} 个: {subpaths}")

        # 2. 新结构：主页已含全部模型数据——主页本身就是第一个片段；
        #    子页（若有）逐个渲染，收集含 rows 的片段
        fragments: list[str] = [index_html]
        for sp in subpaths:
            sub_url = urljoin(source.url + "/", sp)
            try:
                sub_html = await self._render_url(sub_url, source.source_key)
                fragments.append(sub_html)
            except Exception as e:  # noqa: BLE001
                print(f"  kimi 子页 {sub_url} 渲染失败: {e}")

        # 3. 拼接成一个 HTML snapshot（整页拼接，extractor 从中提取
        #    rows:[[ 块；非模型行由 extractor 的 kimi/moonshot 过滤排除）
        combined = "<html><body>" + "\n".join(fragments) + "</body></html>"
        snap = self._assemble(source, combined, time.time())
        # 空内容防护：站点再迁移时 rows 完全消失 → 抓取失败（沿用旧数据），
        # 而不是产出空快照污染归档
        if "rows:[[" not in combined:
            raise RuntimeError(
                "kimi 页面无 rows:[[ 数据，疑似站点结构再迁移，需人工检查")
        return snap


def provider_for(source_key: str) -> PlaywrightSourceProvider:
    """按 source_key 选 provider。Kimi 用多子页聚合，其余通用渲染。"""
    if source_key.startswith("kimi:"):
        return KimiPlaywrightProvider()
    return PlaywrightSourceProvider()
