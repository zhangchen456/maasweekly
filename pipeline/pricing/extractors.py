"""SourceExtractor 实现（方案 §8.1）。

迁移自追浪 app-core-service-001 goals/extractors.py：去 blobstore（snapshot 直接携带 content）、
去 LLMFallbackGate（maasweekly 不做 LLM 兜底，确定性解析失败即 failed_source）。
解析逻辑逐行保留，adapter_version 不变，fixture 回归测试保证行为一致。

只消费 ContentSnapshot（从 blob_ref 取回原文），不联网。
每个厂商一个 Extractor，把官方价格页结构化成 ModelProfile + PriceFact + Evidence。

证据铁律：每个 PriceFact.evidence_id 必须指向一条 Evidence，
Evidence.locator 精确定位到原文中的来源（这里是 markdown 行号区间）。

P0 覆盖 OpenAI + DeepSeek 两家，验证「纵向事实 → 横向台账」的解析路径。
其他六家在 M4 补。
"""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation

from .base import (
    ContextBand,
    ContentSnapshot,
    Evidence,
    ExtractionResult,
    ModelProfile,
    PriceFact,
    TimeCondition,
    fact_key,
    stable_identity,
)

_EXTRACTOR_VERSION_OPENAI = "openai-1"
_EXTRACTOR_VERSION_DEEPSEEK = "deepseek-1"
_EXTRACTOR_VERSION_ANTHROPIC = "anthropic-1"
_EXTRACTOR_VERSION_GOOGLE = "google-1"
_EXTRACTOR_VERSION_KIMI = "kimi-1"
_EXTRACTOR_VERSION_GLM = "glm-1"
_EXTRACTOR_VERSION_DOUBAO = "doubao-2"
_EXTRACTOR_VERSION_QWEN = "qwen-2"

# 厂商固有区域：openai/anthropic/google 为 global（国际官方页），
# 其余五家为 cn（国内官方页）。extractor 内部只有 provider_id 无 source_key，
# 不查 registry，直接按 provider_id 取区域。
_PROVIDER_REGIONS: dict[str, str] = {
    "openai": "global",
    "anthropic": "global",
    "google": "global",
    "deepseek": "cn",
    "kimi": "cn",
    "glm": "cn",
    "doubao": "cn",
    "qwen": "cn",
}

# 千问价格页「服务部署范围」列值 → PriceFact.region 值域（global/cn/us）。
# 日本/欧盟暂无对应值域，归入 global（海外独立计价但非 us 官方口径）。
_QWEN_SCOPE_REGION: dict[str, str] = {
    "全球": "global",
    "国际": "global",
    "美国": "us",
    "日本": "global",
    "欧盟": "global",
}


def _region_for(provider_id: str) -> str:
    return _PROVIDER_REGIONS.get(provider_id, "cn")


def _evidence_id(snapshot_id: str, idx: int) -> str:
    return f"ev-{hashlib.sha256(f'{snapshot_id}:{idx}'.encode()).hexdigest()[:20]}"


def _parse_price(text: str) -> tuple[str, str, int] | None:
    """从 '$1.25 / 1M tokens' 或 '¥0.27 / 1M tokens' 解析出 (amount, currency, unit_quantity)。

    amount 归一为 Decimal 字符串（6 位小数，不带符号）。
    不支持的格式返回 None。
    """
    m = re.search(r"([\$¥])\s*([\d.]+)\s*/\s*(\d+)\s*[Mm]\s*tokens?", text)
    if not m:
        return None
    sym, num, qty = m.group(1), m.group(2), m.group(3)
    currency = "USD" if sym == "$" else "CNY"
    try:
        d = Decimal(num).quantize(Decimal("0.000001"))
    except InvalidOperation:
        return None
    return str(d), currency, int(qty) * 1_000_000


def _parse_tokens(text: str) -> int | None:
    """'400,000' → 400000；'128,000' → 128000。"""
    m = re.search(r"([\d,]+)", text.replace(" ", ""))
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def _parse_amount_only(text: str) -> str | None:
    """纯金额 '$1.25' → '1.250000'。"""
    m = re.search(r"[\$¥]\s*([\d.]+)", text)
    if not m:
        return None
    try:
        return str(Decimal(m.group(1)).quantize(Decimal("0.000001")))
    except InvalidOperation:
        return None


