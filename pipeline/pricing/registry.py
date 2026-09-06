"""官方信源 Registry（方案 §9）。

Registry 保存 registry_version、适配器版本、页面语言、区域和 required/optional 状态。
具体 URL 在适配器实现时用 live smoke 再确认；页面迁移不能静默切换到搜索结果或第三方页面。

P0 八家：openai / anthropic / google / deepseek / kimi / glm / doubao / qwen。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRegistryEntry:
    """一条 Registry 记录。source_key 是跨版本的稳定键。"""

    source_key: str          # 如 "openai:pricing"
    provider_id: str         # 如 "openai"
    url: str
    page_language: str       # en / zh
    region: str              # global / cn
    required: bool           # 是否为必填来源
    adapter_version: str     # 适配器版本，结构漂移时升版
    fetcher_version: str     # 抓取器版本：http-1 / playwright-1


# Registry 版本：结构变更时升版，写入 GoalRun 可观测性记录
REGISTRY_VERSION = "2026-08-31.2"

_REGISTRY: list[SourceRegistryEntry] = [
    SourceRegistryEntry(
        source_key="openai:pricing",
        provider_id="openai",
        url="https://developers.openai.com/api/docs/pricing",
        page_language="en",
        region="global",
        required=True,
        adapter_version="openai-1",
        fetcher_version="playwright-1",  # M6：Next.js SPA，http-1 拿到空壳，需渲染
    ),
    SourceRegistryEntry(
        source_key="anthropic:pricing",
        provider_id="anthropic",
        url="https://docs.anthropic.com/en/docs/about-claude/pricing",
        page_language="en",
        region="global",
        required=True,
        adapter_version="anthropic-1",
        fetcher_version="playwright-1",  # M6：JS 渲染价格表，http-1 拿不到
    ),
    SourceRegistryEntry(
        source_key="google:pricing",
        provider_id="google",
        url="https://ai.google.dev/gemini-api/docs/pricing",
        page_language="en",
        region="global",
        required=True,
        adapter_version="google-1",
        fetcher_version="playwright-1",  # M6：SPA 渲染价格表，http-1 拿不到
    ),
    SourceRegistryEntry(
        source_key="deepseek:pricing",
        provider_id="deepseek",
        url="https://api-docs.deepseek.com/quick_start/pricing",
        page_language="zh",
        region="cn",
        required=True,
        adapter_version="deepseek-1",
        fetcher_version="playwright-1",  # M6：静态文档站，但含 rowspan 表格需渲染后解析
    ),
    SourceRegistryEntry(
        source_key="kimi:pricing",
        provider_id="kimi",
        url="https://platform.moonshot.cn/docs/pricing/chat",
        page_language="zh",
        region="cn",
        required=True,
        adapter_version="kimi-1",
        fetcher_version="playwright-1",  # M6：Mintlify 框架，价格在 JS bundle，多子页聚合
    ),
    SourceRegistryEntry(
        source_key="glm:pricing",
        provider_id="glm",
        url="https://open.bigmodel.cn/pricing",  # M6：bigmodel.cn/pricing 返回空壳，换 open 子域
        page_language="zh",
        region="cn",
        required=True,
        adapter_version="glm-1",
        fetcher_version="playwright-1",
    ),
    SourceRegistryEntry(
        source_key="doubao:pricing",
        provider_id="doubao",
        url="https://www.volcengine.com/docs/82379/1544106",
        page_language="zh",
        region="cn",
        required=True,
        adapter_version="doubao-2",
        fetcher_version="playwright-1",  # M6：JS 渲染页，http-1 拿到未渲染内容
    ),
    SourceRegistryEntry(
        source_key="qwen:pricing",
        provider_id="qwen",
        url="https://help.aliyun.com/zh/model-studio/model-pricing",
        page_language="zh",
        region="cn",
        required=True,
        adapter_version="qwen-2",
        fetcher_version="playwright-1",  # M6：SPA 渲染多张价格表，http-1 拿不到
    ),
]


def all_entries() -> list[SourceRegistryEntry]:
    """返回全部 Registry 条目（按 provider_id 排序，稳定顺序）。"""
    return sorted(_REGISTRY, key=lambda e: e.source_key)


def entries_for(providers: list[str]) -> list[SourceRegistryEntry]:
    """按 GoalSpec.target_scope.providers 过滤 Registry。

    用户不能传任意 URL；只从 Registry 展开的 source 中选择（§5.1 GoalSource）。
    """
    wanted = set(providers)
    return [e for e in all_entries() if e.provider_id in wanted]


def by_source_key(source_key: str) -> SourceRegistryEntry | None:
    return next((e for e in _REGISTRY if e.source_key == source_key), None)
