#!/usr/bin/env python3
"""T07-5.1 Ontology Inventory：用仓库真实数据验证 ontology cardinality 和 mapping 边界。

产出：
  - 107 个 public model 的全量 inventory（modelId → developer/upstream/platform/availability 候选）
  - source → platform footprint（modelId 实际在哪些 source 中被观察到）
  - modelId → availability cardinality 分布
  - observedIdentifiers cardinality（1 modelId → N modelKeys）
  - pointer / preview / snapshot 专项
  - region/status 是否属于 Availability

输入（全部仓库真实数据）：
  data/model-registry/models.json
  pipeline/config/public_providers.json
  pipeline/config/maas_official_sources.json
  data/public/v1/releases/<version>/model-identities.json
  data/public/v1/releases/<version>/changes.json
  data/public/v1/releases/<version>/prices.json
  site/src/data/pricing/ledger.json

原则：
  - candidate ≠ verified（只从数据生成候选，不自动判定 ontology relation）
  - false positive = 0（宁可 unresolved，不可错绑）
  - 禁止 fuzzy/edit-distance/embedding/LLM 自动归并
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent


def load_json(path: Path | str) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    # ---- 加载数据 ----
    registry = load_json(BASE / "data/model-registry/models.json")
    pub_providers = load_json(BASE / "pipeline/config/public_providers.json")
    maas_sources = load_json(BASE / "pipeline/config/maas_official_sources.json")

    # 读当前 release
    manifest = load_json(BASE / "data/public/v1/manifest.json")
    rel_dir = BASE / "data/public/v1" / "releases" / manifest["datasetVersion"]
    catalog = load_json(rel_dir / "model-identities.json")
    changes = load_json(rel_dir / "changes.json")
    prices = load_json(rel_dir / "prices.json")

    # ledger（含 pricing source 信息）
    ledger = load_json(BASE / "site/src/data/pricing/ledger.json")

    # ---- 构建索引 ----
    s2p = pub_providers["sourceToProvider"]  # sourceId → providerId
    p2s = defaultdict(list)  # providerId → [sourceId]
    for s, p in s2p.items():
        if p is not None:
            p2s[p].append(s)

    # platforms from maas_official_sources（含 vendor 字段）
    platforms_meta = {p["name"]: p for p in maas_sources["platforms"]}

    # registry model 索引
    reg_by_id = {m["modelId"]: m for m in registry["models"]}

    # ---- 1. 每个 public modelId 的 inventory ----
    inventory = []
    for cat_model in catalog["models"]:
        mid = cat_model["modelId"]
        reg = reg_by_id.get(mid, {})

        # legacy providerId
        legacy_pid = mid.split(":")[0] if ":" in mid else None

        # registry aliases（含 type/source）
        aliases = reg.get("aliases", [])
        observed_keys_from_registry = [a["value"] for a in aliases]
        alias_types = Counter(a.get("type") for a in aliases)
        alias_sources = Counter(a.get("source") for a in aliases)

        # 从 prices 反查 modelKey（observed identifiers from API）
        price_rows = [p for p in prices if p.get("modelId") == mid]
        observed_keys_from_prices = sorted(set(p["modelKey"] for p in price_rows if p.get("modelKey")))

        # 从 changes 反查 sourceId（source footprint）
        change_rows = [c for c in changes if c.get("modelId") == mid]
        change_source_ids = sorted(set(c.get("sourceId") for c in change_rows if c.get("sourceId")))

        # 从 prices 反查 sourceId
        price_source_ids = sorted(set(p.get("sourceId") for p in price_rows if p.get("sourceId")))

        # source → providerId → candidate platforms
        all_source_ids = sorted(set(change_source_ids) | set(price_source_ids))
        source_providers = sorted(set(s2p.get(s) for s in all_source_ids if s2p.get(s)))

        # candidate platform IDs（从 source 名前缀推断，candidate ≠ verified）
        # source 名如 google-gemini-pricing → candidate platform "google-gemini"
        # source 名如 google-vertex-pricing → candidate platform "google-vertex"
        candidate_platforms = sorted(set(
            "-".join(s.split("-")[:2]) if s and s.count("-") >= 1 else s
            for s in all_source_ids if s
        ))

        # ledger pricing source keys（ledger 的 provider 是 pricing provider）
        ledger_prices = [p for p in ledger.get("prices", []) if p.get("modelId") == mid]
        ledger_source_urls = sorted(set(p.get("source_url", "") for p in ledger_prices if p.get("source_url")))

        # cardinality
        availability_count = len(candidate_platforms) if candidate_platforms else 0
        if not all_source_ids and not price_rows and not change_rows:
            availability_count = 0
            avail_status = "unresolved"
        elif len(candidate_platforms) <= 1:
            avail_status = "candidate-1"
        else:
            avail_status = "candidate-N"

        # developer candidate（从 providerId 推断，candidate ≠ verified）
        dev_candidates = {
            "alibaba": "alibaba-qwen",
            "volcengine": "bytedance-doubao",
            "zhipu": "zhipu",
            "anthropic": "anthropic",
            "openai": "openai",
            "google": "google",
            "deepseek": "deepseek",
            "kimi": "moonshot-kimi",
        }
        candidate_developer = dev_candidates.get(legacy_pid, "unresolved")

        # upstream model candidate（developer:model-slug）
        if candidate_developer != "unresolved" and ":" in mid:
            slug = mid.split(":", 1)[1]
            candidate_upstream = f"{candidate_developer}:{slug}"
        else:
            candidate_upstream = "unresolved"

        # ontology status
        if not all_source_ids and not price_rows and not change_rows:
            ontology_status = "no-data"
        elif avail_status == "candidate-N":
            ontology_status = "multi-platform-candidate"
        else:
            ontology_status = "single-platform-candidate"

        inventory.append({
            "modelId": mid,
            "modelName": cat_model.get("modelName"),
            "legacyProviderId": legacy_pid,
            "familyId": reg.get("familyId"),
            "classification": reg.get("classification"),
            "candidateDeveloperId": candidate_developer,
            "candidateUpstreamModelId": candidate_upstream,
            "candidatePlatformIds": candidate_platforms,
            "candidateAvailabilityCount": availability_count,
            "availabilityStatus": avail_status,
            "ontologyStatus": ontology_status,
            "observedModelKeys": observed_keys_from_prices,
            "observedModelKeyCount": len(observed_keys_from_prices),
            "registryAliasTypes": dict(alias_types),
            "registryAliasSources": dict(alias_sources),
            "sourceIds": all_source_ids,
            "changeSourceIds": change_source_ids,
            "priceSourceIds": price_source_ids,
            "ledgerSourceUrls": ledger_source_urls[:3],  # 前 3 个
            "priceRecordCount": len(price_rows),
            "changeRecordCount": len(change_rows),
        })

    # ---- 2. 统计 ----
    stats = {
        "publicModels": len(catalog["models"]),
        "developer": {
            "candidate": len(set(i["candidateDeveloperId"] for i in inventory if i["candidateDeveloperId"] != "unresolved")),
            "unresolved": sum(1 for i in inventory if i["candidateDeveloperId"] == "unresolved"),
        },
        "upstream": {
            "candidate": len(set(i["candidateUpstreamModelId"] for i in inventory if i["candidateUpstreamModelId"] != "unresolved")),
            "unresolved": sum(1 for i in inventory if i["candidateUpstreamModelId"] == "unresolved"),
        },
        "platformCardinality": dict(Counter(i["availabilityStatus"] for i in inventory)),
        "modelIdToAvailabilityCardinality": dict(Counter(i["candidateAvailabilityCount"] for i in inventory)),
        "observedModelKeyCardinality": {
            "single": sum(1 for i in inventory if i["observedModelKeyCount"] == 1),
            "multiple": sum(1 for i in inventory if i["observedModelKeyCount"] > 1),
            "zero": sum(1 for i in inventory if i["observedModelKeyCount"] == 0),
        },
        "ontologyStatus": dict(Counter(i["ontologyStatus"] for i in inventory)),
    }

    # ---- 3. Google 专项 ----
    google_models = [i for i in inventory if i["legacyProviderId"] == "google"]
    google_gemini_only = [i for i in google_models if any("gemini" in p for p in i["candidatePlatformIds"]) and not any("vertex" in p for p in i["candidatePlatformIds"])]
    google_vertex_only = [i for i in google_models if any("vertex" in p for p in i["candidatePlatformIds"]) and not any("gemini" in p for p in i["candidatePlatformIds"])]
    google_both = [i for i in google_models if any("gemini" in p for p in i["candidatePlatformIds"]) and any("vertex" in p for p in i["candidatePlatformIds"])]
    google_neither = [i for i in google_models if not i["candidatePlatformIds"]]

    google_stats = {
        "total": len(google_models),
        "geminiSourceOnly": len(google_gemini_only),
        "vertexSourceOnly": len(google_vertex_only),
        "bothSources": len(google_both),
        "noSourceFootprint": len(google_neither),
        "multiPlatformCandidates": [i["modelId"] for i in google_both],
    }

    # ---- 4. pointer 专项 ----
    pointers = [m for m in registry["models"] if m.get("classification") == "pointer"]
    pointer_inventory = [{
        "pointerModelId": p["modelId"],
        "canonicalName": p.get("canonicalName"),
        "familyId": p.get("familyId"),
        "aliases": [a["value"] for a in p.get("aliases", [])],
        "notes": p.get("notes", ""),
    } for p in pointers]

    # ---- 5. preview 专项 ----
    preview_models = [i for i in inventory if "preview" in i["modelId"].lower()]
    preview_inventory = [{
        "modelId": i["modelId"],
        "candidateUpstreamModelId": i["candidateUpstreamModelId"],
        "ontologyStatus": i["ontologyStatus"],
        "evidenceStatus": "unresolved",
    } for i in preview_models]

    # ---- 6. region/status 专项 ----
    # 检查同一 modelId 是否有不同 region 的 price records
    region_stats = {}
    for i in inventory:
        mid = i["modelId"]
        price_rows = [p for p in prices if p.get("modelId") == mid]
        regions = set(p.get("region") for p in price_rows if p.get("region"))
        if len(regions) > 1:
            region_stats[mid] = sorted(regions)

    # ---- 7. snapshot 专项 ----
    snapshot_aliases = []
    for m in registry["models"]:
        for a in m.get("aliases", []):
            if a.get("type") == "snapshot":
                snapshot_aliases.append({
                    "modelId": m["modelId"],
                    "snapshotValue": a["value"],
                    "source": a.get("source"),
                })

    # ---- 输出 ----
    result = {
        "meta": {
            "script": "pipeline/scripts/ontology-inventory.py",
            "generatedFrom": "仓库真实数据（registry + public release + ledger + source config）",
            "principle": "candidate ≠ verified；false positive = 0；禁止 fuzzy/embedding/LLM",
            "datasetVersion": manifest["datasetVersion"],
            "dataThrough": manifest["dataThrough"],
        },
        "stats": stats,
        "googleStats": google_stats,
        "pointerInventory": pointer_inventory,
        "previewInventory": preview_inventory,
        "regionStats": {
            "modelsWithMultipleRegions": len(region_stats),
            "sample": dict(list(region_stats.items())[:5]),
            "conclusion": "region 出现在 price fact 中，但同一 modelId 有多 region——region 更可能是 price fact condition 而非 Availability 属性（待 T07-5.1 Gold Set 验证）",
        },
        "snapshotStats": {
            "totalSnapshotAliases": len(snapshot_aliases),
            "modelsWithSnapshots": len(set(s["modelId"] for s in snapshot_aliases)),
            "sample": snapshot_aliases[:5],
        },
        "inventory": inventory,
    }

    out_path = BASE / "docs/product/maas-daily-product-plan/task-07-5-1-ontology-inventory.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Ontology inventory → {out_path}")
    print(f"  publicModels={stats['publicModels']}")
    print(f"  platform cardinality: {stats['platformCardinality']}")
    print(f"  modelId→availability: {stats['modelIdToAvailabilityCardinality']}")
    print(f"  observedModelKey: {stats['observedModelKeyCardinality']}")
    print(f"  Google: {google_stats}")
    print(f"  pointers: {len(pointer_inventory)}")
    print(f"  previews: {len(preview_inventory)}")
    print(f"  snapshots: {len(snapshot_aliases)} aliases / {len(set(s['modelId'] for s in snapshot_aliases))} models")
    print(f"  region: {len(region_stats)} models with multiple regions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
