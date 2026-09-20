#!/usr/bin/env python3
"""validate-model-registry.py：Model Registry 校验器（Task 07 T07-2，只读）。

12 项检查（任务书 §九）：
 1. modelId 唯一
 2. providerId 已 canonicalize（等于公开体系值，非 ledger 别名）
 3. alias 同 provider 下不得冲突映射两个 modelId
 4. canonicalName 非空
 5. familyId 关系合法（family 实体的 familyId == modelId；成员引用的
    family 实体存在或至少同 provider）
 6. pointer 不得与固定 model 混用（pointer 条目的 alias 不得出现在
    其他 model 条目）
 7. snapshot alias 必须显式标记 type=snapshot
 8. classification 枚举合法（model|family|pointer|non_model）
 9. alias type 枚举合法（raw|display|snapshot|cross_generation|api_id|platform_sku）
10. Gold Set 引用的 raw alias（模型类）在 registry 中存在
11. registry 稳定排序
12. 不允许隐式生成 modelId（所有 modelId 形如 provider:slug 且 slug 非空）

用法：
  python3 pipeline/scripts/validate-model-registry.py          # 全量校验（打印报告）
  python3 pipeline/scripts/validate-model-registry.py --check  # 错误清单为空 → 退出 0
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE))

from pipeline.model_identity.provider_map import (  # noqa: E402
    UnknownProviderError, canonicalize_provider_id)
from pipeline.model_identity.registry import ALIAS_TYPES, CLASSIFICATIONS  # noqa: E402

REGISTRY_PATH = BASE / 'data/model-registry/models.json'
GOLD_PATH = BASE / 'docs/product/maas-daily-product-plan/task-07-model-identity-gold.json'

_MODEL_ID_RE = re.compile(r'^[a-z0-9-]+:[a-z0-9.-]+$')
_DATE_SUFFIX_RE = re.compile(r'-\d{4}-\d{2}-\d{2}$')


def validate(registry: dict | None = None, gold: dict | None = None) -> list[str]:
    errors: list[str] = []
    reg = registry if registry is not None else json.loads(REGISTRY_PATH.read_text())
    gld = gold if gold is not None else json.loads(GOLD_PATH.read_text())
    models = reg.get('models', [])

    seen_ids: dict[str, int] = {}
    alias_owner: dict[tuple[str, str], str] = {}
    family_entities: set[str] = set()
    pointer_alias_values: set[tuple[str, str]] = set()

    # 预扫描 family / pointer
    for m in models:
        if m['classification'] == 'family':
            family_entities.add(m['familyId'])
        if m['classification'] == 'pointer':
            for a in m['aliases']:
                pointer_alias_values.add((m['providerId'], a['value']))

    for i, m in enumerate(models):
        mid = m.get('modelId', '')
        # 1. modelId 唯一
        if mid in seen_ids:
            errors.append(f'[1] modelId 重复: {mid}')
        seen_ids[mid] = i
        # 12. modelId 形态（provider:slug，无隐式生成）
        if not _MODEL_ID_RE.match(mid):
            errors.append(f'[12] modelId 形态非法: {mid!r}')
        # 2. providerId 已 canonical
        try:
            if canonicalize_provider_id(m['providerId']) != m['providerId']:
                errors.append(f'[2] providerId 非 canonical: {m["providerId"]} ({mid})')
        except UnknownProviderError:
            errors.append(f'[2] providerId 未知: {m["providerId"]} ({mid})')
        # 4. canonicalName 非空
        if not (m.get('canonicalName') or '').strip():
            errors.append(f'[4] canonicalName 为空: {mid}')
        # 8. classification 枚举
        if m['classification'] not in CLASSIFICATIONS:
            errors.append(f'[8] classification 非法: {m["classification"]} ({mid})')
        # 5. familyId 合法性
        fid = m.get('familyId')
        if not fid:
            errors.append(f'[5] familyId 缺失: {mid}')
        elif m['classification'] == 'family' and fid != mid:
            errors.append(f'[5] family 实体 familyId≠modelId: {fid} vs {mid}')
        # aliases
        for a in m.get('aliases', []):
            v = a.get('value', '')
            # 9. alias type 枚举
            if a.get('type') not in ALIAS_TYPES:
                errors.append(f'[9] alias type 非法: {a.get("type")} ({mid} / {v})')
            if not v.strip():
                errors.append(f'[9] alias value 为空: {mid}')
            # 3. alias 同 provider 冲突
            key = (m['providerId'], v)
            if key in alias_owner and alias_owner[key] != mid:
                errors.append(f'[3] alias 冲突: {key} 同时映射 {alias_owner[key]} 与 {mid}')
            alias_owner[key] = mid
            # 7. snapshot 显式标记
            if _DATE_SUFFIX_RE.search(v) and a.get('type') != 'snapshot':
                errors.append(f'[7] 日期后缀 alias 未标 snapshot: {v} ({mid} 的 {a.get("type")})')
        # 6. pointer 与固定 model 混用（反向：model 条目含 pointer 的值）
        if m['classification'] == 'model':
            for a in m.get('aliases', []):
                if (m['providerId'], a['value']) in pointer_alias_values:
                    errors.append(f'[6] model 条目复用 pointer 值: {a["value"]} ({mid})')

    # 5b. 成员引用的 family 实体存在（或 family 有成员/合法空）
    for m in models:
        if m['classification'] in ('model', 'pointer'):
            fid = m.get('familyId')
            if fid and fid not in family_entities and fid != m.get('modelId'):
                # family 实体缺失不阻断（首批覆盖有限），但同 provider 校验
                if not fid.startswith(m['providerId'] + ':'):
                    errors.append(f'[5] familyId 跨 provider: {fid} vs {m["providerId"]} ({m["modelId"]})')

    # 10. Gold Set 模型类 raw alias 在 registry 存在
    reg_alias_values = {a['value'] for m in models for a in m['aliases']}
    for e in gld.get('entries', []):
        if e['providerId'] == '*' or e['classification'] in ('family', 'non_model', 'ambiguous'):
            continue
        for a in e['knownAliases']:
            if a == a.lower() and ' ' not in a and not a.startswith('('):
                if a not in reg_alias_values:
                    errors.append(f'[10] Gold raw alias 不在 registry: {a} ({e["canonicalName"]})')

    # 11. 稳定排序
    keys = [(m['providerId'], m['modelId']) for m in models]
    if keys != sorted(keys):
        errors.append('[11] registry 未按 (providerId, modelId) 排序')

    # 10b/10c：alias 必须来自真实数据（audit raws——price.model 与 display 全集）
    if not getattr(validate, '_skip_reality', False):
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                'audit_mi', BASE / 'pipeline/scripts/audit-model-identities.py')
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            real_raws = {r['raw'] for r in _mod.audit()['records']}
            real_displays = set()
            for r in _mod.audit()['records']:
                real_displays.update(r.get('displayNames') or [])
            for m in models:
                # family 实体的 alias 是查询侧字符串（用户输入/文档），不在价格数据——豁免
                if m['classification'] == 'family':
                    continue
                for a in m['aliases']:
                    # source=public 的 alias 来自厂商文档/查询侧（非价格抓取）——豁免真实性到 Gold 人工域
                    if a.get('source') == 'public':
                        continue
                    if a['type'] in ('raw', 'snapshot') and a['value'] not in real_raws:
                        errors.append(f'[10b] raw/snapshot alias 不在真实数据: {a["value"]} ({m["modelId"]})')
                    if a['type'] == 'display' and a['value'] not in real_displays:
                        errors.append(f'[10b] display alias 不在真实数据: {a["value"]} ({m["modelId"]})')
            for e in gld.get('entries', []):
                if e['providerId'] == '*' or e['classification'] in ('family', 'non_model', 'ambiguous'):
                    continue
                for a in e['knownAliases']:
                    if a == a.lower() and ' ' not in a and not a.startswith('(') and a not in real_raws:
                        errors.append(f'[10c] Gold raw alias 不在真实数据: {a} ({e["canonicalName"]})')
        except Exception as ex:  # 审计不可用时跳过（单测注入场景）
            errors.append(f'[10b] 真实性校验失败: {ex}')

    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Model Registry 校验（只读）')
    ap.add_argument('--check', action='store_true', help='静默模式：错误非空退出 1')
    args = ap.parse_args(argv)
    errors = validate()
    if args.check:
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            return 1
        return 0
    if errors:
        print(f'✗ {len(errors)} 项违规：')
        for e in errors:
            print(f'  {e}')
        return 1
    print('✓ Model Registry 校验通过（12 项检查零违规）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
