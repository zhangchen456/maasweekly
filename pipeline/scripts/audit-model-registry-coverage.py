#!/usr/bin/env python3
"""audit-model-registry-coverage.py：unresolved 分层审计（Task 07 T07-2.5，只读）。

对全部真实 raw model strings 跑当前 resolver，把 unresolved 项按显式
规则分层（零 fuzzy/LLM——无法判断标 unknown），为补录提供清单。

建议分类（基于字符串显式特征 + T07-1/T07-2 已固定规则）：
  safe_manual_add     无任何风险特征（无日期/指针/序号/emoji/区域/规格歧义）
                      ——raw 本身即候选稳定模型名
  needs_source_check  带序号 (N)/emoji/复合串——需查源页再定
  pointer             -latest/-next 结尾（阿里 -preview 按规则表判）
  snapshot            日期后缀但未在 registry 登记
  noise               纯序号/计费词残留
  long_tail           低频（出现 1 次）且无风险特征——可后补
  non_model           计费条件词/泛指
  unknown             规则覆盖不到

排序：count desc → providerId → rawModel（稳定）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE))

from pipeline.model_identity.resolver import ModelResolver  # noqa: E402

_DATE_RE = re.compile(r'-\d{4}-\d{2}-\d{2}$')
_INDEX_RE = re.compile(r'\(\d+\)$')
_EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF☀-➿]')
# 区域/规格/模态后缀特征（显式枚举——非语义推断）
_REGION_RE = re.compile(r'-(us|eu|cn|ap-se|ap-ne)$')
_SPEC_RE = re.compile(r'-\d+(\.\d+)?[bt](?:-a\d+b)?$', re.I)
_MODAL_WORDS = ('vl', 'omni', 'audio', 'tts', 'asr', 'image', 'ocr',
                'embedding', 'rerank', 'mt', 'vision', 'live', 'robotics',
                'transcribe', 'seed3d', 'seedream', 'coder', 'math', 'doc')


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        'audit_mi', BASE / 'pipeline/scripts/audit-model-identities.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def classify(raw: str, provider: str, pointer_flag: bool) -> tuple[str, str]:
    """返回 (建议分类, 线索说明)。仅显式规则，无法判断 → unknown。"""
    hints = []
    if _DATE_RE.search(raw):
        hints.append('date-suffix')
    if _INDEX_RE.search(raw):
        hints.append('index-noise')
    if _EMOJI_RE.search(raw):
        hints.append('emoji')
    if raw.endswith(('-latest', '-next')):
        hints.append('rolling-pointer')
    if raw.endswith('-preview'):
        hints.append('preview(provider 语义待判)')
    if _REGION_RE.search(raw):
        hints.append('region-suffix')
    if _SPEC_RE.search(raw):
        hints.append('spec-suffix')
    if any(f'-{w}-' in f'-{raw}-' or raw.split('-')[-1] == w or raw.split('-')[0] == w
           for w in _MODAL_WORDS):
        hints.append('modal-word')
    if pointer_flag:
        hints.append('registry-pointer')

    if 'registry-pointer' in hints or 'rolling-pointer' in hints:
        return 'pointer', ','.join(hints)
    if 'emoji' in hints or 'index-noise' in hints:
        return 'needs_source_check', ','.join(hints)
    if 'date-suffix' in hints:
        return 'snapshot', ','.join(hints)
    # 复合多值串（逗号连接的 Google 页面残留）
    if ',' in raw:
        return 'needs_source_check', 'multi-value-comma'
    if not hints:
        return 'safe_manual_add', ''
    return 'long_tail', ','.join(hints)


def audit_coverage() -> dict:
    audit_mod = _load_audit()
    rep = audit_mod.audit()
    resolver = ModelResolver()

    # raw → (count, providers, displayNames)
    agg: dict[str, dict] = {}
    for rec in rep['records']:
        raw = rec['raw']
        e = agg.setdefault(raw, {'count': 0, 'providers': set(), 'displays': set()})
        e['count'] += rec['count']
        e['providers'].update(rec['providers'])
        e['displays'].update(rec.get('displayNames') or [])

    unresolved_rows = []
    status_counts = Counter()
    for raw, e in agg.items():
        for prov in e['providers']:
            res = resolver.resolve(prov, raw)
            status_counts[res['status']] += 1
            if res['status'] != 'unresolved':
                continue
            pointer_flag = False  # unresolved 不可能是 pointer 命中；保持显式
            cls, hint = classify(raw, prov, pointer_flag)
            unresolved_rows.append({
                'providerId': prov,
                'rawModel': raw,
                'displayName': sorted(e['displays']),
                'count': e['count'],
                'sources': ['prices', 'price_changes'],  # 审计口径（两源同库）
                'hints': hint,
                'reason': res.get('reason', ''),
                'suggestedClass': cls,
            })
    # 稳定排序：count desc → providerId → rawModel
    unresolved_rows.sort(key=lambda r: (-r['count'], r['providerId'], r['rawModel']))

    # 低频判定补充：count == 1 且无风险特征 → long_tail
    for r in unresolved_rows:
        if r['suggestedClass'] == 'safe_manual_add' and r['count'] <= 1:
            r['suggestedClass'] = 'long_tail'

    by_class = Counter(r['suggestedClass'] for r in unresolved_rows)
    by_provider = Counter(r['providerId'] for r in unresolved_rows)

    return {
        'meta': {
            'readme': '只读 unresolved 分层审计——suggestedClass 是补录建议非结论',
            'resolverStatusCounts': dict(sorted(status_counts.items())),
        },
        'totals': {
            'unresolvedRows': len(unresolved_rows),
            'byClass': dict(sorted(by_class.items())),
            'byProvider': dict(sorted(by_provider.items())),
        },
        'unresolved': unresolved_rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='unresolved 分层审计（只读）')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--output', type=str)
    ap.add_argument('--top', type=int, default=40, help='只显示前 N（人读模式）')
    args = ap.parse_args(argv)
    rep = audit_coverage()
    if args.output:
        Path(args.output).write_text(json.dumps(rep, ensure_ascii=False, indent=2))
        print(f'✓ 写入 {args.output}', file=sys.stderr)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        t = rep['totals']
        print('═' * 62)
        print('unresolved 分层审计（T07-2.5）')
        print('═' * 62)
        print('resolver 分布:', rep['meta']['resolverStatusCounts'])
        print('unresolved 行数:', t['unresolvedRows'])
        print('按分类:', t['byClass'])
        print('按 provider:', t['byProvider'])
        print()
        print(f'—— Top {args.top}（count desc → provider → raw）——')
        for r in rep['unresolved'][:args.top]:
            print(f"  {r['count']:>4}  {r['providerId']:<11} {r['rawModel']:<48} {r['suggestedClass']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
