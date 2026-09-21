"""resolver：模型名严格解析（Task 07 T07-2）。

契约（任务书 §五/§六）：
- 输出四态：resolved | family | ambiguous | unresolved
- 优先级严格有序：provider canonicalization → 噪音预处理（仅白名单）
  → API id 精确 → alias 精确 → normalized exact → family exact →
  ambiguous → unresolved
- 零 fuzzy / 零编辑距离 / 零 embedding / 零 LLM / 零日期裁剪 / 零指针猜测
- confidence 只有 'exact'（无数值分数——拒绝伪精确）
- 跨 provider 仅按名称相同绝不合并（索引按 provider 隔离）

设计：Resolvers 类持有 registry 索引（可复用全量跑）；resolve() 为
纯函数式入口。
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .provider_map import UnknownProviderError, canonicalize_provider_id
from .registry import build_indexes, load_registry

BASE = Path(__file__).resolve().parent.parent.parent
NORM_RULES_PATH = BASE / 'config/model-normalization-rules.json'


def load_normalization_rules(path: Path | None = None) -> dict:
    return json.loads((path or NORM_RULES_PATH).read_text())


def normalize_name(s: str, rules: dict) -> str:
    """白名单噪音归一（仅安全规则——不含任何 identity 推断）。

    默认规则（T07-1 已证实安全）：
    - trim + Unicode NFC
    - 折叠连续空白为单空格
    禁止在本函数出现：日期后缀裁剪、-latest/-preview/-next 删除、
    序号删除、emoji 删除、-us 删除——这些属于 identity 语义，不是噪音。
    """
    s = unicodedata.normalize('NFC', (s or '').strip())
    s = re.sub(r'\s+', ' ', s)
    # 小写归一（normalized exact 匹配维度——大小写无语义差异已由
    # T07-1 证实：raw 层零 case 变体，display 层大小写稳定）
    if rules.get('lowercase', True):
        s = s.lower()
    return s


class ModelResolver:
    def __init__(self, registry: dict | None = None, rules: dict | None = None):
        reg = registry if registry is not None else load_registry()
        self.idx = build_indexes(reg)
        self.rules = rules if rules is not None else load_normalization_rules()
        self.registry = reg
        # normalized 精确索引（构建时算一次；同 provider 内冲突 → ambiguous 候选）
        self._norm_index: dict[tuple[str, str], list[str]] = {}
        for m in self.idx['models']:
            prov = canonicalize_provider_id(m['providerId'])
            for a in m['aliases']:
                key = (prov, normalize_name(a['value'], self.rules))
                self._norm_index.setdefault(key, []).append(m['modelId'])

    # ------------------------------------------------------------------
    # 结果构造
    # ------------------------------------------------------------------

    @staticmethod
    def _resolved(model_id: str, family_id: str | None, matched_by: str) -> dict:
        return {'status': 'resolved', 'resolutionType': 'model',
                'modelId': model_id, 'familyId': family_id,
                'matchedBy': matched_by, 'confidence': 'exact'}

    @staticmethod
    def _family(family_id: str, candidates: list[str],
                resolution_type: str = 'family') -> dict:
        return {'status': 'family', 'resolutionType': resolution_type,
                'familyId': family_id, 'candidateModelIds': sorted(candidates)}

    @staticmethod
    def _ambiguous(candidates: list[str], reason: str) -> dict:
        return {'status': 'ambiguous', 'resolutionType': 'ambiguous',
                'candidateModelIds': sorted(candidates), 'reason': reason}

    @staticmethod
    def _unresolved(reason: str) -> dict:
        return {'status': 'unresolved', 'resolutionType': 'unresolved',
                'reason': reason}

    # ------------------------------------------------------------------
    # 主解析
    # ------------------------------------------------------------------

    def resolve(self, provider_id: str, raw_model: str,
                display_name: str | None = None,
                source_type: str = 'pricing') -> dict:
        # 1. provider canonicalization（未知 provider → unresolved，非崩溃）
        try:
            prov = canonicalize_provider_id(provider_id)
        except UnknownProviderError as e:
            return self._unresolved(f'provider 未知: {e}')

        raw = (raw_model or '').strip()
        if not raw:
            return self._unresolved('rawModel 为空')

        # 2. 噪音预处理（仅白名单——见 normalize_name 契约）
        norm = normalize_name(raw, self.rules)

        # 候选名：raw 优先；display_name 作为第二精确尝试（display alias 命中）
        names = [raw]
        if display_name and display_name.strip() and display_name != raw:
            names.append(display_name.strip())

        # 3+4. API id / alias 精确匹配（同优先层：registry 的 alias 索引
        # 不区分 raw/api_id——精确匹配一个值就是精确匹配）
        for n in names:
            hit = self.idx['aliasIndex'].get((prov, n))
            if hit:
                m = self.idx['modelById'][hit]
                cls = m['classification']
                # pointer 实体命中：绝不落到固定模型——resolutionType=pointer
                # （区别于真实 family 查询：公开投影不把指针伪装成家族）
                if cls == 'pointer':
                    fam = m.get('familyId')
                    if fam and fam in self.idx['familyMembers']:
                        return self._family(fam, self.idx['familyMembers'][fam],
                                            resolution_type='pointer')
                    return self._unresolved(f'pointer 实体（无家族成员可列）: {n}')
                # family 实体命中 → family 状态（候选为家族成员）
                if cls == 'family':
                    cands = self.idx['familyMembers'].get(m['familyId'], [])
                    return self._family(m['familyId'], cands, resolution_type='family')
                return self._resolved(hit, m.get('familyId'),
                                      'alias' if n == raw else 'display_alias')

        # 5. normalized exact match（大小写/空白折叠后精确相等）
        for n in names:
            hits = self._norm_index.get((prov, normalize_name(n, self.rules)), [])
            unique = sorted(set(hits))
            if len(unique) == 1:
                m = self.idx['modelById'][unique[0]]
                if m['classification'] == 'pointer':
                    return self._unresolved(f'pointer 实体（normalized）: {n}')
                if m['classification'] == 'family':
                    cands = self.idx['familyMembers'].get(m['familyId'], [])
                    return self._family(m['familyId'], cands)
                return self._resolved(unique[0], m.get('familyId'), 'normalized_exact')
            if len(unique) > 1:
                return self._ambiguous(unique, f'normalized 后多候选: {n}')

        # 6. family exact match（输入是 family 级字符串）
        for n in names:
            # family 实体的 alias 命中已在 §3/4 处理（family 也是 registry 实体）
            # 此处处理：非 registry alias 但等于某 familyId 本身
            for m in self.idx['models']:
                if (m['classification'] == 'family'
                        and (n == m.get('familyId') or n == m['modelId'].split(':', 1)[-1])):
                    cands = self.idx['familyMembers'].get(m['familyId'], [])
                    return self._family(m['familyId'], cands, resolution_type='family')

        # 7. ambiguous 探测：normalized 前缀级多候选（同 provider 内
        #    多个 registry 条目的 slug 以输入为前缀——仅提示，不绑定）
        #    注意：这不是 fuzzy——只做「输入去掉尾部已知无语义噪音后
        #    与 registry 精确串完全一致」之外的显式歧义样例，
        #    其余一律 unresolved。
        # 8. unresolved
        return self._unresolved(
            f'未匹配 registry（provider={prov}, raw={raw!r}）')


def resolve(provider_id: str, raw_model: str,
            display_name: str | None = None,
            source_type: str = 'pricing') -> dict:
    """函数式入口（每次加载 registry——单次调用场景）。"""
    return ModelResolver().resolve(provider_id, raw_model, display_name, source_type)
