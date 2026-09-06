"""View dataset 构建（迁移自追浪 view_data_adapter.py 的纯计算部分）。

改造点：去 DB 读取（goal_store/app_setting），改为纯函数——
输入本轮 facts + model profiles + 上轮数据，输出模板消费的 dataset。

- 比价前单位归一为每 1M tokens（Decimal 计算，禁浮点）
- 货币换算用传入的 fx_snapshot（手动维护，不联网）
- 缺失价格 = None（模板显示"暂无"）
- partial 模式：failed_sources 的厂商沿用上轮 facts（stale 标记）
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

# 手动维护的汇率快照（追浪 app_setting 运营可配的等价简化）。
# base USD；rates: currency → 每 1 USD 兑换数。调整时更新 as_of。
DEFAULT_FX = {
    "base": "USD",
    "rates": {"CNY": "7.1", "USD": "1"},
    "source": "manual",
    "as_of": "2026-09-07",
}


def _dec(s: str | None) -> Decimal | None:
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def fact_to_dict(f) -> dict[str, Any]:
    """PriceFact dataclass → 可 JSON 序列化的 dict（ledger_history 存档用）。"""
    return {
        "fact_key": f.fact_key,
        "provider_id": f.provider_id,
        "model_key": f.model_key,
        "component": f.component,
        "billing_mode": f.billing_mode,
        "amount": f.amount,
        "currency": f.currency,
        "unit_quantity": f.unit_quantity,
        "unit_name": f.unit_name,
        "region": f.region,
        "service_tier": f.service_tier,
        "context_band": ({"min": f.context_band.min_input_tokens,
                          "max": f.context_band.max_input_tokens}
                         if f.context_band else None),
        "time_condition": ({"period": f.time_condition.period,
                            "tz": f.time_condition.tz,
                            "schedule": f.time_condition.schedule}
                           if f.time_condition else None),
        "observed_at": f.observed_at,
        "evidence_id": f.evidence_id,
        "field_state": f.field_state,
        "stale_reason": f.stale_reason,
    }


def build_view_dataset(
    facts: list[dict],
    model_profiles: dict[str, str],   # "provider:model_key" → display_name
    source_urls: dict[str, str],      # evidence_id → snapshot url（空 dict 亦可）
    *,
    failed_sources: list[str],
    published_at: float,
    artifact_version: str,
    fx_snapshot: dict | None = None,
    default_currency: str = "CNY",
) -> dict[str, Any]:
    """构建 ledger.json（模板注入用 dataset）。

    facts: fact_to_dict 产出的 dict 列表（本轮 + partial 沿用的上轮 stale facts）
    """
    fx = fx_snapshot or DEFAULT_FX
    base_currency = fx.get("base", "USD")
    rates = fx.get("rates", {})

    providers_set: set[str] = set()
    models_set: set[str] = set()
    currencies_set: set[str] = set()
    prices: list[dict] = []

    for f in facts:
        provider, model = f.get("provider_id", ""), f.get("model_key", "")
        component, currency = f.get("component", ""), f.get("currency", "")
        if provider:
            providers_set.add(provider)
        if model:
            models_set.add(model)
        if currency:
            currencies_set.add(currency)

        # 单位归一为每 1M tokens（Decimal）
        amount_per_1m = None
        original = _dec(f.get("amount"))
        if original is not None:
            uq = f.get("unit_quantity") or 0
            amount_per_1m = (
                original / Decimal(uq) * Decimal(1_000_000) if uq > 0 else original
            )

        # 币种换算到 default_currency
        converted = None
        if amount_per_1m is not None:
            if currency == default_currency:
                converted = amount_per_1m
            else:
                rate = _dec(rates.get(default_currency if base_currency == currency else currency))
                if rate is None and base_currency == default_currency and currency != base_currency:
                    # currency → base（USD）→ default
                    r_inv = _dec(rates.get(currency))
                    if r_inv and r_inv > 0:
                        rate = Decimal(1) / r_inv
                if rate is not None:
                    try:
                        converted = amount_per_1m * rate
                    except (InvalidOperation, ArithmeticError):
                        converted = None

        prices.append({
            "provider": provider,
            "model": model,
            "model_display_name": model_profiles.get(f"{provider}:{model}", model),
            "component": component,
            "amount": f.get("amount"),
            "amount_per_1m": str(amount_per_1m) if amount_per_1m is not None else None,
            "converted_amount_per_1m": str(converted) if converted is not None else None,
            "converted_currency": default_currency if converted is not None else None,
            "currency": currency,
            "unit_quantity": f.get("unit_quantity"),
            "unit_name": f.get("unit_name"),
            "region": f.get("region", ""),
            "billing_mode": f.get("billing_mode", ""),
            "service_tier": f.get("service_tier", ""),
            "context_band": f.get("context_band"),
            "time_condition": f.get("time_condition"),
            "effective_at": f.get("effective_at"),
            "observed_at": f.get("observed_at"),
            "field_state": f.get("field_state", "confirmed"),
            "stale_reason": f.get("stale_reason"),
            "source_url": source_urls.get(f.get("evidence_id", ""), ""),
        })

    return {
        "meta": {
            "published_at": published_at,
            "partial": bool(failed_sources),
            "failed_sources": failed_sources,
            "artifact_version": artifact_version,
        },
        "providers": sorted(providers_set),
        "models": sorted(models_set),
        "prices": prices,
        "currencies": sorted(currencies_set) if currencies_set else ["USD", "CNY"],
        "default_currency": default_currency,
        "fx_snapshot": fx,
    }
