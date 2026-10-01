"""glm pricing adapter: ContentSnapshot → ExtractionResult, no I/O."""
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

_EXTRACTOR_VERSION_GLM = "glm-2"

class GlmPricingExtractor:
    """解析智谱 GLM 价格页（glm-2：2026-09 改版后的卡片 + FAQ 结构）。

    真实页（open.bigmodel.cn/pricing，Playwright 渲染后）两个价格区：

    1. 卡片区（主通道）：每模型一张卡片，标题 .card-title，正文两种渲染——
       - table 卡（GLM-5.3/5.3-Flash）：行是 [label, value] 键值对
         （上下文/输入单价/输出单价/缓存命中/缓存存储）
       - field-group 卡（GLM-5.2/OCR/TTS）：.field-label + .field-value 对
         （OCR 用"输入价格/输出价格"；TTS 按万字符计价，非 token，跳过）
       折叠价取第一个（当前生效）：'0.8元 / M 0.4元 / M' → 0.8
    2. FAQ 区（兜底通道）：卡片只展示最新 5 个模型，其余模型（GLM-5V-Turbo/
       4.6V/4.6V-FlashX/4.5V/5.1 等）价格以文本形式在常见问题列表：
       'GLM-4.6V：输入[0,32K)1元/M·[32K,128K)2元/M，输出[0,32K)3元/M·[32K,128K)6元/M'
       解析为带 ContextBand 的分段计价 facts。"免费"模型与"套餐"（私有化年费）跳过。

    glm-1（旧版）：大表结构（表头行+数据表），模型×价格一行一模型。页面改版后
    该结构不复存在，保留 markdown fixture 路径供 M2/M4 回归。
    """

    version = _EXTRACTOR_VERSION_GLM

    # 卡片字段 label → 计费组件。TTS"单价"按万字符计价非 token，不在此表（跳过）
    _CARD_LABELS = {
        "输入单价": "input",
        "输出单价": "output",
        "输入价格": "input",
        "输出价格": "output",
        "缓存命中": "cache_read",
    }

    def extract(self, snapshot: ContentSnapshot) -> ExtractionResult:
        raw = snapshot.content
        if raw.lstrip().startswith(("<", "<!doctype", "<!DOCTYPE")):
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

    def _extract_html(self, snapshot: ContentSnapshot, html: str) -> ExtractionResult:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        # 促销价的原文标价带删除线（<span style="text-decoration:line-through">0.8元</span>0.4元），
        # 当前生效价是未删除线的折扣价——先移除删除线节点再取文本
        for node in soup.find_all("span", style=True):
            if "line-through" in node["style"]:
                node.decompose()
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        seen_keys: set[str] = set()

        def add_model_facts(model_name: str, comp_amounts: list[tuple[str, str]], ev: Evidence):
            """[(component, 价格原文)] → facts + model profile（有价格才建 model）。"""
            model_key = model_name.lower().replace(" ", "-")
            has_fact = False
            for comp, text in comp_amounts:
                p = _parse_price_html(text, default_currency="CNY")
                if not p:
                    continue
                facts.append(_make_fact(
                    snapshot, ev.evidence_id, "glm", model_name,
                    comp, "realtime", p, region=_region_for("glm"),
                ))
                has_fact = True
            if has_fact and model_key not in seen_keys:
                seen_keys.add(model_key)
                models.append(ModelProfile(
                    provider_id="glm",
                    model_key=model_key,
                    display_name=model_name,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=None,
                    evidence_id=ev.evidence_id,
                ))

        def make_faq_evidence(model_name: str, excerpt: str) -> Evidence:
            nonlocal ev_idx
            ev_idx += 1
            ex = excerpt[:200]
            return Evidence(
                evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                snapshot_id=snapshot.snapshot_id,
                locator_type="dom_selector",
                locator=f"faq:has-text('{model_name}')",
                excerpt=ex,
                excerpt_hash=hashlib.sha256(ex.encode()).hexdigest(),
                extractor_version=self.version,
            )

        # ---- 卡片区（table 卡 + field-group 卡）----
        for title_el in soup.select(".card-title"):
            model_name = _clean_model_name(title_el.get_text(strip=True))
            if not model_name or "glm" not in model_name.lower():
                continue
            # 卡片容器：向上找最近的「含价格结构且只含本卡 title」的祖先
            # （5.3 系 table 卡在 .card-body 内，5.2/OCR/TTS field-group 卡在 .service-card 内）
            card = None
            el = title_el
            for _ in range(8):
                el = el.parent
                if el is None or not hasattr(el, "select"):
                    break
                if not el.select(".field-list, table"):
                    continue
                if len(el.select(".card-title")) == 1:
                    card = el
                    break
            if card is None:
                continue
            # table 卡：行 = [label, value]
            pairs: list[tuple[str, str]] = []
            for table in card.find_all("table"):
                for tr in table.find_all("tr"):
                    cells = [c.get_text(separator=" ", strip=True) for c in tr.find_all(["td", "th"])]
                    if len(cells) >= 2:
                        pairs.append((cells[0], cells[1]))
            # field-group 卡：label + value
            if not pairs:
                for group in card.select(".field-group"):
                    label = group.select_one(".field-label")
                    value = group.select_one(".field-value")
                    if label and value:
                        pairs.append((label.get_text(strip=True), value.get_text(" ", strip=True)))
            comp_amounts = [
                (self._CARD_LABELS[label], value)
                for label, value in pairs if label in self._CARD_LABELS
            ]
            if not comp_amounts:
                continue
            ev_idx += 1
            excerpt = f"{model_name}: " + "; ".join(f"{l}={v}" for l, v in pairs)
            ev = Evidence(
                evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
                snapshot_id=snapshot.snapshot_id,
                locator_type="dom_selector",
                locator=f".card-title:has-text('{model_name}')",
                excerpt=excerpt,
                excerpt_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
                extractor_version=self.version,
            )
            evidence.append(ev)
            add_model_facts(model_name, comp_amounts, ev)

        # ---- FAQ 区（兜底：卡片未覆盖的旧模型）----
        # 行格式：'GLM-4.6V：输入[0,32K)1元/M·[32K,128K)2元/M，输出[0,32K)3元/M·[32K,128K)6元/M'
        # 或 'GLM-5.2：输入 8 元、缓存命中 2 元、输出 28 元'（无分段，多与卡片重复，仅补缺）
        faq_text = soup.get_text(" ", strip=True)
        faq_evs: dict[str, Evidence] = {}
        for m in re.finditer(
            r"(GLM-[A-Za-z0-9.\-]+)\s*[：:]\s*((?:(?!GLM-).){3,600}?)(?=GLM-|\Z)",
            faq_text,
        ):
            model_name = _clean_model_name(m.group(1))
            # desc 裁到首个 ？/问句边界：FAQ 下一问或页脚文本可能紧随价格行
            desc = re.split(r"[？?]", m.group(2))[0]
            if "套餐" in desc:
                continue  # 私有化年费，非 API 按量价格
            if model_name.lower().replace(" ", "-") in seen_keys:
                continue  # 卡片区已有（同源价格），跳过 FAQ 重复
            # 组件关键词 → 价格段：'输入[0,32K)6元/M·[32K+)8元' 或 '输入 8 元'
            simple: list[tuple[str, str]] = []
            banded = False
            for kw, comp in (("缓存命中", "cache_read"), ("输入", "input"), ("输出", "output")):
                # 分段价：[band]价格 序列（'元/M·'、'元 /' 等连接）
                seg_m = re.search(
                    kw + r"((?:\s*[\[(][\d,.KMkms+ ]*[\])]\s*[\d.]+\s*元\s*(?:/M|·|/|\s)*)+)",
                    desc,
                )
                if seg_m:
                    banded = True
                    for band_raw, amount in re.findall(r"([\[(][\d,.KMkms+ ]*[\])])\s*([\d.]+)\s*元", seg_m.group(1)):
                        cb = _parse_context_band(band_raw)
                        p = _parse_price_html(amount + "元", default_currency="CNY")
                        if cb and p:
                            if model_name not in faq_evs:
                                faq_evs[model_name] = make_faq_evidence(model_name, m.group(0))
                                evidence.append(faq_evs[model_name])
                            facts.append(_make_fact(
                                snapshot, faq_evs[model_name].evidence_id, "glm", model_name,
                                comp, "realtime", p, region=_region_for("glm"), context_band=cb,
                            ))
                else:
                    # 无分段简单价：'输入 8 元'
                    s_m = re.search(kw + r"\s*([\d.]+\s*元)", desc)
                    if s_m:
                        simple.append((comp, s_m.group(1)))
            if not banded and not simple:
                continue  # 无任何价格组件（免费模型行等）
            if banded:
                # 分段价路径：facts 已直接 append，补 model profile
                model_key = model_name.lower().replace(" ", "-")
                if model_name in faq_evs and model_key not in seen_keys:
                    seen_keys.add(model_key)
                    models.append(ModelProfile(
                        provider_id="glm",
                        model_key=model_key,
                        display_name=model_name,
                        model_class="flagship",
                        lifecycle_status="active",
                        context_window_tokens=None,
                        evidence_id=faq_evs[model_name].evidence_id,
                    ))
            elif simple:
                if model_name not in faq_evs:
                    faq_evs[model_name] = make_faq_evidence(model_name, m.group(0))
                    evidence.append(faq_evs[model_name])
                add_model_facts(model_name, simple, faq_evs[model_name])

        # ---- 表格回退（glm-1 结构兼容）----
        # 改版前的大表结构（一行一模型：模型名/上下文/输入/输出/缓存）。当前页面不会命中
        # （键值对小表首行无模型名），保留用于旧 fixture 回归与「智谱改回表格」的场景兜底。
        tables = _parse_html_tables(html)
        for table in tables:
            if not table.rows or table.header_rows > 0:
                continue
            first = table.rows[0]
            if len(first) < 4 or not any("glm" in (c or "").lower() for c in first):
                continue
            if not any("元" in (c or "") for c in first):
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            for row in table.rows:
                if len(row) < 4:
                    continue
                model_name = _clean_model_name(row[0].split(" ")[0])
                if not model_name or "glm" not in model_name.lower():
                    continue
                if model_name.lower().replace(" ", "-") in seen_keys:
                    continue  # 卡片/FAQ 通道已覆盖（同源价格，优先新通道）
                model_key = model_name.lower().replace(" ", "-")
                band = _parse_context_band(row[1]) if len(row) > 1 else None
                if band is not None and (band.max_input_tokens or 0) <= 2000:
                    # 旧表头明示「上下文 (千tokens)」，glm-1 未换算量纲（32 = 32K tokens）——
                    # 修正为 token 量纲，与 doubao/qwen 及 glm-2 FAQ 通道一致
                    band = ContextBand(
                        min_input_tokens=band.min_input_tokens * 1000,
                        max_input_tokens=band.max_input_tokens * 1000 if band.max_input_tokens is not None else None,
                    )
                has_fact = False
                for ci, comp in ((2, "input"), (3, "output"), (5, "cache_read")):
                    if ci >= len(row):
                        continue
                    p = _parse_price_html(row[ci], default_currency="CNY")
                    if not p:
                        continue
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "glm", model_name,
                        comp, "realtime", p, region=_region_for("glm"),
                        context_band=band,
                    ))
                    has_fact = True
                if has_fact and model_key not in seen_keys:
                    seen_keys.add(model_key)
                    models.append(ModelProfile(
                        provider_id="glm",
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
            warnings=_drift_warnings("glm", facts),
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
            # H2 = 模型节（排除非模型的小节标题，GLM 无子表）
            if line.startswith("## "):
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
                                snapshot, ev.evidence_id, "glm", current_model,
                                "input", "realtime", inp, region=_region_for("glm"),
                            ))
                        if out:
                            facts.append(_make_fact(
                                snapshot, ev.evidence_id, "glm", current_model,
                                "output", "realtime", out, region=_region_for("glm"),
                            ))
                models.append(ModelProfile(
                    provider_id="glm",
                    model_key=current_model.lower().replace(" ", "-"),
                    display_name=current_model,
                    model_class="flagship",
                    lifecycle_status="active",
                    context_window_tokens=current_ctx,
                    evidence_id=ev.evidence_id,
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
            warnings=_drift_warnings("glm", facts),
        )

