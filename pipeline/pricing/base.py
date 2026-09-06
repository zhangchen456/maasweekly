"""价格模块领域类型（迁移自追浪 app-core-service-001 的 goals/base.py，v0.3.0 方案 M0 契约）。

改造点：
- pydantic BaseModel → dataclass（maasweekly 管线零第三方依赖原则）
- 去 Blob Store：ContentSnapshot 直接携带 content 字符串（maasweekly 用快照文件落盘）
- 保留全部字段语义与「证据先于结论」铁律：每条 PriceFact 必须指向一条 Evidence

设计原则（源项目）：
- 证据先于结论：任何进入台账的值必须能回链到 ContentSnapshot + Evidence
- 当前值与价格条件分离：纵向 PriceFact，展示时再透视成台账
- 金额用 Decimal 字符串，禁止浮点数
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# 价格组件
PriceComponent = str  # "input" | "output" | "cache_read" | "cache_write"
# 计费模式
BillingMode = str  # "realtime" | "batch"
# 峰谷时段
TimePeriod = str  # "peak" | "off_peak" | "valley"
# Artifact 字段状态
FieldState = str  # "confirmed" | "estimated" | "conflicted" | "stale" | "missing" | "not_applicable"


@dataclass
class ContentSnapshot:
    """官方页面当时的原始证据。maasweekly 版直接携带 content（无 Blob Store）。"""

    snapshot_id: str
    source_key: str
    url: str
    fetched_at: float                 # epoch ms
    http_status: int
    content_type: str
    sha256: str
    content: str                      # 页面原文（HTML 或 markdown fixture）
    fetcher_version: str = "playwright-1"
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class Evidence:
    """指向快照中的定位信息。

    locator_type: table_row / dom_selector / json_pointer / markdown_block
    """

    evidence_id: str
    snapshot_id: str
    locator_type: str
    locator: str
    extractor_version: str = ""
    excerpt: str | None = None
    excerpt_hash: str | None = None


@dataclass
class ModelProfile:
    """模型档案。展示名与稳定 model_key 分离。"""

    provider_id: str
    model_key: str                    # 稳定身份键，不随展示名变化
    display_name: str
    model_class: str                  # flagship / small / reasoning / multimodal / other
    lifecycle_status: str             # active / preview / deprecated / unknown
    context_window_tokens: int | None = None
    evidence_id: str | None = None


@dataclass
class TimeCondition:
    """峰谷时段等时间条件。period 归一枚举保证跨厂商可比。"""

    period: TimePeriod
    tz: str                           # IANA 名称，如 Asia/Shanghai
    schedule: str                     # 如 "00:00-08:00"


@dataclass
class ContextBand:
    """长上下文阶梯边界。"""

    min_input_tokens: int = 0
    max_input_tokens: int | None = None


@dataclass
class PriceFact:
    """纵向价格事实。

    稳定身份 = provider + model + component + region + billing_mode
              + service_tier + context_band + time_condition(period+tz+schedule)
    amount / effective_at / observed_at / evidence 不进入稳定身份；
    它们变化时生成新的 Fact 版本。金额用 Decimal 字符串，禁止浮点数。
    """

    fact_key: str                     # sha256(stable_identity)
    provider_id: str
    model_key: str
    component: PriceComponent
    billing_mode: BillingMode
    amount: str                       # Decimal 字符串，如 "1.250000"
    currency: str                     # 原币种，如 USD / CNY
    unit_quantity: int                # 如 1000000
    unit_name: str                    # 如 token
    region: str                       # 如 global / cn / us
    service_tier: str                 # 如 standard / priority
    context_band: ContextBand | None = None
    time_condition: TimeCondition | None = None
    effective_at: float | None = None
    observed_at: float = 0.0          # epoch ms
    evidence_id: str = ""
    field_state: FieldState = "confirmed"
    stale_reason: str | None = None


@dataclass
class SourceSpec:
    """来源规格（registry.py 展开）。"""

    source_key: str
    provider_id: str
    url: str
    required: bool = True
    fetcher_version: str = "http-1"


@dataclass
class SnapshotMetadata:
    """上一轮快照元数据（缓存协商用）。"""

    sha256: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class ExtractionResult:
    """Extractor 的输出：模型档案 + 价格事实候选 + 证据。

    候选事实尚未经过归一与校验；normalize.py 负责后续门禁。
    """

    snapshot_id: str = ""
    extractor_version: str = ""
    models: list[ModelProfile] = field(default_factory=list)
    price_facts: list[PriceFact] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def stable_identity(
    provider_id: str,
    model_key: str,
    component: str,
    region: str,
    billing_mode: str,
    service_tier: str,
    context_band: ContextBand | None,
    time_condition: TimeCondition | None,
) -> str:
    """计算 PriceFact 稳定身份字符串。八元组拼接，None 维度空串占位。"""
    cb = (
        f"{context_band.min_input_tokens}:{context_band.max_input_tokens}"
        if context_band
        else ""
    )
    tc = (
        f"{time_condition.period}|{time_condition.tz}|{time_condition.schedule}"
        if time_condition
        else ""
    )
    return "|".join(
        [provider_id, model_key, component, region, billing_mode, service_tier, cb, tc]
    )


def fact_key(identity: str) -> str:
    """稳定身份的 sha256，作为 PriceFact.fact_key。"""
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
