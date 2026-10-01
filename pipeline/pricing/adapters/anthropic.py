"""anthropic pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
from __future__ import annotations
from .common import (
    ContentSnapshot,
    ContextBand,
    Decimal,
    Evidence,
    ExtractionResult,
    HtmlTable,
    InvalidOperation,
    ModelProfile,
    PriceFact,
    TimeCondition,
    _PRICE_UNIT_PATTERNS,
    _PROVIDER_REGIONS,
    _QWEN_SCOPE_REGION,
    _clean_model_name,
    _drift_warnings,
    _evidence_for_html,
    _evidence_for_table,
    _evidence_id,
    _expand_km,
    _make_fact,
    _parse_amount_only,
    _parse_context_band,
    _parse_html_tables,
    _parse_price,
    _parse_price_html,
    _parse_tokens,
    _region_for,
    _row_locator,
    _safe_span,
    _split_table,
    _strip_zero_width,
    _with_heading_context,
    fact_key,
    hashlib,
    re,
    stable_identity
)

_EXTRACTOR_VERSION_ANTHROPIC = "anthropic-1"

class AnthropicPricingExtractor:
    """解析 Anthropic 价格页（M6：真实 HTML 表格）。

    真实页（docs.anthropic.com）Playwright 渲染后，价格在第一张表：
    表头 Model | Base Input Tokens | 5m Cache Writes | 1h Cache Writes | Cache Hits & Refreshes | Output Tokens
    行=模型，价格 '$10 / MTok'（MTok = 1M tokens）。
    列映射：Base Input→input，5m/1h Cache Writes→cache_write，Cache Hits→cache_read，Output→output。
    """

    version = _EXTRACTOR_VERSION_ANTHROPIC

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        raw = snapshot.content
        if raw.lstrip().startswith(("<", "<!doctype", "<!DOCTYPE")):
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

    def _extract_html(self, snapshot: ContentSnapshot, html: str) -> ExtractionResult:
        tables = _parse_html_tables(html)
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        for table in tables:
            if not table.rows:
                continue
            header = table.rows[0]
            # 只处理含 Base Input Tokens + Output 的价格表（跳过 CCU 概念表等）
            flat = " ".join(header).lower()
            if "base input" not in flat or "output" not in flat:
                continue
            model_col = None
            cols: list[tuple[int, str, TimeCondition | None]] = []
            for ci, h in enumerate(header):
                hl = h.lower()
                if "model" in hl and model_col is None:
                    model_col = ci
                if "base input" in hl:
                    cols.append((ci, "input", None))
                elif "cache hits" in hl or "cache read" in hl or ("cache" in hl and "refresh" in hl):
                    cols.append((ci, "cache_read", None))
                elif "cache write" in hl or "cache writes" in hl:
                    # 5m/1h 时效是计费条件（Task 02 §4.1：同一身份禁止静默覆盖）。
                    # 不区分时两列同 fact_key，dict 覆盖会丢失 1h 价或误报涨跌。
                    tc = None
                    if "5m" in hl:
                        tc = TimeCondition(period="cache_write_5m", tz="UTC",
                                           schedule="5m")
                    elif "1h" in hl:
                        tc = TimeCondition(period="cache_write_1h", tz="UTC",
                                           schedule="1h")
                    cols.append((ci, "cache_write", tc))
                elif "output" in hl:
                    cols.append((ci, "output", None))
            if model_col is None:
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            for row in table.data_rows():
                if model_col >= len(row):
                    continue
                model_name = _clean_model_name(row[model_col])
                if not model_name:
                    continue
                model_key = model_name.lower().replace(" ", "-")
                has_fact = False
                for ci, comp, tc in cols:
                    if ci >= len(row):
                        continue
                    p = _parse_price_html(row[ci])
                    if not p:
                        continue
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "anthropic", model_name,
                        comp, "realtime", p, region=_region_for("anthropic"),
                        time_condition=tc,
                    ))
                    has_fact = True
                if has_fact:
                    models.append(ModelProfile(
                        provider_id="anthropic",
                        model_key=model_key,
                        display_name=model_name,
                        model_class="flagship",
                        lifecycle_status="active",
                        context_window_tokens=None,
                        evidence_id=ev.evidence_id,
                    ))
        return ExtractionResult(
            snapshot_id=snapshot.snapshot_id,
            extractor_version=self.version,
            models=models,
            price_facts=facts,
            evidence=evidence,
            warnings=_drift_warnings("anthropic", facts),
        )

    def _extract_markdown(self, snapshot: ContentSnapshot, raw: str) -> ExtractionResult:
        """旧 markdown fixture 路径（M2/M4 回归测试）。"""
        lines = raw.splitlines()
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        current_model: str | None = None
        current_ctx: int | None = None
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # H2 = 模型节，排除 Prompt caching 子标题
            if line.startswith("## ") and "caching" not in line.lower() and "cache" not in line.lower():
                current_model = line[3:].strip()
                current_ctx = None
            # 主表：Model | Context window | Input | Output
            elif line.startswith("| Model") and current_model:
                rows, j = _split_table(lines, i)
                ev, ev_idx = _evidence_for_table(lines, i, j, snapshot, ev_idx, self.version, rows)
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 4:
                        ctx = _parse_tokens(row[1])
                        if ctx:
                            current_ctx = ctx
                        inp = _parse_price(row[2])
                        out = _parse_price(row[3])
                        if inp:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "anthropic", current_model,
                                "input", "realtime", inp, region=_region_for("anthropic"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "anthropic", current_model,
                                "output", "realtime", out, region=_region_for("anthropic"),
                            ))
                models.append(ModelProfile(
                    provider_id="anthropic",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            # 缓存子表：Tier | Price
            elif line.startswith("| Tier") and current_model:
                rows, j = _split_table(lines, i)
                ev, ev_idx = _evidence_for_table(lines, i, j, snapshot, ev_idx, self.version, rows)
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 2:
                        tier = row[0].lower()
                        p = _parse_price(row[1])
                        if not p:
                            continue
                        if "cache read" in tier:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "anthropic", current_model,
                                "cache_read", "realtime", p, region=_region_for("anthropic"),
                            ))
                        elif "cache write" in tier:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "anthropic", current_model,
                                "cache_write", "realtime", p, region=_region_for("anthropic"),
                            ))
                i = j
                continue
            i += 1
        return ExtractionResult(
            snapshot_id=snapshot.snapshot_id,
            extractor_version=self.version,
            models=models,
            price_facts=facts,
            evidence=evidence,
            warnings=_drift_warnings("anthropic", facts),
        )

