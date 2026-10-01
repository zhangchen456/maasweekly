"""qwen pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_QWEN = "qwen-2"

class QwenPricingExtractor:
    """解析通义千问（阿里云百炼）价格页（M6：真实 HTML 表格）。

    真实页（aliyun.com）Playwright 渲染后是多张表，表头含「模型ID」「输入单价（每百万Token）」
    「输出单价（每百万Token）」。行=模型+模式+输入长度阶梯。价格单元格 '24 元'，单位由表头标明。
    「单次请求的输入Token数」列含 `0<Token≤1M` 阶梯文本，映射 ContextBand。
    """

    version = _EXTRACTOR_VERSION_QWEN

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
        seen_keys: set[str] = set()
        for table in tables:
            if not table.rows:
                continue
            header = table.rows[0]
            flat = " ".join(header)
            # 只处理含「模型」列且含价格列的表（qwen 表头用「每百万 Token」不含「元」）
            if "模型" not in flat or not ("元" in flat or "单价" in flat or "价格" in flat):
                continue
            model_col = None
            band_col = None
            region_col = None
            cols: list[tuple[int, str]] = []
            for ci, h in enumerate(header):
                compact = h.replace(" ", "").lower()
                if compact.startswith("模型id") and model_col is None:
                    model_col = ci
                elif "部署范围" in h:
                    region_col = ci
                elif "输入token" in compact or "单次请求" in h:
                    band_col = ci
                elif "输入" in h and "单价" in h:
                    cols.append((ci, "input"))
                elif "输出" in h and "单价" in h:
                    cols.append((ci, "output"))
            if model_col is None:
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            for row in table.data_rows():
                if model_col >= len(row):
                    continue
                model_name = _clean_model_name(row[model_col].split(" ")[0])
                if not model_name or not model_name.lower().startswith("qwen"):
                    # 前缀精确匹配：千问页面上混排的 deepseek-* 等第三方模型
                    # 不属于本信源（deepseek 官网才是权威信源），跳过防跨
                    # provider 重复计价。
                    continue
                # 已下线模型：价格列明确标「已下线」，显式跳过（不依赖价格解析失败兜底）
                row_text = " ".join(row)
                if "已下线" in row_text:
                    continue
                model_key = model_name.lower().replace(" ", "-")
                band = None
                if band_col is not None and band_col < len(row):
                    band = _parse_context_band(row[band_col])
                # 部署范围 → region（与 PriceFact.region 既有值域 global/cn/us 对齐；
                # 无该列的表默认 cn）
                region = _region_for("qwen")
                if region_col is not None and region_col < len(row):
                    scope = row[region_col].strip()
                    region = _QWEN_SCOPE_REGION.get(scope, region)
                has_fact = False
                for ci, comp in cols:
                    if ci >= len(row):
                        continue
                    p = _parse_price_html(row[ci])
                    if not p:
                        continue
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "qwen", model_name,
                        comp, "realtime", p, region=region,
                        context_band=band,
                    ))
                    has_fact = True
                if has_fact and model_key not in seen_keys:
                    seen_keys.add(model_key)
                    models.append(ModelProfile(
                        provider_id="qwen",
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
            warnings=_drift_warnings("qwen", facts),
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
            # H2 = 模型节，排除「长上下文阶梯」这类子标题
            if line.startswith("## ") and "长上下文" not in line and "阶梯" not in line:
                current_model = line[3:].strip()
                current_ctx = None
            # 主表：模型 | 上下文窗口 | 输入 | 输出
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
                                snapshot, ev.evidence_id, "qwen", current_model,
                                "input", "realtime", inp, region=_region_for("qwen"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "qwen", current_model,
                                "output", "realtime", out, region=_region_for("qwen"),
                            ))
                models.append(ModelProfile(
                    provider_id="qwen",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            # 长上下文阶梯子表：输入长度 | 输入价格
            elif line.startswith("| 输入长度") and current_model:
                rows, j = _split_table(lines, i)
                ev, ev_idx = _evidence_for_table(lines, i, j, snapshot, ev_idx, self.version, rows)
                evidence.append(ev)
                for row in rows:
                    if len(row) >= 2:
                        band = _parse_context_band(row[0])
                        p = _parse_price(row[1])
                        if p and band:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "qwen", current_model, "input", "realtime", p,
                                region=_region_for("qwen"), context_band=band,
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
            warnings=_drift_warnings("qwen", facts),
        )

