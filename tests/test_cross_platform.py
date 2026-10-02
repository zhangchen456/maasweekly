"""Official pricing dates/scenarios and explicit relationship gates."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
from pricing.base import ContentSnapshot
from pricing.adapters.vertex import VertexPricingExtractor
from pricing.adapters.google import GooglePricingExtractor
from pricing.normalize import normalize_and_validate
from pricing.archive import verify_evidence_for_fact
from public_export.cross_platform import load, validate, annotate
from public_export.loaders import ExportError

RAW=(ROOT/'docs/operations/cross-platform-2026-10-02/evidence/cloud-pricing.html').read_text()
def snapshot(provider, day='2026-10-02', raw=RAW):
    sha=hashlib.sha256(raw.encode()).hexdigest()
    return ContentSnapshot('snap-'+sha[:24],provider+':pricing','https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing',datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp(),200,'text/html',sha,raw)

class CrossPlatformTests(unittest.TestCase):
    def test_actual_cloud_table_separates_platform_regions_and_tiers(self):
        google=VertexPricingExtractor('vertex-google').extract(snapshot('vertex-google'))
        claude=VertexPricingExtractor('vertex-anthropic').extract(snapshot('vertex-anthropic'))
        for result in [google,claude]:
            report=normalize_and_validate(result)
            self.assertFalse(report.rejected)
            self.assertEqual(len(result.price_facts),len({f.fact_key for f in result.price_facts}))
            self.assertTrue(all(f.evidence_id in {e.evidence_id for e in result.evidence} for f in result.price_facts))
        ev={e.evidence_id:e.excerpt for e in claude.evidence}
        for f in claude.price_facts:
            fact={'provider_id':f.provider_id,'model_key':f.model_key,'amount':f.amount,
                  'currency':f.currency,'unit_quantity':f.unit_quantity,'unit_name':f.unit_name}
            self.assertEqual(verify_evidence_for_fact(ev[f.evidence_id],fact)[0], 'complete')
            self.assertEqual(verify_evidence_for_fact(ev[f.evidence_id].replace('Claude','Other'),fact)[0], 'partial')
        g={(f.component,f.region,f.service_tier,f.context_band.min_input_tokens):f.amount for f in google.price_facts}
        self.assertEqual(g['input','global','standard',0],'0.750000')
        self.assertEqual(g['output','global','standard',0],'3.750000')
        self.assertEqual(g['input','non-global','standard',0],'0.825000')
        self.assertEqual(g['input','global','priority',0],'1.350000')
        self.assertEqual({f.model_key for f in google.price_facts},{'gemini-3.8-flash'})
        writes=[f for f in claude.price_facts if f.component=='cache_write' and f.model_key=='claude-sonnet-5.5' and f.region=='global' and f.billing_mode=='realtime' and f.context_band.min_input_tokens==0]
        self.assertEqual({f.time_condition.schedule for f in writes},{'PT5M','PT1H'})
        self.assertEqual(len({f.fact_key for f in writes}),2)

    def test_promotional_end_and_future_start_are_resolved_by_snapshot_date(self):
        current=VertexPricingExtractor('vertex-google').extract(snapshot('vertex-google','2026-12-31'))
        future=VertexPricingExtractor('vertex-google').extract(snapshot('vertex-google','2027-01-01'))
        def standard(result):return next(f for f in result.price_facts if f.component=='input' and f.region=='global' and f.service_tier=='standard' and f.context_band.min_input_tokens==0)
        self.assertEqual(standard(current).amount,'0.750000')
        self.assertEqual(standard(future).amount,'1.500000')
        self.assertIsNone(standard(future).time_condition)

    def test_same_model_platform_facts_do_not_collide_and_unknown_tabs_fail_closed(self):
        from pricing.adapters.common import _make_fact
        snap=snapshot('google')
        direct=_make_fact(snap,'e','google','Gemini 3.8 Flash','input','realtime',('0.750000','USD',1000000),region='global')
        cloud=_make_fact(snap,'e','vertex-google','Gemini 3.8 Flash','input','realtime',('0.750000','USD',1000000),region='global')
        self.assertNotEqual(direct.fact_key,cloud.fact_key)
        raw=RAW.replace('Standard Model','Unverified Standard').replace('>Priority<','>Unverified Priority<').replace('Flex/Batch','Unverified Batch')
        result=VertexPricingExtractor('vertex-google').extract(snapshot('vertex-google',raw=raw))
        self.assertEqual(result.price_facts,[])
        self.assertTrue(result.warnings)

    def test_relationship_foreign_keys_and_evidence_are_mandatory(self):
        models=[{'modelId':m['modelId'],'modelName':m['canonicalName']} for m in json.loads((ROOT/'data/model-registry/models.json').read_text())['models'] if m['classification']=='model']
        catalog={'models':models,'families':[]};relations,mapping=load(ROOT,catalog)
        self.assertEqual(len(relations['availabilities']),6)
        self.assertEqual(validate({**catalog,**relations}),[])
        broken=deepcopy(relations);broken['availabilities'][0]['upstreamModelId']='google:lookalike'
        self.assertTrue(validate({**catalog,**broken}))
        broken=deepcopy(relations);broken['upstreamModels'][0].pop('evidence')
        self.assertTrue(validate({**catalog,**broken}))
        self.assertEqual(validate(catalog),[])  # historical catalog
        price={'id':'unchanged','factKey':'unchanged','sourceId':'google-vertex-pricing','modelKey':'gemini-3.8-flash','modelId':'google:gemini-3.8-flash'}
        annotate([price],mapping)
        self.assertEqual(price['platformId'],'google-vertex-ai')
        self.assertEqual((price['id'],price['factKey']),('unchanged','unchanged'))
        unknown={**price,'modelKey':'gemini-3.8-flash-preview'}
        for key in ['platformId','upstreamModelId','availabilityId']:unknown.pop(key)
        annotate([unknown],mapping);self.assertNotIn('platformId',unknown)

if __name__=='__main__':unittest.main()
