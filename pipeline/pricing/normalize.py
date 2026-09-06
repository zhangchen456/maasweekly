"""价格归一与门禁校验（方案 §8.2 Normalizer + Validator）。

Extractor 产出的 PriceFact 是「候选」，必须过 Normalizer → Validator 两道门禁
才能进入 FactDiff / ArtifactPublisher。门禁失败的事实被拒收，记入 warnings。

P0 门禁（§14 M2 验收）：
- NG-01 证据回链完整：每个 fact.evidence_id 必须能在 result.evidence 中找到。
- NG-02 金额为 Decimal 字符串：拒绝 float、拒绝非数字。
- NG-03 稳定身份恒等：fact_key 必须等于 sha256(stable_identity(八元组))。
- NG-04 必填字段非空：provider/model/component/currency/region/service_tier。
- NG-05 上下文阶梯单调：max > min（若 max 非 None）。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .base import ExtractionResult, PriceFact

# material_change_fields（与 GoalSpec.update_policy 默认值一致）
MATERIAL_FIELDS = ("amount", "currency", "unit_quantity", "region", "context_band", "time_condition", "effective_at")


class ValidationReport:
    """归一校验报告。"""

    def __init__(self) -> None:
        self.accepted: list[PriceFact] = []
        self.rejected: list[tuple[PriceFact, str]] = []  # (fact, reason)
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.rejected


def normalize_and_validate(result: ExtractionResult) -> ValidationReport:
    """对候选事实跑 NG-01～NG-05 门禁。"""
    report = ValidationReport()
    ev_ids = {e.evidence_id for e in result.evidence}

    for fact in result.price_facts:
        reason = _check(fact, ev_ids)
        if reason:
            report.rejected.append((fact, reason))
        else:
            report.accepted.append(fact)

    if report.rejected:
        report.warnings.append(
            f"{len(report.rejected)} 个价格事实未通过门禁被拒收"
        )
    return report


def _check(fact: PriceFact, ev_ids: set[str]) -> str | None:
    """返回拒绝原因，None 表示通过。"""
    # NG-04 必填字段非空
    for field in ("provider_id", "model_key", "component", "currency", "region", "service_tier"):
        if not getattr(fact, field, None):
            return f"empty_required_field:{field}"

    # NG-01 证据回链
    if fact.evidence_id not in ev_ids:
        return "evidence_not_found"

    # NG-02 金额为 Decimal 字符串：拒绝 float、拒绝非数字、拒绝指数格式（避免 float 混入）
    if any(c in fact.amount for c in ("e", "E")):
        return f"non_decimal_amount:{fact.amount!r}"
    try:
        Decimal(fact.amount)
    except (InvalidOperation, ValueError):
        return f"invalid_amount:{fact.amount!r}"
    if not _is_decimal_str(fact.amount):
        return f"non_decimal_amount:{fact.amount!r}"

    # NG-05 上下文阶梯单调
    if fact.context_band and fact.context_band.max_input_tokens is not None:
        if fact.context_band.max_input_tokens <= fact.context_band.min_input_tokens:
            return "context_band_not_monotonic"

    # NG-03 稳定身份恒等（延迟导入避免循环）
    from .base import fact_key as _fk, stable_identity as _si

    identity = _si(
        provider_id=fact.provider_id,
        model_key=fact.model_key,
        component=fact.component,
        region=fact.region,
        billing_mode=fact.billing_mode,
        service_tier=fact.service_tier,
        context_band=fact.context_band,
        time_condition=fact.time_condition,
    )
    if fact.fact_key != _fk(identity):
        return "fact_key_mismatch"

    return None


def _is_decimal_str(s: str) -> bool:
    """是否为合法 Decimal 字符串（不含 e/E 指数，避免 float 混入）。"""
    try:
        d = Decimal(s)
    except InvalidOperation:
        return False
    return not d.is_nan() and not d.is_infinite()
