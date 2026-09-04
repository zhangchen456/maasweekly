#!/usr/bin/env python3
"""diff 行级降噪与语义化工具，供 sync-diff-to-site.py / extract-live-events.py 共用。

三层处理：
1. is_noise_line(line)     —— 判定无信息量的行（时间戳/JSON键值/分页/UI文本/纯数字）
2. pair_lines(added, removed) —— 同前缀的 add/remove 行合并为 "X 旧→新" 单条变化
3. classify_source(entry)  —— 信源级分类：substantive（有实质变化）/ jitter（常规抖动）

判定原则：宁可漏过滤（保留可疑行）也不错杀（丢真实变化）——本模块只处理
结构上可枚举的噪声，语义级噪声留给人工或后续 LLM 层。
"""
import re

# ---------------------------------------------------------------------------
# 行级噪声判定
# ---------------------------------------------------------------------------

# 时间戳行：更新时间：xxx / Last updated: xxx / 2026.09.03 21:38:27
NOISE_TIMESTAMP = re.compile(
    r"^(?:最近更新时间|更新时间|最后更新)[:：]|"
    r"last\s+updated[:：]?|"
    r"^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\s+\d{1,2}:\d{2}"
)

# JSON 键值行（HuggingFace 等快照每日字段抖动）："_id": "xxx" / "downloads": 137
NOISE_JSON_FIELD = re.compile(r'^\s*"[^"]+"\s*:\s*')

# 分页/计数文本：11 of 314 models / 693/693 | Overall / showing 1-20 of 500
NOISE_PAGINATION = re.compile(
    r"^\d+\s*(?:of|/)\s*\d+\b|"
    r"showing\s+\d+[-–]\d+\s+of\s+\d+"
)

# UI 文本：-展开更多 N 个模型 / Show all details / 展开全部
NOISE_UI_TEXT = re.compile(
    r"^[-–]?\s*(展开更多|收起|展开全部|show\s+(?:all|more|less)|hide\b)|"
    r"\bshow all details\b"
)

# 拼接词块：SPA 页面把多个厂商名/标签拼成一行。判据是驼峰边界计数
# （实测噪声行 ≥5 个，真实模型 ID / 标题 ≤3 个）
NOISE_CAMEL_BOUNDARY = re.compile(r"[a-z](?=[A-Z])")


def _is_concat_block(s: str) -> bool:
    return len(NOISE_CAMEL_BOUNDARY.findall(s)) >= 5 and " " not in s.strip()

# 纯数字/百分比/空白行（脱离上下文无意义）
NOISE_NUMERIC = re.compile(r"^[\s\d.,%±+\-–—:|/¥$€£]+$")

# "X 小时/天前" 相对时间
NOISE_RELATIVE_TIME = re.compile(r"^\d+\s*(?:小时|分钟|天|日|周|月|年)(?:前|后)")

# 阅读时长/作者署名类：13 min read / By Nick Galloway • 3-minute read
NOISE_BYLINE = re.compile(
    r"^\d+[-\s]?(?:min|minute|分钟).*(?:read|阅读|读完)|"
    r"^by\s+[\w\s.•·]+(?:•|\s)\s*\d"
)

