"""kimi pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_KIMI = "kimi-3"

class KimiPricingExtractor:
    """解析 Kimi（Moonshot）价格页（M6：真实 JS bundle 数据）。

    Kimi 文档站用 Mintlify 框架，价格不在 <table> 而是内联在 JS bundle 的
    结构化对象里：``rows:[[`kimi-k3`,`1M tokens`,`¥2.00`,`¥20.00`,`¥100.00`,`1,048,576 tokens`]]``
    列序固定：[0]模型 [1]计费单位 [2]输入(缓存命中) [3]输入(缓存未命中) [4]输出 [5]上下文窗口。
    → [2]cache_read, [3]input, [4]output。

    模型分散在多个子页（chat-k3/chat-k27-code/chat-k26...），单页只有 1-2 个模型。
    KimiProvider 在 fetch 内部抓主页提取子页链接、逐个渲染子页、合成一个含全部
    子页 rows 的 HTML snapshot；本 extractor 从拼接 HTML 里正则提取所有 rows 块。
    多行 rows（``[[...],[...]]``，一个子页含多模型）用递归正则展开。
    """

    version = _EXTRACTOR_VERSION_KIMI

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        raw = snapshot.content
        if "<table" in raw:
            return self._extract_tables(snapshot, raw)
        # Kimi 渲染后 HTML 含 rows:[[ 标志（JS bundle 表格数据）
        if "rows:[[" in raw:
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

    def _extract_tables(self, snapshot, html):
        models, facts, evidence = [], [], []
        ev_idx = 0
        for table in _parse_html_tables(html):
            header = table.rows[0]
            if not any("缓存未命中" in h for h in header):
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            for row in table.data_rows():
                name = _clean_model_name(row[0])
                if not name.startswith(("kimi-", "moonshot-")):
                    continue
                for ci, label in enumerate(header):
                    comp, tc = None, None
                    if "缓存写入" in label:
                        comp = "cache_write"
                        duration = "1h" if "1h" in label else "5m"
                        tc = TimeCondition(period="cache_write_" + duration, tz="UTC", schedule=duration)
                    elif "缓存未命中" in label:
                        comp = "input"
                    elif "缓存命中" in label:
                        comp = "cache_read"
                    elif "输出" in label:
                        comp = "output"
                    if not comp or ci >= len(row):
                        continue
                    price = _parse_price_html(row[ci])
                    if price:
                        facts.append(_make_fact(snapshot, ev.evidence_id, "kimi", name, comp,
                            "realtime", price, region=_region_for("kimi"), time_condition=tc))
                models.append(ModelProfile(provider_id="kimi", model_key=name,
                    display_name=name, model_class="flagship", lifecycle_status="active",
                    context_window_tokens=_parse_tokens(row[-1]), evidence_id=ev.evidence_id))
        return ExtractionResult(snapshot_id=snapshot.snapshot_id, extractor_version=self.version,
            models=models, price_facts=facts, evidence=evidence, warnings=_drift_warnings("kimi", facts))

    def _extract_html(self, snapshot: ContentSnapshot, html: str) -> ExtractionResult:
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        seen_keys: set[str] = set()
        # 提取所有 rows:[[...]] 块（含多行 [[a,b],[c,d]]）
        # 匹配 rows:[[ 到对应 ]] —— 用非贪婪匹配到第一个 ]] 可能截断多行，
        # 改为匹配 rows:[[ 后逐个 ] 直至 ]] 结束。简单稳健做法：匹配 rows:[[ 之后的
        # 反引号单元格序列到 ]] 之间，允许中间出现 ],[
        for m in re.finditer(r"rows:\[\[(.*?)\]\]", html, re.S):
            block = m.group(1)
            # 把 block 按 ],[ 分割成多行，每行是一个 [cell,cell,...] 或 cell,cell,...
            # 反引号字符串才是数据单元格
            cells = re.findall(r"`([^`]*)`", block)
            # 按 6 列一组切（kimi 固定 6 列）；多余的上下文窗口列丢弃不影响
            COLS = 6
            for i in range(0, len(cells) - COLS + 1, COLS):
                row = cells[i : i + COLS]
                if len(row) < 5:
                    continue
                # 只处理 kimi 模型行（首列含 kimi/moonshot）
                if not row[0] or ("kimi" not in row[0].lower() and "moonshot" not in row[0].lower()):
                    continue
                model_name = _clean_model_name(row[0])
                model_key = model_name.lower().replace(" ", "-")
                ev_idx += 1
                ev = Evidence(
                    evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                    snapshot_id=snapshot.snapshot_id,
                    locator_type="json_pointer",
                    locator=f"rows[{i//COLS}]",
                    excerpt=f"rows:[[`{'`,`'.join(row)}`]]",
                    excerpt_hash=hashlib.sha256(f"rows:[[`{'`,`'.join(row)}`]]".encode()).hexdigest(),
                    extractor_version=self.version,
                )
                evidence.append(ev)
                has_fact = False
                # [2]=缓存命中→cache_read, [3]=缓存未命中→input, [4]=输出→output
                for ci, comp in ((2, "cache_read"), (3, "input"), (4, "output")):
                    p = _parse_price_html(row[ci])
                    if not p:
                        continue
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "kimi", model_name,
                        comp, "realtime", p, region=_region_for("kimi"),
                    ))
                    has_fact = True
                if has_fact and model_key not in seen_keys:
                    seen_keys.add(model_key)
                    models.append(ModelProfile(
                        provider_id="kimi",
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
            warnings=_drift_warnings("kimi", facts),
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
            # H2 = 模型节，排除「缓存」子标题（它属于上一个模型的缓存价格小节）
            if line.startswith("## ") and "缓存" not in line:
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
                                snapshot, ev.evidence_id, "kimi", current_model,
                                "input", "realtime", inp, region=_region_for("kimi"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "kimi", current_model,
                                "output", "realtime", out, region=_region_for("kimi"),
                            ))
                models.append(ModelProfile(
                    provider_id="kimi",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
                ))
                i = j
                continue
            # 缓存子表：类型 | 价格
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
                                snapshot, ev.evidence_id, "kimi", current_model,
                                "cache_read", "realtime", p, region=_region_for("kimi"),
                            ))
                        elif "写" in tier:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "kimi", current_model,
                                "cache_write", "realtime", p, region=_region_for("kimi"),
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
            warnings=_drift_warnings("kimi", facts),
        )

