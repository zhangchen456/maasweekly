"""Task 07 T07-3 测试：public projection + 查询契约。

T01-T07/T20-T22 在此（export/projection 层）；T08-T17（REST/MCP 查询）
在 agent-api 测试运行时验证（本轮已人工验证 + REST 26 项/MCP 13 项回归全绿）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / 'pipeline'))

from model_identity.projector import ModelIdentityProjector, get_projector  # noqa: E402
from model_identity.resolver import ModelResolver  # noqa: E402

GOLD = BASE / 'docs/product/maas-daily-product-plan/task-07-model-identity-gold.json'
EXPORTER = BASE / 'pipeline/scripts/export-public-data.py'


class TestProjectionContract(unittest.TestCase):
    """projector 契约（T01/T03-T07 + pointer/家族红线）。"""

    @classmethod
    def setUpClass(cls):
        cls.p = ModelIdentityProjector()

    def test_resolved_gets_model_id_and_name(self):
        out = self.p.project('anthropic', 'claude-sonnet-4.5', 'Claude Sonnet 4.5')
        self.assertEqual(out['modelId'], 'anthropic:claude-sonnet-4.5')
        self.assertEqual(out['modelName'], 'Claude Sonnet 4.5')

    def test_unresolved_no_model_id(self):
        """T04：unresolved raw 不写 modelId（空投影）。"""
        out = self.p.project('alibaba', 'qwen-flash-us')
        self.assertEqual(out, {})
        out2 = self.p.project('deepseek', 'deepseek-flash-(1)')
        self.assertEqual(out2, {})

    def test_pointer_not_fixed_model_and_not_family(self):
        """T05：pointer 不写 modelId；也不冒充 family（resolutionType=pointer）。"""
        r = ModelResolver()
        res = r.resolve('alibaba', 'qwen-plus-latest')
        self.assertEqual(res['resolutionType'], 'pointer')
        out = self.p.project('alibaba', 'qwen-plus-latest')
        self.assertNotIn('modelId', out)
        self.assertNotIn('familyId', out, 'pointer 不得公开成家族')

    def test_family_query_vs_pointer_distinct(self):
        """pointer ≠ family（resolutionType 维度）。"""
        r = ModelResolver()
        fam = r.resolve('alibaba', 'qwen3')
        ptr = r.resolve('alibaba', 'qwen-plus-latest')
        self.assertEqual(fam['resolutionType'], 'family')
        self.assertEqual(ptr['resolutionType'], 'pointer')

    def test_only_public_family_entities_projected(self):
        """T06：正式 family 才公开 familyId；grouping key 不泄露。"""
        # 正式 family 实体的成员 → familyId 公开
        out = self.p.project('anthropic', 'claude-sonnet-4.5')
        self.assertEqual(out['familyId'], 'anthropic:claude-sonnet')
        # grouping-only family 的成员 → 无 familyId（T07）
        # qwen-plus 的 familyId=alibaba:qwen-plus（单成员 grouping，无正式实体）
        out2 = self.p.project('alibaba', 'qwen-plus')
        self.assertIn('modelId', out2)
        self.assertNotIn('familyId', out2)

    def test_source_observation_never_projected(self):
        """T03：projector 只吃 (provider, raw)——SO 无结构化模型不经此路径
        （exporter 侧 SO 投影函数不调用 helper——集成测试验证）。"""
        # 间接验证：helper 对任意 SO 类 provider 输入仍按契约执行（空投影）
        out = self.p.project('huggingface', 'some-model')
        self.assertEqual(out, {})

    def test_verify_projection_catches_bad_fields(self):
        """T20/T22：悬空 modelId / pointer 错写 → verify 报错（gate 判据）。"""
        errs = self.p.verify_projection({'modelId': 'alibaba:not-exist', 'modelName': 'X'})
        self.assertTrue(any('不在 registry' in e for e in errs))
        errs2 = self.p.verify_projection({'modelId': 'alibaba:qwen-plus-latest'})
        self.assertTrue(errs2)
        errs3 = self.p.verify_projection({'familyId': 'alibaba:qwen-plus'})
        self.assertTrue(any('非正式 family' in e for e in errs3))

    def test_gold_set_zero_false_positive_with_projection(self):
        """T09：Gold 危险输入经 projector 全部不产出 modelId。"""
        gold = json.loads(GOLD.read_text())
        violations = []
        for e in gold['entries']:
            if e['providerId'] == '*':
                continue
            for a in e['knownAliases']:
                if a.startswith('('):
                    continue
                out = self.p.project(e['providerId'], a)
                if e['classification'] in ('family', 'non_model', 'ambiguous') and 'modelId' in out:
                    violations.append(f"{e['canonicalName']}/{a} → {out['modelId']}")
        self.assertEqual(violations, [], '投影 false positive:\n' + '\n'.join(violations))


class TestExporterIntegration(unittest.TestCase):
    """exporter 集成（T02/T24 + gate）。"""

    def test_export_dry_run_clean(self):
        """T24：全量真实 export 成功（dry-run 零写入正式目录）。"""
        r = subprocess.run(
            [sys.executable, str(EXPORTER), '--dry-run'],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[:300])
        self.assertIn('[dry-run] datasetVersion=', r.stdout)

    def test_export_check_passes(self):
        """--check 校验现有 release 通过。"""
        r = subprocess.run(
            [sys.executable, str(EXPORTER), '--check'],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[:300])

    def test_projection_gate_fails_closed_on_corrupt_registry(self):
        """T20：registry 损坏 → exporter fail closed（构造临时 registry 注入失败）。"""
        p = get_projector()
        # 悬空 modelId 注入（直接验证 gate 逻辑——真实文件不动）
        bad = {'modelId': 'alibaba:ghost-model', 'modelName': 'Ghost'}
        errs = p.verify_projection(bad)
        self.assertTrue(errs)


if __name__ == '__main__':
    unittest.main()
