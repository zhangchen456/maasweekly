"""deepseek pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_DEEPSEEK = "deepseek-2"

class DeepSeekPricingExtractor:
    """解析 DeepSeek 价格页（M6：真实 HTML rowspan 表 + 峰谷）。

    真实页（api-docs.deepseek.com）是 Docusaurus 静态 HTML（http-1 可拿），
    单张 rowspan/colspan 嵌套表：列=模型（deepseek-v4-flash/pro/vision），
    行=维度。价格行结构：`PRICING | 1M INPUT TOKENS (CACHE HIT/MISS) | OFF-PEAK/PEAK | $0.007 | $0.022 | ...`
    模型名在第 0 行对应列。OFF-PEAK/PEAK 映射为 time_condition 峰谷。
    """

    version = _EXTRACTOR_VERSION_DEEPSEEK

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
        if not tables:
            return ExtractionResult(
                snapshot_id=snapshot.snapshot_id, extractor_version=self.version,
                models=[], price_facts=[], evidence=[], warnings=_drift_warnings("deepseek", []),
            )
        table = tables[0]
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        schedule_note = soup.find(string=lambda x: x and "Peak hours are" in x)
        schedule = str(schedule_note).strip() if schedule_note else None
        if schedule_note:
            table.html_fragment += str(schedule_note.parent)
        # 找 PRICING 行的起始，模型名在第一行
        # 模型名行：含 MODEL 标签，数据列从第 3 列开始
        model_row = None
        for r in table.rows:
            if r and "model" in r[0].lower() and any("deepseek" in c.lower() for c in r):
                model_row = r
                break
        if not model_row:
            return ExtractionResult(
                snapshot_id=snapshot.snapshot_id, extractor_version=self.version,
                models=[], price_facts=[], evidence=[], warnings=_drift_warnings("deepseek", []),
            )
        # 列 3+ 是模型
        model_cols: list[tuple[int, str]] = []  # (col_idx, model_name)
        for ci, cell in enumerate(model_row):
            if ci >= 3 and cell.strip().lower().startswith("deepseek"):
                model_cols.append((ci, _clean_model_name(cell)))
        if not model_cols:
            return ExtractionResult(
                snapshot_id=snapshot.snapshot_id, extractor_version=self.version,
                models=[], price_facts=[], evidence=[], warnings=_drift_warnings("deepseek", []),
            )
        ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
        evidence.append(ev)
        # 遍历数据行找 PRICING 块
        for row in table.data_rows():
            if not row or "pricing" not in row[0].lower():
                continue
            # 第 1 列是 token 类型（CACHE HIT/MISS/OUTPUT），第 2 列是 OFF-PEAK/PEAK
            if len(row) < 4:
                continue
            token_type = row[1].lower() if len(row) > 1 else ""
            period_label = row[2].lower() if len(row) > 2 else ""
            # 组件 + time_condition
            comp = None
            if "cache hit" in token_type:
                comp = "cache_read"
            elif "cache miss" in token_type:
                comp = "input"
            elif "output" in token_type:
                comp = "output"
            if not comp:
                continue
            period_enum: str | None = None
            if "off-peak" in period_label or "off_peak" in period_label:
                period_enum = "off_peak"
            elif "peak" in period_label:
                period_enum = "peak"
            tc = TimeCondition(period=period_enum, tz="UTC", schedule=schedule or period_label) if period_enum else None
            # 各模型列价格
            for ci, model_name in model_cols:
                if ci >= len(row):
                    continue
                p = _parse_price_html(row[ci])
                if not p:
                    continue
                facts.append(_make_fact(
                    snapshot, ev.evidence_id, "deepseek", model_name,
                    comp, "realtime", p, region=_region_for("deepseek"),
                    time_condition=tc,
                ))
        # 模型 profile
        for ci, model_name in model_cols:
            models.append(ModelProfile(
                provider_id="deepseek",
                model_key=model_name.lower().replace(" ", "-"),
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
            warnings=_drift_warnings("deepseek", facts),
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
            if line.startswith("## ") and "cache" not in line.lower() and "time" not in line.lower():
                current_model = line[3:].strip()
                current_ctx = None
            # 主表：Model | Context window | Input (cache miss) | Output
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
                            facts.append(_make_fact(snapshot, ev.evidence_id, "deepseek", current_model, "input", "realtime", inp, region=_region_for("deepseek")))
                        if out:
                            facts.append(_make_fact(snapshot, ev.evidence_id, "deepseek", current_model, "output", "realtime", out, region=_region_for("deepseek")))
                models.append(ModelProfile(
                    provider_id="deepseek",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            # Cache hit 子表
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
                    if len(row) >= 2 and "cache" in row[0].lower():
                        p = _parse_price(row[1])
                        if p:
                            facts.append(_make_fact(snapshot, ev.evidence_id, "deepseek", current_model, "cache_read", "realtime", p, region=_region_for("deepseek")))
                i = j
                continue
            # Time-based pricing 子表
            elif line.startswith("| Period") and current_model:
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
                        period = row[0].lower().strip()
                        schedule = row[1].strip()
                        p = _parse_price(row[2])
                        if not p:
                            continue
                        period_enum = "off_peak" if "off" in period else ("peak" if "peak" in period else "valley")
                        tc = TimeCondition(period=period_enum, tz="Asia/Shanghai", schedule=schedule)
                        facts.append(_make_fact(
                            snapshot, ev.evidence_id, "deepseek", current_model, "input", "realtime", p,
                            region=_region_for("deepseek"), time_condition=tc,
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
            warnings=_drift_warnings("deepseek", facts),
        )