# ————————————— 真实官网价格解析（M6）—————————————


_PRICE_UNIT_PATTERNS = [
    # / MTok, / 1M tokens, / 百万 tokens, / 百万, / 1,000,000 tokens 等
    (re.compile(r"\$\s*([\d,.]+)\s*/\s*MTok", re.I), "USD"),
    (re.compile(r"\$\s*([\d,.]+)\s*/\s*1[,\s]?000[,\s]?000\s*tok", re.I), "USD"),
    (re.compile(r"\$\s*([\d,.]+)\s*/\s*1M\s*tok", re.I), "USD"),
    (re.compile(r"\$\s*([\d,.]+)\s*/\s*1k\s*call", re.I), "USD"),  # openai web search 按千次
    (re.compile(r"¥\s*([\d,.]+)\s*/\s*百万", re.I), "CNY"),
    (re.compile(r"¥\s*([\d,.]+)\s*/\s*1M\s*tok", re.I), "CNY"),
    (re.compile(r"([\d,.]+)\s*元\s*/\s*百万", re.I), "CNY"),
    (re.compile(r"([\d,.]+)\s*元\s*/\s*1M\s*tok", re.I), "CNY"),
    (re.compile(r"([\d,.]+)\s*元\s*/\s*千", re.I), "CNY"),  # 元/千 tokens
]


def _parse_price_html(text: str, *, default_unit: int = 1_000_000, default_currency: str | None = None) -> tuple[str, str, int] | None:
    """从真实官网 HTML 文本解析价格 → (amount, currency, unit_quantity)。

    支持格式（探查到的真实页面样式）：
    - '$10 / MTok' / '$10 / 1,000,000 tokens' / '$0.007'（无单位时用 default_unit）
    - '$1.50 through December 31, 2026'（含时效，取价格忽略时效文本）
    - '2.4 元/百万' / '¥0.27'
    - '$0.0045 / minute' 这类非 token 计价返回 None（跳过，不混入 token 价格表）

    amount 归一为 Decimal 字符串（6 位小数）。不支持的格式返回 None。
    default_unit：无显式单位时按此归一（真实页价格通常隐含 1M tokens）。
    default_currency：当传入时，纯数字单元格（如 doubao '6.00'，货币单位在表头标明）
    按此货币解析；不传则裸数字不认（避免误判模型名里的版本号）。
    """
    for pat, currency in _PRICE_UNIT_PATTERNS:
        m = pat.search(text)
        if m:
            num = m.group(1).replace(",", "")
            try:
                d = Decimal(num).quantize(Decimal("0.000001"))
            except InvalidOperation:
                continue
            # 元/千 → 1M 换算：amount × 1000
            if "千" in pat.pattern and "百" not in pat.pattern:
                d = d * Decimal(1000)
            # 1k calls 是按次计价，跳过（不是 token 价格）
            if "1k" in pat.pattern.lower() and "call" in pat.pattern.lower():
                return None
            return str(d), currency, default_unit
    # 裸价格 $X 或 ¥X 无单位：openai 表格价格常是裸 '$4.00'，隐含 1M tokens
    m = re.search(r"\$\s*([\d.]+)", text)
    if m:
        try:
            d = Decimal(m.group(1)).quantize(Decimal("0.000001"))
            return str(d), "USD", default_unit
        except InvalidOperation:
            pass
    m = re.search(r"¥\s*([\d.]+)", text)
    if m:
        try:
            d = Decimal(m.group(1)).quantize(Decimal("0.000001"))
            return str(d), "CNY", default_unit
        except InvalidOperation:
            pass
    # 数字 + 元（无单位斜杠）：doubao '9.0 元'、qwen '24 元'，单位由表头标明
    # 需排除 '100 万 Token'（免费额度非价格）这类——要求数字紧跟 元 且无"额度/免费"
    if "免费" not in text and "额度" not in text:
        m = re.search(r"([\d.]+)\s*元", text)
        if m:
            try:
                d = Decimal(m.group(1)).quantize(Decimal("0.000001"))
                return str(d), "CNY", default_unit
            except InvalidOperation:
                pass
    # 裸数字（无货币符号无"元"）：doubao 表 3+ 价格单元格是纯 '6.00'，
    # 货币单位 CNY 在表头 '元/百万token' 标明。仅在 default_currency 传入时启用，
    # 避免误判模型名版本号（openai/anthropic 不传，裸数字走上面的 $ 分支或返回 None）。
    # 排除 '-'、'暂不支持'、'免费' 等非价格占位。
    if default_currency and text.strip() and "免费" not in text and "支持" not in text:
        m = re.fullmatch(r"([\d.]+)", text.strip())
        if m:
            try:
                d = Decimal(m.group(1)).quantize(Decimal("0.000001"))
                return str(d), default_currency, default_unit
            except InvalidOperation:
                pass
    return None


