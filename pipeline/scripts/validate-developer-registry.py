#!/usr/bin/env python3
"""validate-developer-registry.py：T07-5.2 Developer / Platform Registry 校验。

校验：
  - developers.json developerId 唯一
  - platforms.json platformId 唯一
  - 每个 platform 的 developerId 存在于 developers.json
  - 每个 developer 的 platforms 存在于 platforms.json
  - 每个 developer 的 providerIds 存在于 public_providers.json
  - developers.json / platforms.json 的 evidence 完整
  - registry model 的 providerId 全部有对应 developer（兼容性）

用法：
  python3 pipeline/scripts/validate-developer-registry.py          # 校验
  python3 pipeline/scripts/validate-developer-registry.py --check   # 同上
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    devs = json.loads((BASE / "data/model-registry/developers.json").read_text("utf-8"))
    plats = json.loads((BASE / "data/model-registry/platforms.json").read_text("utf-8"))
    pub = json.loads((BASE / "pipeline/config/public_providers.json").read_text("utf-8"))
    reg = json.loads((BASE / "data/model-registry/models.json").read_text("utf-8"))

    errors: list[str] = []

    # developerId 唯一
    dev_ids = [d["developerId"] for d in devs["developers"]]
    if len(dev_ids) != len(set(dev_ids)):
        errors.append(f"developerId 不唯一: {len(dev_ids)} ids, {len(set(dev_ids))} unique")

    # platformId 唯一
    plat_ids = [p["platformId"] for p in plats["platforms"]]
    if len(plat_ids) != len(set(plat_ids)):
        errors.append(f"platformId 不唯一: {len(plat_ids)} ids, {len(set(plat_ids))} unique")

    dev_id_set = set(dev_ids)
    plat_id_set = set(plat_ids)
    pub_provider_set = set(p["providerId"] for p in pub["providers"])

    # 每个 platform 的 developerId 存在
    for p in plats["platforms"]:
        if p["developerId"] not in dev_id_set:
            errors.append(f"platform {p['platformId']} 的 developerId 不存在: {p['developerId']}")
        if not p.get("evidence", {}).get("sourceType"):
            errors.append(f"platform {p['platformId']} 缺 evidence")

    # 每个 developer 的 platforms 存在
    for d in devs["developers"]:
        for pid in d.get("platforms", []):
            if pid not in plat_id_set:
                errors.append(f"developer {d['developerId']} 的 platform 不存在: {pid}")
        for pid in d.get("providerIds", []):
            if pid not in pub_provider_set:
                errors.append(f"developer {d['developerId']} 的 providerId 不在 public_providers: {pid}")
        if not d.get("evidence", {}).get("sourceType"):
            errors.append(f"developer {d['developerId']} 缺 evidence")

    # 兼容性：registry model 的 providerId 全部有对应 developer
    reg_provider_ids = set(m["providerId"] for m in reg["models"] if m.get("providerId"))
    dev_provider_ids = set()
    for d in devs["developers"]:
        dev_provider_ids.update(d.get("providerIds", []))
    for pid in reg_provider_ids:
        if pid not in dev_provider_ids:
            errors.append(f"registry model providerId 无对应 developer: {pid}")

    # 每个 platform 的 providerId 存在于 public_providers
    for p in plats["platforms"]:
        if p.get("providerId") not in pub_provider_set:
            errors.append(f"platform {p['platformId']} 的 providerId 不在 public_providers: {p.get('providerId')}")

    if errors:
        print("✗ Developer/Platform registry 校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"✓ Developer/Platform registry 校验通过")
    print(f"  developers: {len(devs['developers'])}")
    print(f"  platforms: {len(plats['platforms'])}")
    print(f"  registry providerIds covered: {len(reg_provider_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
