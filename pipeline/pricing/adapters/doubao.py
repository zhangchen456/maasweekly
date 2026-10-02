"""doubao pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_DOUBAO = "doubao-3"

class DoubaoPricingExtractor:
    """解析豆包（火山引擎）价格页（M6：真实 HTML 表格）。

    真实页（volcengine.com）Playwright 渲染后是多张表。可靠的模型价格表表头含
    「模型名称」列（行=模型），价格列「输入(非音频) 元/百万token」「输出 元/百万token」，
    部分表有「输入长度 [0, 1024]」阶梯（映射 ContextBand）。
    无模型名的表（仅有「类型」列）跳过——无 model_key 无法产 fact。
    价格单元格是 '6.00 元' 或 '6.00'，单位由表头标明（元/百万token）。
    """

    version = _EXTRACTOR_VERSION_DOUBAO

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        raw = snapshot.content
        if raw.lstrip().startswith(("<", "<!doctype", "<!DOCTYPE")):
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

    def _extract_html(self, snapshot: ContentSnapshot, html: str) -> ExtractionResult:
        from bs4 import BeautifulSoup
        dom_tables = BeautifulSoup(html, "html.parser").find_all("table")
        tables = _parse_html_tables(html)
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        for table in tables:
            if not table.rows:
                continue
            dom_table = dom_tables[table.table_index]
            section = dom_table.find_previous(string=lambda x: x and re.fullmatch(r"\s*(?:在线推理（[^）]+）|批量推理)\s*", x))
            label = str(section).strip() if section else ""
            billing = "batch" if "批量" in label else "realtime"
            tier = "priority" if "低延迟" in label else "flex" if "低优" in label else "standard"
            if section:
                table.html_fragment = "<p>" + label + "</p>" + table.html_fragment
            header = table.rows[0]
            flat = " ".join(header)
            # 只处理含「模型名称」或「模型」列的价格表
            if "模型" not in flat or "元" not in flat:
                continue
            model_col = None
            cols: list[tuple[int, str]] = []
            band_col = None
            # 千 token 计价的表（豆包「条件 千 token」）：band 数值需 ×1000 换算
            band_in_kilo_tokens = "千 token" in flat or "千token" in flat.replace(" ", "")
            for ci, h in enumerate(header):
                hl = h.lower()
                if ("模型名称" in h or h.strip() == "模型") and model_col is None:
                    model_col = ci
                elif "输入长度" in h or "条件" in h and "token" in hl:
                    band_col = ci
                elif "输入" in h and "缓存" not in h:
                    # 「输入(非音频)」是主列，「输入(音频)」是音频附加列——
                    # 只有列名明确以「(音频)」/「（音频）」标注的才是音频列。
                    if "音频" in h and "非音频" not in h:
                        continue
                    cols.append((ci, "input"))
                elif "缓存命中" in h:
                    # 同上：「缓存命中(非音频)」是主列，「缓存命中(音频)」跳过。
                    if "音频" in h and "非音频" not in h:
                        continue
                    cols.append((ci, "cache_read"))
                elif "输出" in h and "成本" not in h and "cost" not in hl:
                    cols.append((ci, "output"))
            if model_col is None:
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            current_model_name: str | None = None
            for row in table.data_rows():
                # rowspan 阶梯续行：条件列为空、条件文本出现在输入列位置
                # （豆包真实页第二阶梯行如 ['doubao-seed-2.0-pro', '', '输入长度 (32, 128]', ...]，
                # rowspan 已被 HTML 解析层填充到模型列，所以判定只看条件列与右邻）。
                # 此时价格列整体右移一格：原 ci 列的数据在 ci+1。
                shifted = False
                if band_col is not None:
                    band_cell = row[band_col] if band_col < len(row) else ""
                    next_cell = row[band_col + 1] if band_col + 1 < len(row) else ""
                    if not band_cell.strip() and "输入长度" in next_cell:
                        # 形态 A（真实页 rowspan）：模型列被填充、条件列为空、
                        # 条件文本出现在输入列位置 → 价格列整体右移一格。
                        shifted = True
                        band = _parse_context_band(next_cell)
                    else:
                        band = _parse_context_band(band_cell) if band_cell.strip() else None
                else:
                    band = None
                if band is not None and band_in_kilo_tokens:
                    # 「条件 千 token」表：数值 ×1000 换算成 token（阶梯与主行统一处理）
                    band = ContextBand(
                        min_input_tokens=band.min_input_tokens * 1000,
                        max_input_tokens=(
                            band.max_input_tokens * 1000
                            if band.max_input_tokens is not None
                            else None
                        ),
                    )
                model_cell = row[model_col] if model_col < len(row) else ""
                if not model_cell.strip() or (
                    _clean_model_name(model_cell).lower().find("doubao") < 0
                    and model_cell.strip()
                ):
                    # 模型列为空（形态 B：fixture 阶梯续行，条件列有值）→
                    # 沿用上一行的模型，价格列不右移。
                    if not model_cell.strip() and current_model_name:
                        model_name = current_model_name
                    else:
                        continue
                elif shifted:
                    # 形态 A：模型列被 rowspan 填充，价格列右移
                    candidate = _clean_model_name(model_cell)
                    if candidate and "doubao" in candidate.lower():
                        model_name = candidate
                        current_model_name = candidate
                    else:
                        model_name = current_model_name or ""
                    if not model_name:
                        continue
                else:
                    model_name = _clean_model_name(model_cell)
                    if not model_name or "doubao" not in model_name.lower():
                        continue
                    current_model_name = model_name
                model_key = model_name.lower().replace(" ", "-")
                has_fact = False
                for ci, comp in cols:
                    if shifted:
                        # 右移后：原列 ci 的数据在 ci+1（band 占据了 band_col+1 位置）
                        data_ci = ci + 1
                        if data_ci >= len(row):
                            continue
                        cell = row[data_ci]
                    else:
                        if ci >= len(row):
                            continue
                        cell = row[ci]
                    p = _parse_price_html(cell, default_currency="CNY")
                    if not p:
                        continue
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "doubao", model_name,
                        comp, billing, p, region=_region_for("doubao"),
                        context_band=band, service_tier=tier,
                    ))
                    has_fact = True
                if has_fact:
                    models.append(ModelProfile(
                        provider_id="doubao",
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
            warnings=_drift_warnings("doubao", facts),
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
            if line.startswith("## ") and "缓存" not in line:
                current_model = line[3:].strip()
                current_ctx = None
            elif line.startswith("| 模型") and current_model:
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
                                snapshot, ev.evidence_id, "doubao", current_model,
                                "input", "realtime", inp, region=_region_for("doubao"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "doubao", current_model,
                                "output", "realtime", out, region=_region_for("doubao"),
                            ))
                models.append(ModelProfile(
                    provider_id="doubao",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            elif line.startswith("| 类型") and current_model:
                rows, j = _split_table(lines, i)
                ev, ev_idx = _evidence_for_table(lines, i, j, snapshot, ev_idx, self.version, rows)
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 2:
                        tier = row[0].lower()
                        p = _parse_price(row[1])
                        if not p:
                            continue
                        if "读" in tier:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "doubao", current_model,
                                "cache_read", "realtime", p, region=_region_for("doubao"),
                            ))
                        elif "写" in tier:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "doubao", current_model,
                                "cache_write", "realtime", p, region=_region_for("doubao"),
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
            warnings=_drift_warnings("doubao", facts),
        )

