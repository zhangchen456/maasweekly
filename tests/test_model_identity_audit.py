"""Task 07 T07-1 测试：audit-model-identities 只读审计 + Gold Set schema。

覆盖（任务书 §六）：
1. audit 脚本只读（对仓库数据文件的 mtime+hash 前后一致）
2. 重复执行输出稳定（两次 audit() JSON 相等）
3. provider/raw name 排序稳定
4. 同一 raw string 多数据源计数正确聚合
5. Gold Set JSON schema / 必填字段正确
6. Gold Set 不允许重复 canonicalName + providerId
7. knownAliases 去重
8. classification 只能是允许枚举
9. 覆盖多个 provider 和 family/variant/ambiguous/non_model 样例
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCRIPT = BASE / 'pipeline' / 'scripts' / 'audit-model-identities.py'
GOLD = BASE / 'docs' / 'product' / 'maas-daily-product-plan' / 'task-07-model-identity-gold.json'

# 只读性验证盯防的输入文件（audit 读取的全部业务数据）
READ_TARGETS = [
    BASE / 'site/src/data/pricing/ledger.json',
    BASE / 'data/public/v1/manifest.json',
    BASE / 'pipeline/config/public_providers.json',
]


def _load_audit_module():
    spec = importlib.util.spec_from_file_location('audit_model_identities', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _file_fingerprint(p: Path) -> tuple:
    st = p.stat()
    return (st.st_mtime_ns, st.st_size, hashlib.sha256(p.read_bytes()).hexdigest())


class TestAuditReadOnly(unittest.TestCase):
    def test_audit_is_read_only(self):
        """audit() 前后输入文件指纹完全一致（mtime/size/hash）。"""
        before = {p: _file_fingerprint(p) for p in READ_TARGETS}
        mod = _load_audit_module()
        rep = mod.audit()
        self.assertTrue(rep['totals']['uniqueRawModelStrings'] > 0)
        after = {p: _file_fingerprint(p) for p in READ_TARGETS}
        self.assertEqual(before, after, 'audit 修改了输入文件')

    def test_repeated_execution_stable(self):
        """两次 audit() 的 JSON 序列化逐字节一致。"""
        mod = _load_audit_module()
        a = json.dumps(mod.audit(), ensure_ascii=False, sort_keys=False)
        b = json.dumps(mod.audit(), ensure_ascii=False, sort_keys=False)
        self.assertEqual(a, b)

    def test_sorting_stable(self):
        """records 按 raw 排序；providerDistribution 按 provider 排序。"""
        mod = _load_audit_module()
        rep = mod.audit()
        raws = [r['raw'] for r in rep['records']]
        self.assertEqual(raws, sorted(raws))
        provs = list(rep['providerDistribution'])
        self.assertEqual(provs, sorted(provs))

    def test_multi_source_aggregation(self):
        """同一 raw string 在 prices + price_changes 两个数据源的计数正确聚合。"""
        mod = _load_audit_module()
        rep = mod.audit()
        # 独立重算对照：ledger prices 里 anthropic 的 model 计数
        ledger = json.loads((BASE / 'site/src/data/pricing/ledger.json').read_text())
        from collections import Counter
        ledger_counts = Counter(p['model'] for p in ledger['prices'])
        # 抽 5 个真实 raw 验证聚合（prices 维度计数一致）
        recs = {r['raw']: r for r in rep['records']}
        checked = 0
        for raw, n in ledger_counts.items():
            if checked >= 5:
                break
            self.assertIn(raw, recs)
            self.assertEqual(recs[raw]['sources'].get('prices', 0), n,
                             f'prices 计数不一致: {raw}')
            checked += 1

    def test_cli_exit_zero(self):
        """CLI 两种形态退出 0。"""
        for args in ([], ['--json']):
            r = subprocess.run([sys.executable, str(SCRIPT), *args],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[:300])

    def test_cli_output_file(self):
        """--output 写文件且退出 0。"""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            out = f.name
        try:
            r = subprocess.run([sys.executable, str(SCRIPT), '--output', out],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[:300])
            data = json.loads(Path(out).read_text())
            self.assertIn('totals', data)
        finally:
            Path(out).unlink(missing_ok=True)


class TestGoldSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(GOLD.read_text())
        cls.entries = cls.doc['entries']

    def test_required_fields(self):
        required = {'canonicalName', 'providerId', 'family', 'knownAliases',
                    'knownApiIds', 'classification', 'notes'}
        for e in self.entries:
            missing = required - set(e)
            self.assertFalse(missing, f"缺字段 {missing}: {e.get('canonicalName')}")
            self.assertTrue(e['canonicalName'].strip())
            self.assertTrue(e['notes'].strip(), f"notes 空: {e['canonicalName']}")

    def test_no_duplicate_canonical_plus_provider(self):
        keys = [(e['canonicalName'], e['providerId']) for e in self.entries]
        self.assertEqual(len(keys), len(set(keys)),
                         'canonicalName+providerId 重复')

    def test_known_aliases_deduped(self):
        for e in self.entries:
            self.assertEqual(len(e['knownAliases']), len(set(e['knownAliases'])),
                             f"knownAliases 重复: {e['canonicalName']}")

    def test_classification_enum(self):
        allowed = {'model', 'family', 'ambiguous', 'non_model'}
        for e in self.entries:
            self.assertIn(e['classification'], allowed,
                          f"非法 classification: {e['classification']}")

    def test_size_range(self):
        """T07-1 要求 30-50 项；T07-2.5 任务书明确要求扩展 Gold（≥50 上限放宽）。"""
        self.assertGreaterEqual(len(self.entries), 30)
        self.assertLessEqual(len(self.entries), 80)

    def test_multi_provider_coverage(self):
        """覆盖多个 provider（≥6 个非通配）。"""
        provs = {e['providerId'] for e in self.entries if e['providerId'] != '*'}
        self.assertGreaterEqual(len(provs), 6, f'provider 覆盖不足: {provs}')

    def test_classification_coverage(self):
        """四类 classification 都有样例（family/variant/ambiguous/non_model）。"""
        cls = {e['classification'] for e in self.entries}
        self.assertEqual(cls, {'model', 'family', 'ambiguous', 'non_model'})

    def test_hard_cases_present(self):
        """任务书指定的难例类型逐项在位（基于真实数据）。"""
        raws = set()
        for e in self.entries:
            raws.update(e['knownAliases'])
        # 同 family 不同 variant
        self.assertIn('qwen3-coder-plus', raws)
        self.assertIn('qwen3-coder-30b-a3b-instruct', raws)
        # 相似但不是同一个模型
        self.assertIn('claude-sonnet-4.5', raws)
        self.assertIn('gemini-2.5-flash-lite', raws)
        self.assertIn('gemini-2.5-flash', raws)
        # display name 与 raw 不同
        self.assertIn('Claude Opus 4.1', raws)
        self.assertIn('claude-opus-4.1', raws)
        # family 级字符串
        self.assertIn('qwen3', raws)
        self.assertIn('gemini-2.5', raws)
        # 非模型字符串
        self.assertIn('latest', raws)
        self.assertIn('input', raws)

    def test_rolling_pointer_marked_ambiguous_or_non_model(self):
        """滚动指针（-next/-latest/latest 等）不得标 model；-preview 分 provider
        语义：google 的 preview 是产品名组成部分（notes 必须解释），其他
        provider 的 -preview 属滚动指针。"""
        for e in self.entries:
            for a in e['knownAliases']:
                if a in ('latest', 'default', 'auto') or a.endswith('-latest') or a.endswith('-next'):
                    self.assertIn(e['classification'], ('ambiguous', 'non_model', 'family'),
                                  f"滚动指针 {a} 被标 {e['classification']}: {e['canonicalName']}")
                if a.endswith('-preview'):
                    if e['providerId'] == 'google':
                        self.assertIn('产品', e['notes'],
                                      f"google preview 项须在 notes 解释产品名语义: {e['canonicalName']}")
                    else:
                        self.assertIn(e['classification'], ('ambiguous', 'non_model'),
                                      f"滚动指针 {a} 被标 {e['classification']}: {e['canonicalName']}")

    def test_gold_aliases_subset_of_audit_raws(self):
        """Gold Set 的模型类 alias（排除 family/泛指）应存在于真实数据
        （非泛指、非 family 项）——人工基准不得凭空造名。"""
        mod = _load_audit_module()
        rep = mod.audit()
        audit_raws = {r['raw'] for r in rep['records']}
        skipped = 0
        checked = 0
        for e in self.entries:
            if e['providerId'] == '*' or e['classification'] in ('family', 'non_model'):
                skipped += 1
                continue
            for a in e['knownAliases']:
                # display-name 形态（含空格/大写）不在 audit raw 集——只查 raw 形态
                if a == a.lower() and ' ' not in a:
                    checked += 1
                    self.assertIn(a, audit_raws,
                                  f"alias {a!r} 不在真实数据: {e['canonicalName']}")
        self.assertGreater(checked, 20, '校验的 raw alias 太少')


if __name__ == '__main__':
    unittest.main()