# 日期碎片行：Apr 30, 2026 / Jul 30, 2026Announcements...
NOISE_DATE_STUB = re.compile(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s*\d{4}", re.I)

# 模型 ID / 实质内容特征（用于"择优预览"）：org/Model-Name 或已知模型命名风格
MODEL_ID = re.compile(r"[A-Za-z][\w.\-]*/[\w.\-]+|(?<![A-Za-z])[a-z]+(?:-[a-z0-9.]+){1,6}(?![A-Za-z])")
# 价格模式：$10 / Input MTok / ¥xxx 元/百万 / 0.0008 /M
PRICE_PATTERN = re.compile(r"[¥$€£]\s?[\d,.]+|元/百万|/MTok|per\s+million|/\s*M\b", re.I)


def is_noise_line(line: str) -> bool:
    """判定一行 diff 是否为结构噪声。"""
    s = line.strip()
    if not s:
        return True
    if (NOISE_TIMESTAMP.search(s) or NOISE_JSON_FIELD.match(s)
            or NOISE_PAGINATION.search(s) or NOISE_UI_TEXT.search(s)
            or _is_concat_block(s)
            or NOISE_NUMERIC.match(s) or NOISE_RELATIVE_TIME.match(s)
            or NOISE_BYLINE.search(s) or NOISE_DATE_STUB.match(s)):
        return True
    return False


def has_signal(line: str) -> bool:
    """一行是否携带可读信号：含模型 ID、价格模式、中文说明文字或足够长的英文词组。"""
    s = line.strip()
    if is_noise_line(s):
        return False
    if MODEL_ID.search(s) or PRICE_PATTERN.search(s):
        return True
    # 中文内容（公告标题等）
    if re.search(r"[一-鿿]{4,}", s):
        return True
    # 较长的英文说明（完整的公告标题而非碎片）
    if len(re.findall(r"[A-Za-z]{3,}", s)) >= 3 and len(s) > 20:
        return True
    return False


# ---------------------------------------------------------------------------
# 语义化转写：把机器格式的粘连行翻译成可读文本
# ---------------------------------------------------------------------------

# LMArena 排行榜快照行："claude-fable-5.1-max1504±11" / "4Bytedancedreamina-seedance-2.5-720p1478±10"
# 结构是 [排名]实体名 + 分数[±置信区间]，实体名与分数粘连（页面表格文本化产物）
# LMArena 排行榜快照行："claude-fable-51507±5" / "4Bytedancedreamina-seedance-2.5-720p1478±10"
# 结构是 [排名]实体名 + 4位Elo分数[±置信区间][+胜/-负]，实体名与分数粘连（页面表格文本化产物）。
# 切分依据：Elo 分数恒为 4 位（约 1400-1700），固定 4 位 + 惰性实体名即可消歧
# （否则 claude-fable-5|1507 与 claude-fable-51|507 两种切分都合法）。
LMARENA_LINE = re.compile(
    r"^(?:(\d{1,3}))?"
    r"([a-z][\w.\-]*?(?:\s*\(codex-harness\))?)"
    r"\s*(\d{4})"
    r"([±][\d.]+)?"
    r"(?:([+\-][\d]+)/([+\-][\d]+))?$",
    re.I,
)
# HuggingFace 快照行：模型 id + downloads/likes 计数
HF_LINE = re.compile(r'^"?(downloads|likes)"?:?\s*"?(\d+)"?,?$')


def humanize_line(line: str) -> str:
    """尝试把机器格式行转写为人话；不匹配已知格式时原样返回。

    "claude-fable-51507±5" -> "claude-fable-5: 1507±5"
    "4Bytedancedreamina-seedance-2.5-720p1478±10" -> "bytedancedreamina-seedance-2.5-720p: 1478±10 (第4名)"
    """
    s = _split_leading_rank(line)
    m = LMARENA_LINE.match(s)
    if m:
        rank, name, score, ci, up, down = m.groups()
        out = f"{name}: {score}{ci or ''}"
        if up and down:
            out += f" ({up}/{down})"
        if rank:
            out += f" · 第{rank}名"
        return out
    m = HF_LINE.match(s)
    if m:
        return f"{m.group(1)}: {m.group(2)}"
    return line.strip()


# ---------------------------------------------------------------------------
# add/remove 成对合并
# ---------------------------------------------------------------------------

def _split_leading_rank(line: str) -> str:
    """去掉行首的排名数字（LMArena 快照行 '4Bytedance...' 是表格拼接产物）。"""
    return re.sub(r"^\d{1,3}(?=[A-Za-z一-鿿])", "", line.strip())


def _extract_key(line: str, min_len: int = 4) -> str:
    """提取行的"实体键"：优先模型 ID（org/name 或 kebab-case），否则行首连续词。

    用于配对：LMArena 的 "claude-fable-51507±5" vs "claude-fable-51508±5"
    实体键都是 "claude-fable"，视为同一实体的分数变化。
    """
    s = _split_leading_rank(line)
    m = MODEL_ID.search(s)
    if m:
        return m.group(0).lower()
    # 行首实体（中文公告标题去掉【】段落标记）
    head = re.split(r"[\d±|:：,，.。]", s, maxsplit=1)[0].strip("【】[] ")
    if len(head) >= min_len:
        return head.lower()
    return ""


def pair_lines(added: list, removed: list, max_pairs: int = 40):
    """把同实体键的新增/删除行合并为变化条目。

    返回 (pairs, residual_added, residual_removed)：
      pairs: [{key, before, after}]  —— 实体旧值→新值
      residual_*: 无法配对的行（保持原 diff 展示）
    """
    removed_by_key = {}
    for l in removed:
        k = _extract_key(l)
        if k:
            removed_by_key.setdefault(k, []).append(l)

    pairs, residual_added, residual_removed = [], [], []
    used_removed = set()
    added_keys: list = []  # [line, key, matched_removed_line]
    for l in added:
        added_keys.append([l, _extract_key(l), None])
    for item in added_keys:
        k = item[1]
        if k and k in removed_by_key:
            for idx, r in enumerate(removed_by_key[k]):
                if (k, idx) not in used_removed:
                    item[2] = r
                    used_removed.add((k, idx))
                    break
    for l, k, matched in added_keys:
        if matched is not None:
            pairs.append({"key": k, "before": matched, "after": l})
        else:
            residual_added.append(l)

    matched_removed = {id(r) for _, _, r in added_keys if r is not None}
    for k, lines in removed_by_key.items():
        for l in lines:
            if id(l) not in matched_removed:
                residual_removed.append(l)
    # 没提取到键的 removed 行也要保留
    removed_with_key = {l for lines in removed_by_key.values() for l in lines}
    for l in removed:
        if l not in removed_with_key:
            residual_removed.append(l)

    return pairs[:max_pairs], residual_added, residual_removed


# ---------------------------------------------------------------------------
# 信源级分类
# ---------------------------------------------------------------------------

def classify_source(entry: dict) -> str:
    """判定信源变化类型。

    substantive: 过滤噪声后仍有携带信号的行
    jitter:      过滤后为空（纯常规抖动），页面折叠展示
    """
    added = [l for l in (entry.get("added_lines") or []) if not is_noise_line(l)]
    removed = [l for l in (entry.get("removed_lines") or []) if not is_noise_line(l)]
    for l in added + removed:
        if has_signal(l):
            return "substantive"
    # 过滤后有剩余行但都不含强信号：内容存在但价值低，归为 jitter
    return "jitter"


def filter_and_pair(entry: dict) -> dict:
    """对单个 changed 信源做降噪 + 配对，返回增强后的条目。

    新增字段：
      kind: "substantive" | "jitter"
      pairs: [{key, before, after}]
      added_lines / removed_lines: 过滤噪声后的残留行
      signal_preview: 第一条携带信号的行（供卡片摘要用）
    """
    added = [l for l in (entry.get("added_lines") or []) if not is_noise_line(l)]
    removed = [l for l in (entry.get("removed_lines") or []) if not is_noise_line(l)]

    pairs, added, removed = pair_lines(added, removed)
    # 丢弃"值未变"的配对（如 LMArena 排名变化但 Elo 分数相同），零信息量
    pairs = [p for p in pairs if p["before"] != p["after"]]
    kind = "substantive" if any(has_signal(l) for l in added + removed) or \
        any(has_signal(p["before"]) or has_signal(p["after"]) for p in pairs) else "jitter"

    signal = ""
    for l in added:
        if has_signal(l):
            signal = l
            break
    if not signal and pairs:
        for p in pairs:
            if has_signal(p["after"]) or has_signal(p["before"]):
                signal = p["after"] or p["before"]
                break

    out = dict(entry)
    out["kind"] = kind
    out["pairs"] = pairs
    out["added_lines"] = added
    out["removed_lines"] = removed
    out["signal_preview"] = signal
    # 保留原始计数供参考
    out["raw_added_count"] = entry.get("added_count", len(entry.get("added_lines") or []))
    out["raw_removed_count"] = entry.get("removed_count", len(entry.get("removed_lines") or []))
    out["added_count"] = len(added)
    out["removed_count"] = len(removed)
    return out