def _evidence_for_html(
    snapshot: ContentSnapshot,
    ev_idx: int,
    table: HtmlTable,
    version: str,
) -> tuple[Evidence, int]:
    """为一张 HTML 表格装配 Evidence。locator 用 table 序号定位，excerpt 是表 HTML 片段。"""
    ev_idx += 1
    excerpt = table.html_fragment
    ev = Evidence(
        evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
        snapshot_id=snapshot.snapshot_id,
        locator_type="dom_selector",
        locator=f"table:nth-of-type({table.table_index + 1})",
        excerpt=excerpt,
        excerpt_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
        extractor_version=version,
    )
    return ev, ev_idx


def _clean_model_name(text: str) -> str:
    """清洗模型名：去掉括号备注（如 '( limited availability )'）、多余空白。

    真实页模型名常带状态标注，如 'Claude Mythos 5 ( limited availability )'，
    清洗成 'Claude Mythos 5' 才能生成稳定的 model_key。
    """
    s = text.strip()
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)  # 去括号备注
    s = re.sub(r"\s*\[[^\]]*\]\s*", " ", s)  # 去方括号标注
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    """从 start 行开始解析一个 Markdown 表格，返回 (rows, next_line)。

    rows 不含表头分隔行（|---|---|）。
    """
    rows: list[list[str]] = []
    i = start
    # 跳过表头分隔行
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        if re.match(r"^\|[\s:|-]+\|$", line):
            i += 1
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
        i += 1
    return rows, i


def _row_locator(start: int, end: int) -> str:
    return f"lines:{start}-{end}"


# ————————————— HTML 表格解析（M6 真实官网）—————————————


class HtmlTable:
    """一张 HTML 表格的结构化表示。

    rows 是二维列表，rowspan/colspan 已展开铺平（重复值填充到合并的单元格），
    便于按行列号直接取值。header_rows 是表头行数（th 或前几行），数据行从 header_rows 开始。
    html_fragment 是该表的原始 HTML 片段（用于 Evidence.excerpt），table_index 是在全文中的序号。
    """

    def __init__(self, rows: list[list[str]], header_rows: int, html_fragment: str, table_index: int) -> None:
        self.rows = rows
        self.header_rows = header_rows
        self.html_fragment = html_fragment
        self.table_index = table_index

    def data_rows(self) -> list[list[str]]:
        """返回非表头的数据行。"""
        return self.rows[self.header_rows:]

    def __repr__(self) -> str:
        return f"HtmlTable(idx={self.table_index}, rows={len(self.rows)}, header={self.header_rows})"


def _strip_zero_width(text: str) -> str:
    """去除零宽字符（U+200B/200C/200D/FEFF）和多余空白。

    火山引擎/阿里云文档页的 td 文本末尾常带零宽空格（​），导致
    '模型名称' != '模型名称​'、'6.00' 解析失败。统一在这里清掉。
    """
    return re.sub(r"[​‌‍﻿]", "", text).strip()


def _safe_span(val) -> int:
    """colspan/rowspan 容错解析：'2' / '\"2\"' / '\\\"2\\\"' / 非数字 → int，否则 1。

    真实页偶有属性值带转义引号（渲染残留），int() 会抛错。取数字部分，无则 1。
    """
    if val is None:
        return 1
    m = re.search(r"\d+", str(val))
    return int(m.group()) if m else 1


