import hashlib
import importlib.util
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
from english_translation import collect_texts, projected_texts, protect, restore_and_validate, text_key, PROMPT_VERSION, normalize_terms

class EnglishTranslationTests(unittest.TestCase):
    def test_scope_excludes_original_evidence_and_identity(self):
        data={'highlights':[{'platform':'中文厂商','logo_summary':'新增模型','items':[{'text':'模型上线'}]}],
              'changed':[{'llm_summary':'信源解读','added_lines':['原始证据'],'signal_preview':'原文预览','url':'https://example.com/中文'}],
              'sourceSummaries':{'id':'补充解读'}}
        self.assertEqual(collect_texts(data),{'新增模型','模型上线','信源解读','补充解读'})

    def test_protection_units_identifiers_dates(self):
        source='10月5日，gpt-6.1-sol 使用 thinking_budget；输入 $12/MTok，超过10万 tokens。'
        masked, values=protect(source)
        self.assertFalse(any(value in masked for value in ['thinking_budget','$12/MTok','100000','October 5']))
        translated='On '+masked.split('，',1)[0]+', '+ ' '.join(token for token in values if token != next(iter(values)))+'.'
        restored=restore_and_validate(source,translated,values)
        self.assertIn('thinking_budget',restored);self.assertIn('$12/MTok',restored);self.assertIn('100000',restored)

    def test_missing_changed_or_invented_numbers_rejected(self):
        source='输入价格 $12/MTok'; masked,values=protect(source)
        tokens=' '.join(values)
        self.assertRaises(ValueError,restore_and_validate,source,'Input '+tokens+' 99',values)
        self.assertRaises(ValueError,restore_and_validate,source,'Input '+tokens+' '+tokens,values)
        self.assertRaises(ValueError,restore_and_validate,source,'Input pricing $12/MTok',values)
        self.assertRaises(ValueError,restore_and_validate,source,'输入 '+tokens,values)

    def test_chinese_discount_percentages_preserve_pricing_facts(self):
        for discount, percent in [('五折', '50%'), ('七五折', '75%'), ('九五折', '95%')]:
            with self.subTest(discount=discount):
                source=f'MiniMax输入tokens永久{discount}，优先服务按1.5倍计费'
                _, values=protect(source)
                self.assertEqual(list(values.values()), ['MiniMax', 'tokens', percent, '1.5'])
                raw='KEEP000TOKEN input KEEP001TOKEN permanently priced at KEEP002TOKEN; priority service billed at KEEP003TOKEN times the standard rate.'
                restored=restore_and_validate(source,raw,values)
                self.assertIn(percent,restored)
                self.assertIn('1.5',restored)
                self.assertRaises(ValueError,restore_and_validate,source,raw+' 99%',values)
                self.assertRaises(ValueError,restore_and_validate,source,raw.replace('KEEP002TOKEN','50%'),values)

    def test_uncertainty_and_removal_are_not_strengthened(self):
        source='LMArena 移除旧模型，或为更新。';_,values=protect(source);tokens=' '.join(values)
        self.assertRaises(ValueError,restore_and_validate,source,tokens+' retired models for updating.',values)
        self.assertIn('may',restore_and_validate(source,tokens+' removed models, which may support updating.',values))

    def test_cache_rejects_hash_mismatch_failed_and_old_prompt(self):
        source='今日要点';good={'source':source,'translation':'Today’s highlights','status':'success','promptVersion':PROMPT_VERSION}
        self.assertEqual(projected_texts({'entries':{text_key(source):good}}),{source:'Today’s highlights'})
        for bad in [{**good,'status':'failed'},{**good,'promptVersion':'old'},{**good,'source':'已修改内容'}]:
            self.assertEqual(projected_texts({'entries':{text_key(source):bad}}),{})

    def test_quantization_uses_the_technical_term(self):
        self.assertEqual(normalize_terms('新增量化版本','Added quantitative version'),'Added quantized version')
        self.assertEqual(normalize_terms('普通统计','quantitative analysis'),'quantitative analysis')
        self.assertEqual(normalize_terms('硅基流动下架 THUDM/GLM-4-32B-0414，新增 zai-org/GLM-5.3-Flash','SiliconFlow and THUDM are removed'),'SiliconFlow delisted THUDM/GLM-4-32B-0414 and added zai-org/GLM-5.3-Flash.')
        self.assertEqual(normalize_terms('更新时间更新至 10 月 8 日','Updated to 10 month 8 day'),'Updated to October 8')

    def test_negation_is_preserved(self):
        source='暂无价格，不能判断免费。'
        self.assertRaises(ValueError,restore_and_validate,source,'Pricing is available and the model is free.',{})
        self.assertIn('no',restore_and_validate(source,'There are no prices; this does not imply free service.',{}))

    def test_short_literal_retry_keeps_the_same_validation(self):
        spec=importlib.util.spec_from_file_location('translate_dynamic',ROOT/'pipeline/scripts/translate-dynamic-en.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        calls=[]
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):
                content='Reasoning tier names simplified' if len(calls)<4 else 'Claude Sonnet 5.5 reasoning tier names simplified'
                return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':content}}]}).encode()
        def response(request,timeout):calls.append(json.loads(request.data));return Reply()
        with patch.object(module.urllib.request,'urlopen',response),patch.object(module.time,'sleep'):
            entry=module.translate('Claude Sonnet 5.5 推理档位命名简化','fake-test-key','https://example.com','spark-x2.5-4b')
        self.assertEqual(len(calls),4);self.assertEqual(entry['status'],'success')
        self.assertIn('Claude Sonnet 5.5',entry['translation'])
        self.assertNotIn('fake-test-key',json.dumps(entry))

    def test_chinese_pricing_unit_never_restored_into_english(self):
        source='搜索超出后 $14/千次，图片 $0.1/张';_,values=protect(source)
        self.assertTrue(all(not any('\u3400'<=c<='\u9fff' for c in v) for v in values.values()))

if __name__=='__main__':unittest.main()
