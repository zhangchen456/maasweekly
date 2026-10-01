"""Shared deterministic parsing helpers; moved verbatim without semantic version changes."""
from __future__ import annotations

import hashlib


import re


from decimal import Decimal, InvalidOperation


from ..base import (
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
            html_fragment=_with_heading_context(table, str(table)),
            table_index=idx,
        ))
    return result


def _with_heading_context(table, fragment: str) -> str:
    """表前置标题并入证据摘录（验收 P1-3：证据需含模型上下文）。

    Google 等页的模型名在表外 h2/h3/h4 标题里，表内只有金额与列名——
    摘录不含模型时无法独立核价。把表前最近一个标题文本包在摘录最前，
    标题与表之间最多 2 个块级元素（超过视为无关标题）。
    """
    try:
        heading = table.find_previous(["h1", "h2", "h3", "h4"])
        if heading is None:
            return fragment
        # 距离检查：文档行距（不同层级容器的标题与表不是 sibling，
        # 用 sourceline 差近似距离，差 < 30 行视为该表的章节标题）
        t_line = getattr(table, "sourceline", None)
        h_line = getattr(heading, "sourceline", None)
        if t_line and h_line and t_line - h_line > 30:
            return fragment
        text = heading.get_text(" ", strip=True)
        if not text or len(text) > 120:
            return fragment
        return f"<p>{text}</p>{fragment}"
    except Exception:  # noqa: BLE001
        return fragment


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
    - '[0,32K)' / '[32K,128K)' / '[32K+)'（glm FAQ）：K/M 缩写方括号区间
    """
    # qwen 形式：0<Token≤1M / 1M<Token≤32K（K/M 缩写）
    m = re.search(r"([\d.]+)\s*[<≤]\s*[Tt]oken\s*[<≤]\s*([\d.]+)\s*([KkMm]?)", text)
    if m:
        lo = _expand_km(m.group(1), m.group(3))
        hi = _expand_km(m.group(2), m.group(3))
        return ContextBand(min_input_tokens=lo, max_input_tokens=hi)
    # glm FAQ 形式：[0,32K) 闭开区间 / [32K,128K) / [32K+) 开区间（K/M 缩写）
    m = re.search(r"[\[(]\s*([\d.]+)\s*([KkMm]?)\s*(?:,\s*([\d.]+)\s*([KkMm]?)\s*[\])])?", text)
    if m and (m.group(3) is not None or "+" in text or text.rstrip().endswith(")")):
        lo = _expand_km(m.group(1), m.group(2))
        hi = _expand_km(m.group(3), m.group(4)) if m.group(3) is not None else None
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

