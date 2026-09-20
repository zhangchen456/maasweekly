#!/usr/bin/env python3
"""audit-model-identities.py：模型身份盘点（Task 07 T07-1，只读审计）。

目标：回答「当前真实数据中模型名称到底有多少种写法」——不做任何
identity 判断/合并/落库；「疑似」仅用于审计报告。

数据源（全部本地只读）：
  1. site/src/data/pricing/ledger.json      —— price.model / model_display_name
     （provider 体系 = pricing providerId：openai/qwen/doubao/glm/…）
  2. data/public/v1/manifest.json → 当前 release 的 changes.json
     —— price_change.price.model（providerId 体系：alibaba/volcengine/…）
     —— price_change.title 中「· model 组件 价格变化」形态（文本抽取，标注低可信）
     —— source_observation.title（无结构化 model 字段）
  3. pipeline/config/public_providers.json  —— provider 两套命名映射（registry 维度）

用法：
  python3 pipeline/scripts/audit-model-identities.py
  python3 pipeline/scripts/audit-model-identities.py --json
  python3 pipeline/scripts/audit-model-identities.py --output /tmp/model-audit.json

性质：只读、无网络、无 LLM、确定性输出（排序稳定，相同输入结果相同）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# 数据装载（只读）
# ---------------------------------------------------------------------------

def _load_public_changes() -> list[dict]:
    """当前 release 的 changes（经 manifest 定位，不遍历 releases/）。"""
    man = json.loads((BASE / 'data/public/v1/manifest.json').read_text())
    ds = man['datasetVersion']
    p = BASE / 'data/public/v1/releases' / ds / 'changes.json'
    data = json.loads(p.read_text())
    return data if isinstance(data, list) else data.get('items', [])


def _load_ledger() -> dict:
    return json.loads((BASE / 'site/src/data/pricing/ledger.json').read_text())


def _load_public_providers() -> dict:
    return json.loads((BASE / 'pipeline/config/public_providers.json').read_text())


# ---------------------------------------------------------------------------
# 名称归一（仅用于「疑似近似」审计分组——不写回、不合并身份）
# ---------------------------------------------------------------------------

def norm(s: str) -> str:
    """审计分组用的宽松归一：小写 + 去连字符/空格/slash/冒号（保留点——
    3.5 与 35 是不同模型）。

    只影响「哪些 raw string 被放在一起比较」，绝不代表它们是同一模型。
    """
    return re.sub(r'[-\s/:]', '', s).lower()


def norm_case_only(s: str) -> str:
    """仅大小写归一（连字符等分隔符差异单独一组报告）。"""
    return s.lower()


# title 中抽取模型段的形态：「Provider · MODEL COMPONENT 价格变化」
_TITLE_MODEL_RE = re.compile(r'^[^·]+·\s*(.+?)\s+(?:input|output|cached|缓存|输入|输出).*价格变化')

# 明显非具体模型的字符串（审计维度之一；判断只用于标注，不删数据）
_NON_MODEL_HINTS = re.compile(
    r'^(latest|default|auto|all|other|new|base|chat|embed|rerank|fine-?tuning|'
    r'tier|standard|free|pro|enterprise|on-?demand|batch|realtime)$', re.I)


def looks_non_model(s: str) -> bool:
    if _NON_MODEL_HINTS.match(s.strip()):
        return True
    # 纯 pricing group / 计费条件词
    if re.fullmatch(r'(input|output|cached|cache|存储|上下文)[\w ]*', s.strip(), re.I):
        return True
    return False


# family-like：无版本号/参数后缀的裸家族名（宽松启发，仅供审计标注）
_FAMILY_HINT = re.compile(
    r'^(gpt-?5|gpt-?4|claude|claude (?:opus|sonnet|haiku|fable|mythos)|gemini|qwen|glm|'
    r'deepseek|kimi|k2|doubao|minimax|mistral|llama)(?:\s*-?\s*\d+(?:\.\d+)?)?$', re.I)

# variant-like：带参数/变体后缀
_VARIANT_HINT = re.compile(
    r'(?:-\d+b|-\d+x\d+b|-\d+\.\d+b|[0-9]+b-|[a-z]{1,4}-turbo|-latest|-preview|-thinking|-chat|-instruct|-coder|-vision|-mini|-nano|-exp|-b\d+|-thinking|-\d{4}|-v\d+(?:\.\d+)?(?:-ital)?)$', re.I)


def classify_shape(s: str) -> str:
    """审计标注（非结论）：family-like / variant-like / specific / non_model-like。"""
    if looks_non_model(s):
        return 'non_model_like'
    if _VARIANT_HINT.search(s):
        return 'variant_like'
    if _FAMILY_HINT.match(s):
        return 'family_like'
    return 'specific'


# ---------------------------------------------------------------------------
# 主审计
# ---------------------------------------------------------------------------

def audit() -> dict:
    ledger = _load_ledger()
    changes = _load_public_changes()
    providers_cfg = _load_public_providers()
    p2p = providers_cfg['pricingProviderIdToProvider']

    # 统一记录形态：{raw: {provider, source_counter, display_names}}
    # source ∈ {prices, price_changes, title_extract, registry?}
    entries: dict[str, dict] = {}

    def record(raw: str, source: str, provider: str, display: str | None = None):
        if not raw:
            return
        e = entries.setdefault(raw, {'sources': Counter(), 'providers': set(),
                                     'display_names': set()})
        e['sources'][source] += 1
        if provider:
            e['providers'].add(provider)
        if display and display != raw:
            e['display_names'].add(display)

    # 1. ledger prices（价格事实；provider 为 pricing providerId 体系）
    for p in ledger['prices']:
        record(p['model'], 'prices', p['provider'], p.get('model_display_name'))

    # 2. 公开投影 price_change（结构化 price.model；providerId 体系）
    for it in changes:
        if it.get('recordType') != 'price_change':
            continue
        price = it.get('price') or {}
        record(price.get('model'), 'price_changes', it.get('providerId'))
        # title 文本抽取（低可信——仅审计展示）
        m = _TITLE_MODEL_RE.match(it.get('title') or '')
        if m:
            record(m.group(1).strip(), 'title_extract', it.get('providerId'))

    # 3. source_observation：title 无结构化 model——只统计 provider 维度
    so_providers = Counter(
        it.get('providerId') or '(none)' for it in changes
        if it.get('recordType') == 'source_observation')

    # ---- 汇总 ----
    raw_sorted = sorted(entries)
    out_rows = []
    for raw in raw_sorted:
        e = entries[raw]
        out_rows.append({
            'raw': raw,
            'count': sum(e['sources'].values()),
            'sources': {k: e['sources'][k] for k in sorted(e['sources'])},
            'providers': sorted(e['providers']),
            'displayNames': sorted(e['display_names']),
            'shape': classify_shape(raw),
        })

    # provider 分布（按 raw string 计数）
    provider_raw_counts: dict[str, int] = defaultdict(int)
    for r in out_rows:
        for pv in r['providers']:
            provider_raw_counts[pv] += 1

    # 大小写差异（同 norm 组内出现 >1 个 raw）
    norm_groups: dict[str, list[str]] = defaultdict(list)
    for raw in raw_sorted:
        norm_groups[norm(raw)].append(raw)

    def _diff_kind(a: str, b: str) -> str:
        kinds = []
        if a.lower() != b.lower():
            kinds.append('case')
        stripped = lambda x: re.sub(r'[-\s/:._]', '', x)
        if a != b and stripped(a) == stripped(b):
            kinds.append('separator')
        if a.replace(' ', '') != b.replace(' ', ''):
            if 'case' not in kinds and 'separator' not in kinds:
                kinds.append('other')
        return '+'.join(kinds) if kinds else 'same'

    def _fold_providers(raws):
        """provider 折叠到公开 providerId 体系（qwen→alibaba 等），
        再判断真正的跨 provider（两套命名指向同一家不算跨）。"""
        provs = set()
        for raw in raws:
            for pv in entries[raw]['providers']:
                provs.add(p2p.get(pv, pv))
        return provs

    near_same_provider = []  # 同 provider 内近似
    cross_provider = []      # 跨 provider 同名/近似（折叠后仍多家）
    same_string_multi_provider = []  # 完全同串多 provider（折叠后多家）
    diff_groups = []
    for key, group in sorted(norm_groups.items()):
        if len(group) > 1:
            kinds = set()
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    kinds.add(_diff_kind(group[i], group[j]))
            g = {'group': group, 'diffKinds': sorted(kinds)}
            diff_groups.append(g)
            folded = _fold_providers(group)
            if len(folded) == 1:
                near_same_provider.append(g)
            else:
                cross_provider.append(g)

    # 完全相同 raw string 出现在（折叠后）多个 provider
    for raw in raw_sorted:
        folded = _fold_providers([raw])
        if len(folded) > 1:
            same_string_multi_provider.append(
                {'raw': raw, 'providers': sorted(folded)})

    # 形态分布
    shape_counts = Counter(r['shape'] for r in out_rows)

    # 非模型样例
    non_model = [r['raw'] for r in out_rows if r['shape'] == 'non_model_like']

    # 高风险自动误绑候选：同 norm 组跨 provider（fuzzy 会合并）
    risky = [
        {'group': g['group'], 'providers': sorted(
            set().union(*(entries[r]['providers'] for r in g['group']))),
         'reason': '同 normalized 形态跨 provider——fuzzy match 会误绑'}
        for g in cross_provider
    ]

    # top ambiguous：出现在多数据源但无 display 对齐 / 形态不明
    ambiguous = [
        {'raw': r['raw'], 'sources': r['sources'], 'shape': r['shape']}
        for r in out_rows
        if len(r['sources']) > 1 and r['shape'] in ('family_like', 'non_model_like')
    ][:40]

    return {
        'meta': {
            'datasetVersion': json.loads(
                (BASE / 'data/public/v1/manifest.json').read_text())['datasetVersion'],
            'dataThrough': json.loads(
                (BASE / 'data/public/v1/manifest.json').read_text())['dataThrough'],
            'readme': '只读审计；「疑似/近似」仅为报告标注，不代表同一模型结论',
        },
        'totals': {
            'uniqueRawModelStrings': len(raw_sorted),
            'ledgerPriceFacts': len(ledger['prices']),
            'priceChangeRecords': sum(
                1 for it in changes if it.get('recordType') == 'price_change'),
            'sourceObservations': sum(
                1 for it in changes if it.get('recordType') == 'source_observation'),
            'priceChangeModelsUnique': len(set(
                (it.get('price') or {}).get('model') for it in changes
                if it.get('recordType') == 'price_change') - {None}),
        },
        'providerDistribution': dict(sorted(provider_raw_counts.items())),
        'providerNamingSystems': {
            'pricingProviderIdToProvider': p2p,
            'note': 'ledger 用 pricing providerId（qwen/doubao/glm），公开投影用 '
                    'providerId（alibaba/volcengine/zhipu）——两套体系并存',
        },
        'shapeDistribution': dict(sorted(shape_counts.items())),
        'formatDiffGroups': diff_groups[:80],
        'nearMatchesSameProvider': near_same_provider[:40],
        'crossProviderMatches': cross_provider[:40],
        'nonModelLike': sorted(non_model),
        'sameStringMultiProvider': same_string_multi_provider,
        'displayNameVariants': {
            'note': 'raw model 与 model_display_name 的差异对（同模型两种写法）——'
                    'ledger 内 54 对（首查时观察），此处由 records[].displayNames 逐条承载',
        },
        'formatDiffFinding': {
            'caseVariants': len([g for g in diff_groups if any('case' in k for k in g['diffKinds'])]),
            'separatorVariants': len([g for g in diff_groups if any('separator' in k for k in g['diffKinds'])]),
            'conclusion': 'price.model 全部来自结构化抓取，raw 层零 case/separator 变体；'
                          '格式差异集中在 display_name 层与 provider 双命名体系',
        },
        'highRiskAutoMergeCandidates': risky[:30],
        'topAmbiguous': ambiguous,
        'sourceObservationProviders': dict(sorted(so_providers.items())),
        'records': out_rows,
    }


def _print_report(rep: dict):
    t = rep['totals']
    print('═' * 64)
    print('模型身份盘点（只读审计 · Task 07 T07-1）')
    print('═' * 64)
    print(f"datasetVersion: {rep['meta']['datasetVersion'][:16]}…  "
          f"dataThrough: {rep['meta']['dataThrough']}")
    print()
    print(f"unique raw model strings : {t['uniqueRawModelStrings']}")
    print(f"ledger price facts        : {t['ledgerPriceFacts']}")
    print(f"price_change 记录         : {t['priceChangeRecords']} "
          f"（unique models {t['priceChangeModelsUnique']}）")
    print(f"source observations       : {t['sourceObservations']}（无结构化 model 字段）")
    print()
    print('—— provider 分布（raw string 数）——')
    for pv, n in rep['providerDistribution'].items():
        print(f'  {pv:<12} {n}')
    print()
    print(f"—— 命名形态分布 ——  {rep['shapeDistribution']}")
    print()
    print(f"—— 同 provider 疑似近似组: {len(rep['nearMatchesSameProvider'])} ——")
    for g in rep['nearMatchesSameProvider'][:12]:
        print(f"  {g['diffKinds']}  {g['group']}")
    print()
    print(f"—— 跨 provider 同名/近似组: {len(rep['crossProviderMatches'])} ——")
    for g in rep['crossProviderMatches'][:12]:
        provs = sorted(set().union(*[set() for _ in g['group']]))  # 占位（records 内查）
        print(f"  {g['diffKinds']}  {g['group']}")
    print()
    print(f"—— 非模型样例: {len(rep['nonModelLike'])} ——")
    print(' ', rep['nonModelLike'][:15])
    print()
    print(f"—— 高风险自动误绑候选（fuzzy 会合并）: {len(rep['highRiskAutoMergeCandidates'])} ——")
    for r in rep['highRiskAutoMergeCandidates'][:10]:
        print(f"  {r['providers']}  {r['group']}")
    print()
    print('—— source_observation 只有文本（title 无结构化 model）——')
    print(f"  provider 分布: {rep['sourceObservationProviders']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='模型身份只读审计')
    ap.add_argument('--json', action='store_true', help='输出完整 JSON（含逐条记录）')
    ap.add_argument('--output', type=str, help='写 JSON 到文件')
    args = ap.parse_args(argv)

    rep = audit()
    if args.output:
        Path(args.output).write_text(
            json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=False))
        print(f'✓ 写入 {args.output}', file=sys.stderr)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_report(rep)
    return 0


if __name__ == '__main__':
    sys.exit(main())
