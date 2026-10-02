"""Official 2026-10-02 table shapes: preserve scenarios and component meaning."""
import dataclasses
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.pricing.base import ContentSnapshot
from pipeline.pricing.extractors import get_extractor
from pipeline.pricing.normalize import normalize_and_validate
from pipeline.pricing.archive import verify_evidence_for_fact, html_excerpt_to_text

class CurrentPricingTests(unittest.TestCase):
    def extract(self, provider, observed=1790899200):
        raw = (Path(__file__).parent / 'fixtures/pricing' / f'{provider}_pricing_2026-10-02.html').read_text()
        sha = hashlib.sha256(raw.encode()).hexdigest()
        snap = ContentSnapshot('snap-' + sha[:24], provider + ':pricing', 'https://official.example/pricing', observed, 200, 'text/html', sha, raw, 'playwright-1')
        result = get_extractor(snap.source_key).extract(snap)
        self.assertFalse(normalize_and_validate(result).rejected)
        return result

    def prices(self, result, model, **conditions):
        return {f.component: f for f in result.price_facts if f.model_key == model and all(getattr(f,k) == v for k,v in conditions.items())}

    def test_openai_context_and_service_tiers(self):
        r = self.extract('openai')
        for tier, amount in [('standard','10.000000'),('flex','5.000000'),('fast','20.000000'),('ultrafast','60.000000')]:
            f = next(f for f in r.price_facts if f.model_key == 'gpt-6-astra' and f.component == 'input' and f.service_tier == tier and f.billing_mode == 'realtime' and f.context_band.min_input_tokens == 0)
            self.assertEqual(f.amount, amount)
            self.assertEqual(f.context_band.max_input_tokens,272000)
        long = next(f for f in r.price_facts if f.model_key == 'gpt-6-astra' and f.component == 'input' and f.service_tier == 'standard' and f.billing_mode == 'realtime' and f.context_band.min_input_tokens == 272001)
        self.assertEqual(long.amount,'20.000000')
        self.assertTrue(any(f.billing_mode == 'batch' for f in r.price_facts))
        evidence = {e.evidence_id:e for e in r.evidence}
        self.assertEqual(verify_evidence_for_fact(html_excerpt_to_text(evidence[long.evidence_id].excerpt),dataclasses.asdict(long))[0],'complete')

    def test_anthropic_multilevel_header_and_body_heading(self):
        r=self.extract('anthropic')
        for model, inp, out in [('claude-opus-5.5','4.000000','20.000000'),('claude-sonnet-5.5','2.000000','10.000000')]:
            p=self.prices(r,model)
            self.assertEqual(p['input'].amount,inp);self.assertEqual(p['output'].amount,out)
        writes=[f for f in r.price_facts if f.model_key=='claude-opus-5.5' and f.component=='cache_write']
        self.assertEqual({f.time_condition.period for f in writes},{'cache_write_5m','cache_write_1h'})

    def test_kimi_header_mapping_with_cache_write_columns(self):
        r=self.extract('kimi');p=self.prices(r,'kimi-k3')
        self.assertEqual(p['input'].amount,'20.000000');self.assertEqual(p['output'].amount,'100.000000');self.assertEqual(p['cache_read'].amount,'2.000000')
        self.assertEqual(len([f for f in r.price_facts if f.model_key=='kimi-k3' and f.component=='cache_write']),2)
        self.assertEqual(self.prices(r,'kimi-k2.7-code')['input'].amount,'6.500000')

    def test_deepseek_footnote_and_utc_schedule(self):
        r=self.extract('deepseek');p=self.prices(r,'deepseek-flash')
        self.assertEqual(p['input'].amount,'0.300000')
        self.assertEqual(p['input'].time_condition.tz,'UTC')
        self.assertIn('Monday through Friday',p['input'].time_condition.schedule)
        self.assertEqual(self.prices(r,'deepseek-v4-pro')['input'].amount,'1.320000')

    def test_doubao_standard_priority_flex_and_batch(self):
        r=self.extract('doubao')
        for mode,tier,amount in [('realtime','standard','3.000000'),('realtime','priority','6.000000'),('realtime','flex','1.500000'),('batch','standard','1.500000')]:
            p=self.prices(r,'doubao-seed-2.1-turbo',billing_mode=mode,service_tier=tier)
            self.assertEqual(p['input'].amount,amount)
        self.assertEqual(self.prices(r,'doubao-seed-2.1-pro',billing_mode='realtime',service_tier='standard')['input'].amount,'6.000000')

    def test_google_context_and_cache_read_not_hourly_storage(self):
        r=self.extract('google')
        p={f.component:f for f in r.price_facts if f.model_key=='gemini-3.1-pro-preview' and f.context_band.min_input_tokens==0}
        self.assertEqual(p['input'].amount,'2.000000');self.assertEqual(p['output'].amount,'12.000000');self.assertEqual(p['cache_read'].amount,'0.200000')
        self.assertEqual(self.prices(r,'gemini-3.8-flash')['cache_read'].amount,'0.075000')
        self.assertEqual(self.prices(r,'gemini-3.8-flash')['input'].time_condition.schedule,'through December 31, 2026')
        future=self.extract('google',1801440000)
        self.assertEqual(self.prices(future,'gemini-3.8-flash')['input'].amount,'1.500000')
        self.assertIsNone(self.prices(future,'gemini-3.8-flash')['input'].time_condition)

if __name__=='__main__':unittest.main()
