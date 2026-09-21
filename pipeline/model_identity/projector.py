"""projector：model identity 公开投影（Task 07 T07-3，唯一入口）。

契约（任务书 §五/§十四）：
- 所有 public projection（prices/changes/items）只能经 project_model_identity
- resolved → modelId + modelName（正式 family 才附 familyId/familyName）
- family（真实家族查询）→ 不写 modelId；正式 family 时写 familyId/familyName
- pointer → 不写 modelId，也不冒充 family（写 pointerId 供观察）
- ambiguous / unresolved → 空对象（omit 字段，不输出 null）
- 「没有 modelId」优于「错误 modelId」——零伪造
"""
from __future__ import annotations

from .registry import build_indexes, load_registry
from .resolver import ModelResolver


class ModelIdentityProjector:
    """持有 resolver 与 registry 索引；提供公开字段投影。"""

    def __init__(self, registry: dict | None = None):
        self.registry = registry if registry is not None else load_registry()
        self.resolver = ModelResolver(registry=self.registry)
        self.idx = build_indexes(self.registry)
        # 正式 family 实体（只有这些 familyId 可公开）
        self._public_families = {
            m['familyId'] for m in self.registry['models']
            if m['classification'] == 'family'}

    def project(self, provider_id: str, raw_model: str,
                display_name: str | None = None) -> dict:
        """返回公开允许的字段（未解析 → {}，字段 omit 不写 null）。"""
        res = self.resolver.resolve(provider_id, raw_model, display_name)

        if res['status'] == 'resolved':
            m = self.idx['modelById'][res['modelId']]
            out = {
                'modelId': res['modelId'],
                'modelName': m['canonicalName'],
            }
            # familyId 仅当引用的是正式 family 实体（public family contract）
            fid = m.get('familyId')
            if fid and fid in self._public_families:
                out['familyId'] = fid
                out['familyName'] = self.idx['modelById'][fid]['canonicalName']
            return out

        if res['status'] == 'family' and res.get('resolutionType') == 'family':
            fid = res['familyId']
            if fid in self._public_families:
                return {
                    'familyId': fid,
                    'familyName': self.idx['modelById'][fid]['canonicalName'],
                }
            return {}

        # pointer / ambiguous / unresolved → 空投影（保留调用方的 modelKey）
        return {}

    # ---- build gate（§十五：exporter 构建时校验）----
    def verify_projection(self, projected: dict) -> list[str]:
        """对已投影字段做最终校验（fail closed 判据）。"""
        errors = []
        mid = projected.get('modelId')
        if mid is not None:
            m = self.idx['modelById'].get(mid)
            if m is None:
                errors.append(f'modelId 不在 registry: {mid}')
            elif m['classification'] != 'model':
                errors.append(
                    f'modelId classification 非 model: {mid} ({m["classification"]})')
            elif projected.get('modelName') != m['canonicalName']:
                errors.append(
                    f'modelName 与 registry 不符: {projected.get("modelName")!r} vs {m["canonicalName"]!r}')
            elif mid.split(':')[0] != m['providerId']:
                errors.append(f'modelId provider 不一致: {mid}')
        fid = projected.get('familyId')
        if fid is not None:
            f = self.idx['modelById'].get(fid)
            if f is None or f['classification'] != 'family':
                errors.append(f'familyId 非正式 family 实体: {fid}')
            elif projected.get('familyName') != f['canonicalName']:
                errors.append(f'familyName 与 registry 不符: {fid}')
        return errors


_default: ModelIdentityProjector | None = None


def get_projector() -> ModelIdentityProjector:
    global _default
    if _default is None:
        _default = ModelIdentityProjector()
    return _default


def project_model_identity(provider_id: str, raw_model: str,
                           display_name: str | None = None) -> dict:
    """公开投影函数式入口（模块级缓存 projector）。"""
    return get_projector().project(provider_id, raw_model, display_name)
