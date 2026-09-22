"""canonical：公开数据的规范 JSON、稳定排序与 datasetVersion（Task 03 M1）。

算法对齐 pipeline/pricing/archive.py 的 canonical_json 语义（UTF-8 /
ensure_ascii=False / sort_keys / 紧凑分隔符），但独立实现——公开导出
不依赖在线归档模块（避免 pricing 侧演化牵动公开投影的稳定性）。

datasetVersion 契约（任务书 §4.1）：
- 对全部公开实体的规范内容计算，排除 generatedAt / 构建机器路径 /
  requestId / release 目录名
- 同输入重建必须得到相同版本与相同业务文件字节
- 任一公开实体、状态或 coverage 变化都产生新版本
- manifest.files[].sha256 记录实际文件字节哈希（供 --check 与服务端
  启动校验）；datasetVersion 用规范内容摘要——两者分离，勿混用
"""
from __future__ import annotations

import hashlib

SCHEMA_VERSION = "1.0"


def canonical_json(value) -> str:
    """规范 JSON：UTF-8、保留 Unicode、键排序、紧凑分隔符。"""
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entity_digest(entity: dict) -> str:
    """单实体的规范摘要（sha256 hex）。"""
    return _sha256_hex(canonical_json(entity))


def collection_digest(entities: list[dict]) -> str:
    """集合摘要：实体按规范串排序后拼接（\\n 分隔）的 sha256。

    排序必须由调用方按业务排序完成后再传入（本函数不再排序，
    保证「集合内规范串排序」与业务排序的一致性由 projector 单点控制
    ——changes 的业务排序即规范排序：日期倒序 + id 升序）。
    """
    return _sha256_hex("\n".join(canonical_json(e) for e in entities))


# 各集合的稳定排序键（业务排序 = 规范排序，单点定义）
# changes: 有效时间倒序（observationDate 字符串比较）、id 升序 tie-break
# prices:  providerId、modelKey、component、factKey 全升序
# evidence/weekly/items: id 升序
def changes_sort_key(entity: dict) -> tuple:
    return (entity["observationDate"], entity["id"])


def changes_sorted(entities: list[dict]) -> list[dict]:
    """changes 集合的稳定全序：日期倒序 + id 升序（任务书 §5）。"""
    return sorted(entities, key=lambda e: (-_date_ord(e["observationDate"]),
                                           e["id"]))


def _date_ord(d: str) -> int:
    # YYYY-MM-DD 字符串可直接比较；取负实现倒序（返回 tuple 比较用）
    y, m, dd = d.split("-")
    return int(y) * 10000 + int(m) * 100 + int(dd)


def prices_sort_key(entity: dict) -> tuple:
    return (entity["providerId"], entity["modelKey"], entity["component"],
            entity["factKey"])


def by_id_sorted(entities: list[dict]) -> list[dict]:
    """evidence / weekly / items 集合：id 升序。"""
    return sorted(entities, key=lambda e: e["id"])


def compute_data_through(changes: list[dict], prices: list[dict],
                         weekly: list[dict]) -> str:
    """数据覆盖上限：全部观察日期（上海日历日）的最大值。

    数据推导（非墙钟）——进 datasetVersion 不破坏稳定性。
    - changes: observationDate（已是上海日历日）
    - prices: observedAt（ISO UTC）转上海日历日
    - weekly: date（发布日期）
    """
    dates: list[str] = [c["observationDate"] for c in changes]
    dates.extend(w["date"] for w in weekly)
    for p in prices:
        ts = p.get("observedAt") or ""
        if ts:
            dates.append(_shanghai_date(ts))
    return max(dates) if dates else "1970-01-01"


def _shanghai_date(iso_utc: str) -> str:
    """ISO UTC → 上海日历日（+8 无夏令时）。"""
    from datetime import datetime, timedelta
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return (dt + timedelta(hours=8)).strftime("%Y-%m-%d")


def compute_dataset_version(collections: dict[str, list[dict] | dict],
                            data_through: str) -> str:
    """datasetVersion = ds_<64hex>。

    输入 collections：{"changes": [...], "items": [...], "prices": [...],
    "evidence": [...], "weekly": [...], "status": {...},
    "modelIdentities": {"models": [...], "families": [...]}}——全部为
    排序完成后的公开实体（不含 datasetVersion/generatedAt 包装字段，
    那些在哈希之后注入文件）。status 是单实体 dict。
    """
    parts = {name: collection_digest(items) if isinstance(items, list)
             else entity_digest(items)
             for name, items in collections.items()}
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "dataThrough": data_through,
        "collections": dict(sorted(parts.items())),
    }
    return "ds_" + _sha256_hex(canonical_json(payload))
