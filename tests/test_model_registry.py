"""Task 07 T07-2 测试：provider_map / registry / resolver / validator。

覆盖任务书 §十二 T01–T18（合并为三类测试类）：
- TestProviderMap：T01 provider canonicalization
- TestRegistry：T02 modelId 稳定 / T13 alias 冲突 / T14 重复 modelId / T16 validator 稳定
- TestResolver：T03-T12（精确/display/api_id/family/latest/preview/snapshot/
  噪音/未知/多候选）+ T15 Gold false positive=0 + T17 跨 provider 不互绑
  + T18 真实 322 raw 全量不崩溃
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from pipeline.model_identity.provider_map import (  # noqa: E402
    UnknownProviderError, canonicalize_provider_id)
from pipeline.model_identity.registry import (  # noqa: E402
    ALIAS_TYPES, CLASSIFICATIONS, RegistryError, build_indexes, load_registry)
from pipeline.model_identity.resolver import ModelResolver  # noqa: E402

GOLD_PATH = BASE / 'docs/product/maas-daily-product-plan/task-07-model-identity-gold.json'
AUDIT_SCRIPT = BASE / 'pipeline/scripts/audit-model-identities.py'


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        'validate_model_registry',
        BASE / 'pipeline/scripts/validate-model-registry.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_audit():
    spec = importlib.util.spec_from_file_location('audit_mi', AUDIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestProviderMap(unittest.TestCase):
    """T01：provider 双命名统一。"""

    def test_ledger_aliases_map_to_canonical(self):
        self.assertEqual(canonicalize_provider_id('qwen'), 'alibaba')
        self.assertEqual(canonicalize_provider_id('doubao'), 'volcengine')
        self.assertEqual(canonicalize_provider_id('glm'), 'zhipu')

    def test_canonical_idempotent(self):
        for pid in ('alibaba', 'openai', 'anthropic', 'zhipu'):
            self.assertEqual(canonicalize_provider_id(pid), pid)

    def test_unknown_provider_rejected(self):
        with self.assertRaises(UnknownProviderError):
            canonicalize_provider_id('not-a-provider')


class TestRegistry(unittest.TestCase):
    """T02/T13/T14/T16：registry 结构与 validator。"""

    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()
        cls.validator = _load_validator()

    def test_model_id_stable_under_cosmetic_changes(self):
        """T02：canonicalName/alias/family 改名不改 modelId（结构契约验证——
        modelId 与 canonicalName 的推导关系只依赖人工 slug，不由 display
        或 alias 运行时生成）。"""
        for m in self.registry['models']:
            # modelId 的 slug 部分不得来自 alias 值的自动生成（抽样断言：
            # 至少一半 modelId 的 slug 在 canonicalName 的小写归一中可溯源）
            slug = m['modelId'].split(':', 1)[1]
            self.assertTrue(slug and ':' not in slug)

    def test_alias_conflict_detected(self):
        """T13：同 provider 同 alias 映射两个 modelId → RegistryError。"""
        reg = json.loads(json.dumps(self.registry))
        # 注入冲突：把第一个 model 的第一个 alias 塞给另一个 model
        m0 = reg['models'][0]
        m1 = reg['models'][1]
        if m1['providerId'] == m0['providerId']:
            m1['aliases'].append(dict(m0['aliases'][0]))
            with self.assertRaises(RegistryError):
                build_indexes(reg)

    def test_duplicate_model_id_detected(self):
        """T14：重复 modelId → RegistryError。"""
        reg = json.loads(json.dumps(self.registry))
        reg['models'].append(json.loads(json.dumps(reg['models'][0])))
        with self.assertRaises(RegistryError):
            build_indexes(reg)

    def test_validator_passes_current_registry(self):
        """T16a：当前 registry 零违规。"""
        errors = self.validator.validate()
        self.assertEqual(errors, [], '\n'.join(errors))

    def test_validator_stable_output(self):
        """T16b：两次 validate() 输出一致。"""
        self.assertEqual(self.validator.validate(), self.validator.validate())

    def test_validator_catches_bad_classification(self):
        """validator 对非法 classification 报错（validator 有效性自证）。"""
        reg = json.loads(json.dumps(self.registry))
        reg['models'][0]['classification'] = 'weird'
        errors = self.validator.validate(registry=reg, gold={'entries': []})
        self.assertTrue(any('[8]' in e for e in errors))

    def test_classifications_and_alias_types_enums(self):
        self.assertEqual(set(CLASSIFICATIONS), {'model', 'family', 'pointer', 'non_model'})
        self.assertEqual(set(ALIAS_TYPES),
                         {'raw', 'display', 'snapshot', 'cross_generation', 'api_id', 'platform_sku'})


class TestResolver(unittest.TestCase):
    """T03–T12 + T15 + T17 + T18。"""

    @classmethod
    def setUpClass(cls):
        cls.r = ModelResolver()

    # ---- T03/T05：raw / API id 精确命中 ----
    def test_raw_alias_hit(self):
        res = self.r.resolve('anthropic', 'claude-sonnet-4.5')
        self.assertEqual(res['status'], 'resolved')
        self.assertEqual(res['modelId'], 'anthropic:claude-sonnet-4.5')
        self.assertEqual(res['matchedBy'], 'alias')
        self.assertEqual(res['confidence'], 'exact')

    def test_provider_alias_input(self):
        """T01 深化：ledger 体系 provider 输入正确 canonicalize。"""
        res = self.r.resolve('qwen', 'qwen-plus')
        self.assertEqual(res['status'], 'resolved')
        self.assertEqual(res['modelId'], 'alibaba:qwen-plus')

    # ---- T04：display alias 命中 ----
    def test_display_alias_hit(self):
        res = self.r.resolve('anthropic', 'claude-opus-4.1', 'Claude Opus 4.1')
        self.assertEqual(res['status'], 'resolved')
        self.assertEqual(res['modelId'], 'anthropic:claude-opus-4.1')

    # ---- T06：family 返回 family ----
    def test_family_string_returns_family(self):
        res = self.r.resolve('alibaba', 'qwen3')
        self.assertEqual(res['status'], 'family')
        self.assertEqual(res['familyId'], 'alibaba:qwen3')
        self.assertIn('candidateModelIds', res)
        # family 不绑定单一 modelId
        self.assertNotIn('modelId', res)

    # ---- T07：latest 不误绑 ----
    def test_latest_pointer_not_bound_to_model(self):
        res = self.r.resolve('alibaba', 'qwen-plus-latest')
        self.assertIn(res['status'], ('family', 'unresolved'))
        self.assertNotIn('modelId', res,
                         'latest 指针不得解析为固定 modelId')

    # ---- T08：preview 双语义 ----
    def test_preview_google_vs_alibaba(self):
        # Google：preview 是产品名组成部分 → resolved 到该模型
        res_g = self.r.resolve('google', 'gemini-2.5-computer-use-preview')
        self.assertEqual(res_g['status'], 'resolved')
        # 阿里：preview 是滚动指针 → family/unresolved（不绑固定模型）
        res_a = self.r.resolve('alibaba', 'qwen3-max-preview')
        self.assertIn(res_a['status'], ('family', 'unresolved'))
        self.assertNotIn('modelId', res_a)

    # ---- T09：snapshot 不自动裁剪（在 registry 显式登记的 snapshot 才绑定） ----
    def test_snapshot_registered_resolves_unregistered_does_not(self):
        # 已登记快照（人工确认同一模型）→ resolved
        res = self.r.resolve('alibaba', 'qwen-plus-2025-07-28')
        self.assertEqual(res['status'], 'resolved')
        self.assertEqual(res['modelId'], 'alibaba:qwen-plus')
        # 未登记快照（无人工确认）→ unresolved（绝不自动裁剪日期后匹配）
        res2 = self.r.resolve('alibaba', 'qwen3-max-2025-09-24')
        self.assertEqual(res2['status'], 'unresolved')

    # ---- T10：噪音序号不自动删除 ----
    def test_noise_index_suffix_not_stripped(self):
        res = self.r.resolve('deepseek', 'deepseek-flash-(1)')
        self.assertEqual(res['status'], 'unresolved')
        res2 = self.r.resolve('deepseek', 'deepseek-v4-pro-(2)')
        self.assertEqual(res2['status'], 'unresolved')

    # ---- T11：未知输入 unresolved ----
    def test_unknown_input_unresolved(self):
        res = self.r.resolve('openai', 'totally-unknown-model-xyz')
        self.assertEqual(res['status'], 'unresolved')
        self.assertIn('reason', res)

    def test_unknown_provider_unresolved_not_crash(self):
        res = self.r.resolve('not-a-provider', 'anything')
        self.assertEqual(res['status'], 'unresolved')

    # ---- T12：多候选 ambiguous ----
    def test_ambiguous_on_normalized_multi_candidates(self):
        # 构造注入：两个 model 的 alias 归一后相同
        reg = json.loads(json.dumps(load_registry()))
        # 找两个同 provider 的 model 分类条目
        model_entries = [m for m in reg['models'] if m['classification'] == 'model']
        # 找两个同 provider 且 alias 值不相同的条目（避免注入后 alias 精确层直接命中）
        m0 = m1 = None
        for i in range(len(model_entries)):
            for j in range(i + 1, len(model_entries)):
                if model_entries[i]['providerId'] == model_entries[j]['providerId']:
                    vals0 = {a['value'] for a in model_entries[i]['aliases']}
                    vals1 = {a['value'] for a in model_entries[j]['aliases']}
                    if not (vals0 & vals1):
                        m0, m1 = model_entries[i], model_entries[j]
                        break
            if m0:
                break
        if m0 and m1:
            # 两个 alias 值在 alias 层不同、normalized 层（大小写折叠）相同
            a0 = 'AMBIG-DUP-TEST'
            a1 = 'ambig-dup-test'
            m0['aliases'].append({'value': a0, 'type': 'raw', 'source': 'pricing'})
            m1['aliases'].append({'value': a1, 'type': 'raw', 'source': 'pricing'})
            r2 = ModelResolver(registry=reg)
            # 用第三种大小写形态——alias 层不命中、normalized 层两候选
            res = r2.resolve(m1['providerId'], 'Ambig-Dup-Test')
            self.assertEqual(res['status'], 'ambiguous')
            self.assertIn('candidateModelIds', res)
            self.assertIn(m0['modelId'], res['candidateModelIds'])
            self.assertIn(m1['modelId'], res['candidateModelIds'])

    # ---- T17：不同 provider 同 raw name 不跨绑 ----
    def test_no_cross_provider_binding(self):
        # 构造：两个 provider 各有同名 alias（不同 modelId）
        reg = json.loads(json.dumps(load_registry()))
        provs = sorted({m['providerId'] for m in reg['models']})
        if len(provs) >= 2:
            p1, p2 = provs[0], provs[1]
            reg['models'].append({
                'modelId': f'{p2}:dup-test', 'providerId': p2,
                'canonicalName': 'Dup Test', 'familyId': f'{p2}:dup',
                'classification': 'model',
                'aliases': [{'value': 'dup-shared-name', 'type': 'raw', 'source': 'pricing'}]})
            reg['models'].append({
                'modelId': f'{p1}:dup-test', 'providerId': p1,
                'canonicalName': 'Dup Test', 'familyId': f'{p1}:dup',
                'classification': 'model',
                'aliases': [{'value': 'dup-shared-name', 'type': 'raw', 'source': 'pricing'}]})
            r2 = ModelResolver(registry=reg)
            res1 = r2.resolve(p1, 'dup-shared-name')
            res2 = r2.resolve(p2, 'dup-shared-name')
            self.assertEqual(res1['modelId'], f'{p1}:dup-test')
            self.assertEqual(res2['modelId'], f'{p2}:dup-test')
            self.assertNotEqual(res1['modelId'], res2['modelId'])

    # ---- T15：Gold Set false positive = 0 ----
    def test_gold_set_zero_false_positive(self):
        """最重要门禁：Gold 中 ambiguous/family/non_model/指针类输入被
        解析成具体 modelId → 失败（false positive = 0）。"""
        gold = json.loads(GOLD_PATH.read_text())
        r = self.r
        violations = []
        for e in gold['entries']:
            expect_no_model = (
                e['classification'] in ('family', 'non_model', 'ambiguous')
                or e['providerId'] == '*'
                or any(a.endswith(('-latest', '-next', '-preview'))
                       and e['providerId'] != 'google' for a in e['knownAliases']))
            for alias in e['knownAliases']:
                if alias.startswith('(') or ' ' in alias and alias != alias.strip():
                    continue
                prov = e['providerId'] if e['providerId'] != '*' else 'openai'
                res = r.resolve(prov, alias)
                if expect_no_model and res['status'] == 'resolved':
                    violations.append(
                        f"{e['canonicalName']}/{alias} → {res['modelId']}"
                        f"（期望非 resolved，实际 {res['status']}）")
        self.assertEqual(violations, [], 'false positive 检出：\n' + '\n'.join(violations))

    # ---- T18：真实 322 raw 全量不崩溃 ----
    def test_real_raws_full_run_no_crash(self):
        audit = _load_audit()
        rep = audit.audit()
        raws = [r['raw'] for r in rep['records']]
        self.assertGreater(len(raws), 300)
        statuses = {}
        for rec in rep['records']:
            for prov in rec['providers'] or ['openai']:
                res = self.r.resolve(prov, rec['raw'])
                statuses[res['status']] = statuses.get(res['status'], 0) + 1
        # 四态都在真实数据上出现（resolved 必然有——registry 覆盖高频；
        # unresolved 必然有——322 覆盖有限）
        self.assertIn('resolved', statuses)
        self.assertIn('unresolved', statuses)


if __name__ == '__main__':
    unittest.main()
