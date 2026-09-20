"""provider_map：provider 双命名体系统一（Task 07 T07-2 前置项）。

T07-1 发现的事实：
  ledger 侧 pricing providerId（qwen/doubao/glm/…）与公开投影
  providerId（alibaba/volcengine/zhipu/…）是两套并存的体系，靠
  pipeline/config/public_providers.json 的 pricingProviderIdToProvider
  连接。240 个模型字符串同时携带两套名——审计「跨 provider」全是假象。

契约：
- registry / resolver 内部只使用 canonical providerId
- ledger 原始值保留（本模块只做读取时转换，不覆盖原始数据）
- 映射集中在唯一模块（此处），不允许各处重复维护
- 未知 provider 不允许静默生成新 canonical id（显式报错）
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
_PROV_CFG = BASE / 'pipeline/config/public_providers.json'

# 已知 canonical providerId 全集（公开投影体系）
# 与 public_providers.json 的 providers[].providerId 一致。
_KNOWN_CANONICAL: frozenset[str] | None = None

# pricing providerId → canonical（源自 public_providers.json，单一事实来源）
_PRICING_TO_CANONICAL: dict[str, str] | None = None


class UnknownProviderError(ValueError):
    """未知 provider——不允许静默生成新 canonical id。"""


def _load() -> None:
    global _KNOWN_CANONICAL, _PRICING_TO_CANONICAL
    if _KNOWN_CANONICAL is not None:
        return
    cfg = json.loads(_PROV_CFG.read_text())
    _KNOWN_CANONICAL = frozenset(p['providerId'] for p in cfg['providers'])
    _PRICING_TO_CANONICAL = dict(cfg['pricingProviderIdToProvider'])


def known_canonical_provider_ids() -> frozenset[str]:
    _load()
    return _KNOWN_CANONICAL  # type: ignore[return-value]


def canonicalize_provider_id(raw_provider_id: str) -> str:
    """raw provider id（两套体系任一）→ canonical providerId。

    - 已是 canonical（公开体系）→ 原样返回
    - 是 ledger pricing 体系（qwen/doubao/glm…）→ 映射
    - 未知 → UnknownProviderError（绝不静默造新 id）
    """
    _load()
    pid = (raw_provider_id or '').strip()
    if not pid:
        raise UnknownProviderError('provider id 为空')
    if pid in _KNOWN_CANONICAL:  # type: ignore[operator]
        return pid
    mapped = _PRICING_TO_CANONICAL.get(pid)  # type: ignore[union-attr]
    if mapped is not None:
        return mapped
    raise UnknownProviderError(
        f'未知 provider id: {raw_provider_id!r}（已知 canonical: '
        f'{sorted(_KNOWN_CANONICAL)}；已知 pricing 别名: '
        f'{sorted(_PRICING_TO_CANONICAL)}）')  # type: ignore[arg-type]


def is_known_provider(raw_provider_id: str) -> bool:
    try:
        canonicalize_provider_id(raw_provider_id)
        return True
    except UnknownProviderError:
        return False
