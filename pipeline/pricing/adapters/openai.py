"""openai pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_OPENAI = "openai-1"

class OpenAIPricingExtractor:
    """解析 OpenAI 价格页（M6：真实 HTML 表格）。

    真实页（developers.openai.com）用 Playwright 渲染后是 16 张 HTML 表，
    每张表两层表头：上层 Short/Long context 跨列，下层 Input/Cached input/Cache writes/Output。
    行=模型名。价格是裸 '$4.00'，隐含 /1M tokens。

    旧 markdown 路径（_split_table 扫 | 分隔）保留为 _extract_markdown，
    供 M2/M4 的 .md fixture 回归测试使用；真实 HTML 走 _extract_html。
    """

    version = _EXTRACTOR_VERSION_OPENAI

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        raw = snapshot.content
        # HTML 页以 <table 或 <!doctype 开头；fixture markdown 以 # 开头
        if raw.lstrip().startswith(("<", "<!doctype", "<!DOCTYPE")):
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

    def _extract_html(self, snapshot: ContentSnapshot, html: str) -> ExtractionResult:
        tables = _parse_html_tables(html)
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        # 列名 → component 映射（不区分 Short/Long context，都产出 input/output/cache_*）
        # context_band 标记：表头含 Long context 的列设长上下文 band
        for table in tables:
            if not table.rows or len(table.rows) < 2:
                continue
            header = table.rows[1] if len(table.rows) > 1 else table.rows[0]
            # 找 Model 列与各价格列
            model_col = None
            cols: list[tuple[int, str, bool]] = []  # (col_idx, component, is_long_ctx)
            ctx_band_active = False
            for ci, h in enumerate(header):
                hl = h.lower()
                if h.strip() == "Model" or "model" in hl and "modality" not in hl:
                    model_col = ci
                if "long context" in hl:
                    ctx_band_active = True
                if "short context" in hl:
                    ctx_band_active = False
                comp = None
                if hl == "input" or "input" in hl and "cached" not in hl and "cache" not in hl:
                    comp = "input"
                elif "cached input" in hl or ("cache" in hl and "read" in hl):
                    comp = "cache_read"
                elif "cache write" in hl or "cache writes" in hl:
                    comp = "cache_write"
                elif hl == "output" or "output" in hl and "cost" not in hl:
                    comp = "output"
                if comp:
                    cols.append((ci, comp, ctx_band_active))
            if model_col is None:
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            for row in table.data_rows():
                if model_col >= len(row):
                    continue
                model_name = row[model_col].strip()
                if not model_name or "$" not in model_name and not any("$" in row[ci] for ci, _, _ in cols):
                    continue
                # 跳过非价格行（如 Modality 行 Audio/Text/Image）
                if model_name.lower() in ("audio", "text", "image", "size", "portrait", "landscape"):
                    continue
                model_key = model_name.lower().replace(" ", "-")
                has_fact = False
                for ci, comp, is_long in cols:
                    if ci >= len(row):
                        continue
                    p = _parse_price_html(row[ci])
                    if not p:
                        continue
                    band = ContextBand(min_input_tokens=200_000, max_input_tokens=None) if is_long else None
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "openai", model_name,
                        comp, "realtime", p, region=_region_for("openai"),
                        context_band=band,
                    ))
                    has_fact = True
                if has_fact:
                    models.append(ModelProfile(
                        provider_id="openai",
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
            warnings=_drift_warnings("openai", facts),
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
            # H2 = 模型节
            if line.startswith("## ") and not line.startswith("## Cached") and not line.startswith("## Batch"):
                current_model = line[3:].strip()
                current_ctx = None
            # 主表：Model | Context window | Input | Output
            elif line.startswith("| Model") and current_model:
                rows, j = _split_table(lines, i)
                ev_idx += 1
                ev = Evidence(
                    evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                    snapshot_id=snapshot.snapshot_id,
                    locator_type="markdown_block",
                    locator=_row_locator(i + 1, j),
                    excerpt=" | ".join(rows[0]) if rows else None,
                    excerpt_hash=hashlib.sha256((" | ".join(rows[0]) if rows else "").encode()).hexdigest(),
                    extractor_version=self.version,
                )
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
                                snapshot, ev.evidence_id, "openai", current_model,
                                "input", "realtime", inp, region=_region_for("openai"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "openai", current_model,
                                "output", "realtime", out, region=_region_for("openai"),
                            ))
                models.append(ModelProfile(
                    provider_id="openai",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            # Cached input 子表
            elif line.startswith("| Tier") and current_model:
                rows, j = _split_table(lines, i)
                ev_idx += 1
                ev = Evidence(
                    evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                    snapshot_id=snapshot.snapshot_id,
                    locator_type="markdown_block",
                    locator=_row_locator(i + 1, j),
                    excerpt=lines[i].strip(),
                    extractor_version=self.version,
                )
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 2:
                        tier = row[0].lower()
                        p = _parse_price(row[1])
                        if not p:
                            continue
                        if "cache read" in tier:
                            facts.append(_make_fact(snapshot, ev.evidence_id, "openai", current_model, "cache_read", "realtime", p, region=_region_for("openai")))
                        elif "cache write" in tier:
                            facts.append(_make_fact(snapshot, ev.evidence_id, "openai", current_model, "cache_write", "realtime", p, region=_region_for("openai")))
                i = j
                continue
            # Batch 子表
            elif line.startswith("| Mode") and current_model:
                rows, j = _split_table(lines, i)
                ev_idx += 1
                ev = Evidence(
                    evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                    snapshot_id=snapshot.snapshot_id,
                    locator_type="markdown_block",
                    locator=_row_locator(i + 1, j),
                    excerpt=lines[i].strip(),
                    extractor_version=self.version,
                )
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 3:
                        inp = _parse_price(row[1])
                        out = _parse_price(row[2])
                        if inp:
                            facts.append(_make_fact(snapshot, ev.evidence_id, "openai", current_model, "input", "batch", inp, region=_region_for("openai")))
                        if out:
                            facts.append(_make_fact(snapshot, ev.evidence_id, "openai", current_model, "output", "batch", out, region=_region_for("openai")))
                i = j
                continue
            # Long context 阶梯
            elif line.startswith("| Input length") and current_model:
                rows, j = _split_table(lines, i)
                ev_idx += 1
                ev = Evidence(
                    evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                    snapshot_id=snapshot.snapshot_id,
                    locator_type="markdown_block",
                    locator=_row_locator(i + 1, j),
                    excerpt=lines[i].strip(),
                    extractor_version=self.version,
                )
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 2:
                        band = _parse_context_band(row[0])
                        p = _parse_price(row[1])
                        if p and band:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "openai", current_model, "input", "realtime", p,
                                region=_region_for("openai"), context_band=band,
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
            warnings=_drift_warnings("openai", facts),
        )

