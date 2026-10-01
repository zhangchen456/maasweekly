"""google pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_GOOGLE = "google-1"

class GooglePricingExtractor:
    """解析 Google Gemini 价格页（M6：真实 HTML 表格）。

    真实页（ai.google.dev）Playwright 渲染后，每个模型一张表，模型名在表前的 h2 标题。
    表结构：行=Input price / Output price (including thinking tokens) / Context caching price，
    列=Free Tier / Paid Tier。价格在 Paid 列，含时效（'$0.75 through December 31, 2026.
    $1.50 starting January 1, 2027'），取当前生效值（第一个价格，当前日期落在 through 段内）。

    同一模型可能有多张表（不同变体），DOM 无明确区分；取该模型第一张表作为代表价，
    避免重复 model_key 冲突（fact stable_identity 相同会覆盖）。
    """

    version = _EXTRACTOR_VERSION_GOOGLE

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        raw = snapshot.content
        if raw.lstrip().startswith(("<", "<!doctype", "<!DOCTYPE")):
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

    def _extract_html(self, snapshot: ContentSnapshot, html: str) -> ExtractionResult:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        seen_models: set[str] = set()
        for idx, table in enumerate(soup.find_all("table")):
            rows_raw = table.find_all("tr")
            if not rows_raw:
                continue
            # 行文本判断是否价格表
            all_text = table.get_text(" ", strip=True).lower()
            if "input price" not in all_text or "paid tier" not in all_text:
                continue
            # 模型名：表前最近的 h2/h3
            model_el = table.find_previous(["h2", "h3"])
            model_name = _clean_model_name(model_el.get_text(strip=True)) if model_el else ""
            if not model_name:
                continue
            model_key = model_name.lower().replace(" ", "-")
            # 同模型多表取第一张
            if model_key in seen_models:
                continue
            # 找 Paid Tier 列索引（表头含 Paid）
            header_cells = [c.get_text(" ", strip=True) for c in rows_raw[0].find_all(["td", "th"])]
            paid_col = None
            for ci, h in enumerate(header_cells):
                if "paid" in h.lower():
                    paid_col = ci
                    break
            if paid_col is None:
                continue
            ev_idx += 1
            # 模型名在表外 h2/h3 标题里——并入摘录才能独立核价（P1-3）
            html_frag = _with_heading_context(table, str(table))
            ev = Evidence(
                evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                snapshot_id=snapshot.snapshot_id,
                locator_type="dom_selector",
                locator=f"table:nth-of-type({idx + 1})",
                excerpt=html_frag,
                excerpt_hash=hashlib.sha256(html_frag.encode()).hexdigest(),
                extractor_version=self.version,
            )
            evidence.append(ev)
            has_fact = False
            for row in rows_raw[1:]:
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                if not cells:
                    continue
                label = cells[0].lower()
                comp = None
                if "input" in label and "caching" not in label:
                    comp = "input"
                elif "output" in label:
                    comp = "output"
                elif "caching" in label or "cache" in label:
                    comp = "cache_read"
                if not comp or paid_col >= len(cells):
                    continue
                # 价格含时效文本，取第一个价格（当前生效，2026-08 落在 through 段内）
                p = _parse_price_html(cells[paid_col])
                if not p:
                    continue
                facts.append(_make_fact(
                    snapshot, ev.evidence_id, "google", model_name,
                    comp, "realtime", p, region=_region_for("google"),
                ))
                has_fact = True
            if has_fact:
                seen_models.add(model_key)
                models.append(ModelProfile(
                    provider_id="google",
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
            warnings=_drift_warnings("google", facts),
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
            # H2 = 模型节，排除 Long context 子标题
            if line.startswith("## ") and "long context" not in line.lower():
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
                                snapshot, ev.evidence_id, "google", current_model,
                                "input", "realtime", inp, region=_region_for("google"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "google", current_model,
                                "output", "realtime", out, region=_region_for("google"),
                            ))
                models.append(ModelProfile(
                    provider_id="google",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            # 长上下文阶梯子表：Input length | Input price
            elif line.startswith("| Input length") and current_model:
                rows, j = _split_table(lines, i)
                ev, ev_idx = _evidence_for_table(lines, i, j, snapshot, ev_idx, self.version, rows)
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 2:
                        band = _parse_context_band(row[0])
                        p = _parse_price(row[1])
                        if p and band:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "google", current_model, "input", "realtime", p,
                                region=_region_for("google"), context_band=band,
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
            warnings=_drift_warnings("google", facts),
        )

