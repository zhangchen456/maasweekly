#!/usr/bin/env python3
"""validate-developer-registry.py：T07-5.2 Developer / Platform Registry 校验。

校验：
  - developers.json developerId 唯一
  - platforms.json platformId 唯一
  - Developer 与 Platform 独立（无 FK 关系）
  - 每个 entity 的 verificationStatus ∈ {verified, candidate, unresolved}
  - evidence 四字段（sourceType/sourceUrl/verifiedAt/verificationNote）非空
  - verificationStatus=verified 时 evidence 必须存在
  - providerIds 若存在，必须来自 public_providers.json
  - Platform 不含 developerId FK
  - Developer 不含 platforms 反向 FK

用法：
  python3 pipeline/scripts/validate-developer-registry.py          # 校验
  python3 pipeline/scripts/validate-developer-registry.py --check   # 同上
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
VALID_STATUS = {"verified", "candidate", "unresolved"}
EVIDENCE_FIELDS = ["sourceType", "sourceUrl", "verifiedAt", "verificationNote"]


def main() -> int:
    devs = json.loads((BASE / "data/model-registry/developers.json").read_text("utf-8"))
    plats = json.loads((BASE / "data/model-registry/platforms.json").read_text("utf-8"))
    pub = json.loads((BASE / "pipeline/config/public_providers.json").read_text("utf-8"))

    errors: list[str] = []

    # developerId 唯一
    dev_ids = [d["developerId"] for d in devs["developers"]]
    if len(dev_ids) != len(set(dev_ids)):
        errors.append(f"developerId 不唯一: {len(dev_ids)} ids, {len(set(dev_ids))} unique")

    # platformId 唯一
    plat_ids = [p["platformId"] for p in plats["platforms"]]
    if len(plat_ids) != len(set(plat_ids)):
        errors.append(f"platformId 不唯一: {len(plat_ids)} ids, {len(set(plat_ids))} unique")

    pub_provider_set = set(p["providerId"] for p in pub["providers"])

    # Developer 校验
    for d in devs["developers"]:
        did = d["developerId"]
        # 不含 platforms 反向 FK
        if "platforms" in d:
            errors.append(f"developer {did} 含 platforms 反向 FK（Developer/Platform 应独立）")
        # verificationStatus
        vs = d.get("verificationStatus")
        if vs not in VALID_STATUS:
            errors.append(f"developer {did} verificationStatus 非法: {vs}")
        # evidence 四字段
        ev = d.get("evidence", {})
        for f in EVIDENCE_FIELDS:
            if not ev.get(f):
                errors.append(f"developer {did} evidence.{f} 缺失")
        # verificationStatus=verified 时 evidence 必须存在（四字段已在上面检查）
        # providerIds 若存在，必须来自 public_providers
        for pid in d.get("providerIds", []):
            if pid not in pub_provider_set:
                errors.append(f"developer {did} providerId 不在 public_providers: {pid}")

    # Platform 校验
    for p in plats["platforms"]:
        pid = p["platformId"]
        # 不含 developerId FK
        if "developerId" in p:
            errors.append(f"platform {pid} 含 developerId FK（Platform/Developer 应独立）")
        # verificationStatus
        vs = p.get("verificationStatus")
        if vs not in VALID_STATUS:
            errors.append(f"platform {pid} verificationStatus 非法: {vs}")
        # evidence 四字段
        ev = p.get("evidence", {})
        for f in EVIDENCE_FIELDS:
            if not ev.get(f):
                errors.append(f"platform {pid} evidence.{f} 缺失")
        # providerId 若存在，必须来自 public_providers
        if p.get("providerId") and p["providerId"] not in pub_provider_set:
            errors.append(f"platform {pid} providerId 不在 public_providers: {p.get('providerId')}")

    if errors:
        print("✗ Developer/Platform registry 校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # 统计
    dev_status = {s: sum(1 for d in devs["developers"] if d.get("verificationStatus") == s) for s in VALID_STATUS}
    plat_status = {s: sum(1 for p in plats["platforms"] if p.get("verificationStatus") == s) for s in VALID_STATUS}

    print("✓ Developer/Platform registry 校验通过")
    print(f"  developers: {len(devs['developers'])} (verified={dev_status['verified']} candidate={dev_status['candidate']} unresolved={dev_status['unresolved']})")
    print(f"  platforms: {len(plats['platforms'])} (verified={plat_status['verified']} candidate={plat_status['candidate']} unresolved={plat_status['unresolved']})")
    print(f"  Platform→Developer FK: 不存在 ✓")
    print(f"  Developer→Platform FK: 不存在 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