def _parse_html_tables(html: str) -> list[HtmlTable]:
    """解析 HTML 所有 <table>，rowspan/colspan 展开。

    用 BeautifulSoup。rowspan/colspan 是 HTML 表格的难点（deepseek 价格表靠它
    做行列嵌套），这里把合并单元格的值复制填充到展开后的每个格子，让上层按
    行列号直接取值即可。
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    result: list[HtmlTable] = []
    for idx, table in enumerate(soup.find_all("table")):
        rows_raw = table.find_all("tr")
        if not rows_raw:
            continue
        # 先建一个可写的二维网格，处理 rowspan/colspan
        grid: list[list[str | None]] = [[None] * 32 for _ in range(len(rows_raw) * 2)]  # 预留展开空间
        max_col = 0
        # 跟踪每行实际写入位置，处理 colspan 跳过已占用的格子
        occupied: list[set[int]] = [set() for _ in range(len(rows_raw) * 2)]
        for r_idx, tr in enumerate(rows_raw):
            cells = tr.find_all(["td", "th"])
            c_idx = 0
            for cell in cells:
                # 跳过被上方 rowspan 占用的列
                while c_idx in occupied[r_idx]:
                    c_idx += 1
                text = cell.get_text(separator=" ", strip=True)
                text = _strip_zero_width(text)  # 去零宽空格（火山/阿里页 td 末尾常带 ​）
                colspan = _safe_span(cell.get("colspan", 1))
                rowspan = _safe_span(cell.get("rowspan", 1))
                for dr in range(rowspan):
                    for dc in range(colspan):
                        rr = r_idx + dr
                        if rr >= len(grid):
                            grid.extend([[None] * 32 for _ in range(8)])
                            occupied.extend([set() for _ in range(8)])
                        while c_idx + dc >= len(grid[rr]):
                            grid[rr].extend([None] * 8)
                        grid[rr][c_idx + dc] = text
                        occupied[rr].add(c_idx + dc)
                        max_col = max(max_col, c_idx + dc)
                c_idx += colspan
        # 表头行数：前若干行若全是 th 或含 th 算表头
        header_rows = 0
        for r_idx, tr in enumerate(rows_raw):
            if tr.find("th") or all(c.name == "th" for c in tr.find_all(["td", "th"])):
                header_rows = r_idx + 1
        # 收成二维 list，裁剪到实际列数
        rows = []
        for r in grid[: len(rows_raw)]:
            row = [c if c is not None else "" for c in r[: max_col + 1]]
            if any(c.strip() for c in row):
                rows.append(row)
        result.append(HtmlTable(
            rows=rows,
            header_rows=header_rows,
            html_fragment=str(table),
            table_index=idx,
        ))
    return result


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
                model_cols.append((ci, cell.strip()))
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
            tc = TimeCondition(period=period_enum, tz="Asia/Shanghai", schedule=period_label) if period_enum else None
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


# ————————————— 中文页厂商 Extractor —————————————


def _evidence_for_table(lines, i, j, snapshot, ev_idx, version, rows=None):
    """装配一张子表/主表对应的 Evidence，返回 (ev, next_idx)。"""
    ev_idx += 1
    excerpt = " | ".join(rows[0]) if rows else lines[i].strip()
    ev = Evidence(
        evidence_id=_evidence_id(snapshot.snapshot_id, ev_idx),
        snapshot_id=snapshot.snapshot_id,
        locator_type="markdown_block",
        locator=_row_locator(i + 1, j),
        excerpt=excerpt,
        excerpt_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
        extractor_version=version,
    )
    return ev, ev_idx


def _drift_warnings(provider_id: str, facts: list) -> list[str]:
    """facts 为空时产出结构漂移告警。

    页面结构变化（表头改版/JS 未渲染/内容下线）导致确定性解析零产出时，
    不静默返回空结果，而是附 structure_drift 告警。该告警触发：
    - worker 把 warning 落到 source_run.errors（诊断可观测）
    - LLMFallbackGate.should_fallback 判定需 LLM 兜底（§8.2）
    - run 终态 partial（该 provider missing，不编造 fact）
    """
    return [f"structure_drift:{provider_id} 未匹配到价格表结构"] if not facts else []


class GlmPricingExtractor:
    """解析智谱 GLM 价格页（M6：真实 HTML 表格）。

    真实页（open.bigmodel.cn/pricing）Playwright 渲染后有多套表：
    - 表 0 是表头行（模型名称/输入单价/输出单价/缓存命中），表 1 是紧邻的数据表
      （header_rows=0，全部行是数据）。列位置固定：[0]模型 [2]输入 [3]输出 [5]缓存命中。
      价格 '8元'、'0.4元 0.8元'（带折扣取第一个=当前生效）、'免费'/'限时免费'跳过。
      第二列 '输入长度 [0, 32)' → ContextBand，'1M'/'200K' → 上下文窗口。
    - 表 3+ 是旧版价格表（GLM-4-Plus 等），价格 '¥X / M Tokens'，用 header 列映射。
    """

    version = _EXTRACTOR_VERSION_GLM

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
        # 表 1 类数据表（无表头，header_rows=0，含 GLM 模型名 + 元价格）
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
                model_key = model_name.lower().replace(" ", "-")
                # 第二列：输入长度阶梯或上下文窗口
                band = _parse_context_band(row[1]) if len(row) > 1 else None
                has_fact = False
                # 列 2=输入 3=输出 5=缓存命中
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
        # 旧版表（¥X / M Tokens，有表头）
        for table in tables:
            if not table.rows or table.header_rows == 0:
                continue
            header = table.rows[0]
            flat = " ".join(header)
            if "glm" not in flat.lower() and "model" not in flat.lower():
                # 数据行首列含 GLM 才处理
                if not table.rows[0] or not any("glm" in (c or "").lower() for c in table.rows[0]):
                    continue
            model_col = None
            cols: list[tuple[int, str]] = []
            for ci, h in enumerate(header):
                hl = h.lower()
                if ("模型" in h or "model" in hl or "product" in hl) and model_col is None:
                    model_col = ci
                elif ("输入" in h or "input" in hl or "price" in hl) and "缓存" not in h:
                    cols.append((ci, "input"))
                elif "输出" in h or "output" in hl:
                    cols.append((ci, "output"))
            if model_col is None:
                continue
            ev, ev_idx = _evidence_for_html(snapshot, ev_idx, table, self.version)
            evidence.append(ev)
            for row in table.data_rows():
                if model_col >= len(row):
                    continue
                model_name = _clean_model_name(row[model_col].split(" ")[0])
                if not model_name or "glm" not in model_name.lower():
                    continue
                model_key = model_name.lower().replace(" ", "-")
                has_fact = False
                for ci, comp in cols:
                    if ci >= len(row):
                        continue
                    p = _parse_price_html(row[ci])
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
        # Kimi 渲染后 HTML 含 rows:[[ 标志（JS bundle 表格数据）
        if "rows:[[" in raw:
            return self._extract_html(snapshot, raw)
        return self._extract_markdown(snapshot, raw)

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
        tables = _parse_html_tables(html)
        models: list[ModelProfile] = []
        facts: list[PriceFact] = []
        evidence: list[Evidence] = []
        ev_idx = 0
        for table in tables:
            if not table.rows:
                continue
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
                        comp, "realtime", p, region=_region_for("doubao"),
                        context_band=band,
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


# ————————————— 英文国际页厂商 Extractor —————————————


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
            cols: list[tuple[int, str]] = []
            for ci, h in enumerate(header):
                hl = h.lower()
                if "model" in hl and model_col is None:
                    model_col = ci
                if "base input" in hl:
                    cols.append((ci, "input"))
                elif "cache hits" in hl or "cache read" in hl or ("cache" in hl and "refresh" in hl):
                    cols.append((ci, "cache_read"))
                elif "cache write" in hl:
                    cols.append((ci, "cache_write"))
                elif "output" in hl:
                    cols.append((ci, "output"))
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
                for ci, comp in cols:
                    if ci >= len(row):
                        continue
                    p = _parse_price_html(row[ci])
                    if not p:
                        continue
                    facts.append(_make_fact(
                        snapshot, ev.evidence_id, "anthropic", model_name,
                        comp, "realtime", p, region=_region_for("anthropic"),
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
            html_frag = str(table)
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


# ————————————— 工厂 —————————————

_EXTRACTORS: dict[str, object] = {
    "openai:pricing": OpenAIPricingExtractor(),
    "anthropic:pricing": AnthropicPricingExtractor(),
    "google:pricing": GooglePricingExtractor(),
    "deepseek:pricing": DeepSeekPricingExtractor(),
    "kimi:pricing": KimiPricingExtractor(),
    "glm:pricing": GlmPricingExtractor(),
    "doubao:pricing": DoubaoPricingExtractor(),
    "qwen:pricing": QwenPricingExtractor(),
}


def get_extractor(source_key: str) -> object | None:
    """按 source_key 取适配器。M4 扩展至八家厂商。"""
    return _EXTRACTORS.get(source_key)


# ————————————— 内部装配 —————————————


def _make_fact(
    snapshot: ContentSnapshot,
    evidence_id: str,
    provider_id: str,
    model_display: str,
    component: str,
    billing_mode: str,
    parsed: tuple[str, str, int],
    *,
    region: str,
    context_band: ContextBand | None = None,
    time_condition: TimeCondition | None = None,
) -> PriceFact:
    amount, currency, unit_quantity = parsed
    model_key = model_display.lower().replace(" ", "-")
    identity = stable_identity(
        provider_id=provider_id,
        model_key=model_key,
        component=component,
        region=region,
        billing_mode=billing_mode,
        service_tier="standard",
        context_band=context_band,
        time_condition=time_condition,
    )
    return PriceFact(
        fact_key=fact_key(identity),
        provider_id=provider_id,
        model_key=model_key,
        component=component,  # type: ignore[arg-type]
        billing_mode=billing_mode,  # type: ignore[arg-type]
        amount=amount,
        currency=currency,
        unit_quantity=unit_quantity,
        unit_name="token",
        region=region,
        service_tier="standard",
        context_band=context_band,
        time_condition=time_condition,
        effective_at=None,
        observed_at=snapshot.fetched_at,
        evidence_id=evidence_id,
    )


def _parse_context_band(text: str) -> ContextBand | None:
    """价格行内输入长度阶梯 → ContextBand。支持多种真实页格式：

    - '0–272,000 tokens' / '0-272000'：闭区间
    - '272,001+ tokens'：开区间（max=None）
    - '0<Token≤1M' / '0<Token≤32K'（qwen）：闭区间，K/M 缩写展开
    - '[0, 1024]' / '[0,1024]'（doubao）：方括号闭区间
    """
    # qwen 形式：0<Token≤1M / 1M<Token≤32K（K/M 缩写）
    m = re.search(r"([\d.]+)\s*[<≤]\s*[Tt]oken\s*[<≤]\s*([\d.]+)\s*([KkMm]?)", text)
    if m:
        lo = _expand_km(m.group(1), m.group(3))
        hi = _expand_km(m.group(2), m.group(3))
        return ContextBand(min_input_tokens=lo, max_input_tokens=hi)
    # doubao 形式：[0, 1024] 闭区间 / (32, 128] 半开区间（阶梯续行）
    m = re.search(r"[\[(]\s*([\d,]+)\s*,\s*([\d,]+)\s*[\])]", text)
    if m:
        return ContextBand(
            min_input_tokens=int(m.group(1).replace(",", "")),
            max_input_tokens=int(m.group(2).replace(",", "")),
        )
    # 通用区间形式
    m = re.search(r"([\d,]+)\s*[–\-]\s*([\d,]+)", text)
    if m:
        return ContextBand(
            min_input_tokens=int(m.group(1).replace(",", "")),
            max_input_tokens=int(m.group(2).replace(",", "")),
        )
    # 开区间形式
    m = re.search(r"([\d,]+)\s*\+", text)
    if m:
        return ContextBand(
            min_input_tokens=int(m.group(1).replace(",", "")),
            max_input_tokens=None,
        )
    return None


def _expand_km(num: str, suffix: str) -> int:
    """'1.5' + 'K' → 1500，'2' + 'M' → 2000000。无后缀原样取整。"""
    val = float(num)
    if suffix:
        s = suffix.lower()
        if s == "k":
            val *= 1_000
        elif s == "m":
            val *= 1_000_000
    return int(val)
