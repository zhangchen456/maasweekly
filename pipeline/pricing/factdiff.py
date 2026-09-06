"""价格事实差异计算（方案 §8.2 FactDiff）。

对比本轮提取的 PriceFact 与上一轮 artifact 的当前事实集，按 fact_key 分组：
- 新增（new）：上一轮没有的 fact_key
- 变更（changed）：fact_key 存在但 material 字段不同
- 不变（unchanged）：fact_key 存在且 material 字段全一致
- 缺失（missing）：上一轮有、本轮没有（§7 决策补丁：缺行判 partial）

missing 判定带身份漂移豁免：fact_key 由 stable_identity（含 context_band/region 等）
哈希而来，extractor 升版修正阶梯/区域归属后，同一 (provider, model, component,
region) 的数据会换 fact_key——这不是数据缩水，不计入 missing。只有当同业务身份
的条目在本轮完全不存在时才判 missing（真正可能保留旧报价的场景）。

material_change_fields 来自 GoalSpec.update_policy。只有 material 字段变化
才算「实质变化」，非 material 字段（如 observed_at）变化不产生新版本。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import MATERIAL_FIELDS


@dataclass
class FactDiff:
    """单条事实的差异结论。"""

    fact_key: str
    status: str  # new / changed / unchanged / missing
    new_fact: dict | None = None        # 本轮事实（missing 时为 None）
    previous_fact: dict | None = None    # 上一轮事实（new 时为 None）
    changed_fields: list[str] = field(default_factory=list)
    # missing 判为身份漂移（同业务身份本轮仍有数据，key 因 stable_identity 组成变化而换）
    identity_migrated: bool = False


def _business_identity(fact: dict) -> tuple[str, str, str, str]:
    """业务身份：fact_key 之外的稳定定位（provider + model + component + region）。

    fact_key 含 context_band 等阶梯维度，extractor 修正阶梯/区域归属后同一条
    数据会换 key；业务身份不含这些易漂移维度，用于区分「数据消失」与「换身份证」。
    """
    return (
        str(fact.get("provider_id", "")),
        str(fact.get("model_key", "")),
        str(fact.get("component", "")),
        str(fact.get("region", "")),
    )


@dataclass
class DiffResult:
    """整个 GoalRun 的差异汇总。"""

    new: list[FactDiff] = field(default_factory=list)
    changed: list[FactDiff] = field(default_factory=list)
    unchanged: list[FactDiff] = field(default_factory=list)
    missing: list[FactDiff] = field(default_factory=list)

    @property
    def has_material_change(self) -> bool:
        """是否有实质变化（决定 run 终态 updated vs no_change）。"""
        return bool(self.new or self.changed)

    @property
    def fact_keys_this_round(self) -> list[str]:
        """本轮所有 fact_key（用于 artifact_version.fact_keys）。"""
        return [d.fact_key for d in [*self.new, *self.changed, *self.unchanged]]


def diff_facts(
    current_facts: list[dict],
    previous_facts: list[dict],
) -> DiffResult:
    """对比本轮与上一轮事实集。

    current_facts / previous_facts 元素是 price_fact_version 行（dict）。
    """
    prev_by_key = {f["fact_key"]: f for f in previous_facts}
    curr_by_key = {f["fact_key"]: f for f in current_facts}

    result = DiffResult()

    # 本轮有的
    for fk, curr in curr_by_key.items():
        prev = prev_by_key.get(fk)
        if prev is None:
            result.new.append(FactDiff(fact_key=fk, status="new", new_fact=curr))
            continue
        changed_fields = _material_diff(prev, curr)
        if changed_fields:
            result.changed.append(
                FactDiff(fact_key=fk, status="changed", new_fact=curr, previous_fact=prev, changed_fields=changed_fields)
            )
        else:
            result.unchanged.append(
                FactDiff(fact_key=fk, status="unchanged", new_fact=curr, previous_fact=prev)
            )

    # 上一轮有、本轮没有的。先收集本轮业务身份集合，区分真实缩水与身份漂移：
    # 同 (provider, model, component, region) 本轮仍有条目 → key 换了但数据还在，
    # 标 identity_migrated 不计 missing（extractor 升版的正常迁移，非数据丢失）。
    curr_identities = {_business_identity(f) for f in current_facts}
    for fk, prev in prev_by_key.items():
        if fk in curr_by_key:
            continue
        migrated = _business_identity(prev) in curr_identities
        result.missing.append(
            FactDiff(
                fact_key=fk,
                status="missing",
                previous_fact=prev,
                identity_migrated=migrated,
            )
        )

    return result


def _material_diff(prev: dict, curr: dict) -> list[str]:
    """比较 material 字段，返回变化的字段名列表。

    context_band / time_condition 是 JSON 字符串，按规范化字符串比较。
    """
    changed: list[str] = []
    for f in MATERIAL_FIELDS:
        pv = _normalize_field(prev.get(f))
        cv = _normalize_field(curr.get(f))
        if pv != cv:
            changed.append(f)
    return changed


def _normalize_field(value) -> str:
    """把字段值归一为可比较字符串。

    - None → ""
    - dict → sort_keys JSON（本轮事实的 context_band/time_condition 是 dict）
    - str → 若是 JSON 字符串则 loads 后 sort_keys 重新序列化（DB 读出的是 JSON 文本），
            否则去空白后原样返回
    - 其他 → str()
    保证 dict 和其等价 JSON 字符串归一结果一致，跨轮次可比。
    """
    import json

    if value is None:
        return ""
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return json.dumps(json.loads(s), sort_keys=True, separators=(",", ":"))
            except (json.JSONDecodeError, ValueError):
                return s
        return s
    return str(value)
