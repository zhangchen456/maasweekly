#!/usr/bin/env python3
"""价格解析器离线回归测试（迁移自追浪 test_goal_m4/m6 的核心断言）。

八家厂商 × 双格式（真实渲染 HTML + markdown fixture）走 extractor → normalize 门禁：
- facts ≥ 1（零产出 = 结构漂移，厂商页面改版或解析器退化）
- 门禁零拒绝（证据链 / Decimal / 稳定身份 / 必填 / 阶梯单调）
- 零 structure_drift 告警
- region / currency 与 registry 预期一致
- 每条 fact 的 evidence_id 可回链

无需网络、无需 playwright——这是 CI 每日防退化的底线测试。
运行：python3 tests/test_pricing_extractors.py（从任意 cwd，退出码 0 = 全绿）
"""
import hashlib
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "pipeline"))

from pricing.base import ContentSnapshot  # noqa: E402
from pricing.extractors import (  # noqa: E402
    OpenAIPricingExtractor,
    AnthropicPricingExtractor,
    GooglePricingExtractor,
    DeepSeekPricingExtractor,
    KimiPricingExtractor,
    GlmPricingExtractor,
    DoubaoPricingExtractor,
    QwenPricingExtractor,
)
from pricing.normalize import normalize_and_validate  # noqa: E402

FIXTURES = BASE / "tests" / "fixtures" / "pricing"

# 八家：(provider_id, Extractor 类, 期望 region, 期望币种)
# 期望值按「真实 HTML 页」口径；两处与 md fixture 不同（见 run_case）：
# - deepseek md fixture 是国内页 CNY 定价（真实 HTML 是国际页 USD）
# - qwen 真实页同时列 global/cn/us 三区域定价（多区域是官方页事实，非解析错误）
EIGHT = [
    ("openai", OpenAIPricingExtractor, "global", "USD"),
    ("anthropic", AnthropicPricingExtractor, "global", "USD"),
    ("google", GooglePricingExtractor, "global", "USD"),
    ("deepseek", DeepSeekPricingExtractor, "cn", "USD"),
    ("kimi", KimiPricingExtractor, "cn", "CNY"),
    ("glm", GlmPricingExtractor, "cn", "CNY"),
    ("doubao", DoubaoPricingExtractor, "cn", "CNY"),
    ("qwen", QwenPricingExtractor, "cn", "CNY"),
]

# region/currency 断言口径按 (provider_id, suffix) 定制：
# - 默认：HTML 按 EIGHT 表断言全量一致；md fixture 只查证据链（源 m4 测试对 md 不断言 region/currency）
# - qwen HTML：官方页同时列 global/cn/us 多区域定价（事实而非错误），断言三区域都有
# - deepseek md：fixture 是国内页 CNY（真实 HTML 是国际页 USD）
def check_region_currency(provider_id, suffix, facts):
    if suffix == "md":
        if provider_id == "deepseek":
            for f in facts:
                assert f.currency == "CNY", f"deepseek(md): currency={f.currency} 期望 CNY"
        return  # 其余 md fixture 不做 region/currency 全量断言
    if provider_id == "qwen":
        regions = {f.region for f in facts}
        assert {"global", "cn"} <= regions, f"qwen(html): 多区域缺失，实际 {regions}"
        for f in facts:
            assert f.currency == "CNY", f"qwen(html): currency={f.currency} 期望 CNY"
        return
    # 其余按 EIGHT 表（闭包外传入期望值）


def make_snapshot(provider_id: str, content: str) -> ContentSnapshot:
    raw = content.encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    return ContentSnapshot(
        snapshot_id=f"snap-{sha[:24]}",
        source_key=f"{provider_id}:pricing",
        url=f"https://example.com/{provider_id}",
        fetched_at=0,
        http_status=200,
        content_type="text/html; charset=utf-8",
        sha256=sha,
        content=content,
        fetcher_version="playwright-1",
    )


def run_case(provider_id: str, cls, region: str, currency: str, suffix: str) -> None:
    fixture = FIXTURES / f"{provider_id}_pricing.{suffix}"
    assert fixture.exists(), f"缺少 fixture：{fixture}"
    content = fixture.read_text(encoding="utf-8")
    result = cls().extract(make_snapshot(provider_id, content))
    report = normalize_and_validate(result)

    label = f"{provider_id}({suffix})"
    # 1. facts ≥ 1
    assert result.price_facts, f"{label}: 零 fact 产出（结构漂移）"
    # 2. 门禁零拒绝
    assert not report.rejected, (
        f"{label}: {len(report.rejected)} 个 fact 被门禁拒绝，"
        f"首条原因: {report.rejected[0][1] if report.rejected else ''}"
    )
    assert len(report.accepted) == len(result.price_facts), f"{label}: accepted 数与 facts 不符"
    # 3. 零结构漂移告警
    drift = [w for w in result.warnings if "structure_drift" in w.lower()]
    assert not drift, f"{label}: 结构漂移告警 {drift}"
    # 4. region / currency 按口径校验
    check_region_currency(provider_id, suffix, result.price_facts)
    if suffix == "html" and provider_id not in ("qwen",):
        for f in result.price_facts:
            assert f.region == region, f"{label}: region={f.region} 期望 {region}"
            assert f.currency == currency, f"{label}: currency={f.currency} 期望 {currency}"
    for f in result.price_facts:
        assert f.evidence_id, f"{label}: fact 无 evidence_id"
    # 5. 证据回链
    ev_ids = {e.evidence_id for e in result.evidence}
    for f in result.price_facts:
        assert f.evidence_id in ev_ids, f"{label}: evidence_id {f.evidence_id} 无回链"
    print(f"  ✓ {label}: {len(result.price_facts)} facts, {len(result.models)} models")


def main() -> int:
    failures = []
    for provider_id, cls, region, currency in EIGHT:
        for suffix in ("html", "md"):
            try:
                run_case(provider_id, cls, region, currency, suffix)
            except AssertionError as e:
                failures.append(str(e))
                print(f"  ✗ {e}")
    if failures:
        print(f"\n{len(failures)} 项失败")
        return 1
    print("\n八家 × 双格式 fixture 回归全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
