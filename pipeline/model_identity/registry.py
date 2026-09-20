"""registry：Model Registry 加载与索引（Task 07 T07-2）。

数据：data/model-registry/models.json（人工可读/稳定排序/可 code review）。

schema（v1.0）：
  modelId        <canonicalProviderId>:<canonicalSlug>（永久身份）
  providerId     canonical 体系（必须已经 provider_map 校验）
  canonicalName  人类可读名（改名不改 modelId）
  familyId       家族 id（family 改名不改既有 modelId）
  classification model | family | pointer | non_model
  aliases[]      {value, type, source}
                 type ∈ raw | display | snapshot | cross_generation | api_id | platform_sku
  notes          人工备注

契约：
- ambiguous / unresolved 是 resolver 结果状态，不进 registry
- alias 增删 / canonicalName 改名 / familyId 改名都不改变 modelId
- modelId 一旦公开不得复用给另一模型
"""
from __future__ import annotations

import json
from pathlib import Path

from .provider_map import canonicalize_provider_id

BASE = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = BASE / 'data/model-registry/models.json'

ALIAS_TYPES = ('raw', 'display', 'snapshot', 'cross_generation', 'api_id', 'platform_sku')
CLASSIFICATIONS = ('model', 'family', 'pointer', 'non_model')


class RegistryError(ValueError):
    """registry 结构违规（validator 亦复用同一判据）。"""


def load_registry(path: Path | None = None) -> dict:
    return json.loads((path or REGISTRY_PATH).read_text())


def build_indexes(registry: dict) -> dict:
    """构建解析索引：alias → modelId（同 provider 唯一性在此校验）。

    索引键：(canonicalProviderId, aliasValue)——跨 provider 同名
    天然隔离（T07-1 已证零跨 provider 同名，但规则仍按 provider 隔离）。
    """
    models = registry['models']
    alias_index: dict[tuple[str, str], str] = {}
    model_by_id: dict[str, dict] = {}
    for m in models:
        mid = m['modelId']
        if mid in model_by_id:
            raise RegistryError(f'modelId 重复: {mid}')
        model_by_id[mid] = m
        # providerId 必须已是 canonical（load 时校验过；此处防御）
        prov = canonicalize_provider_id(m['providerId'])
        for a in m['aliases']:
            key = (prov, a['value'])
            if key in alias_index and alias_index[key] != mid:
                raise RegistryError(
                    f'alias 冲突: ({prov}, {a["value"]}) 同时映射 '
                    f'{alias_index[key]} 与 {mid}')
            alias_index[key] = mid
    family_index: dict[str, list[str]] = {}
    for m in models:
        if m['classification'] == 'family':
            continue
        fid = m.get('familyId')
        if fid:
            family_index.setdefault(fid, []).append(m['modelId'])
    return {
        'models': models,
        'modelById': model_by_id,
        'aliasIndex': alias_index,
        'familyMembers': family_index,
        'familyEntities': {m['familyId']: m['modelId'] for m in models
                           if m['classification'] == 'family'},
    }
