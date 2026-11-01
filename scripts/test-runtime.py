#!/usr/bin/env python3
"""One fixture-based gate for PRs and release packages; production data is never required."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PYTHON=['shadow_store','shadow_transfer','shadow_verification','data_publication','database_writer','weekly_publishing','blob_storage','import_memory','runtime_control','runtime_package','runtime_cleanup','workflow_release_contract','standard_inputs','english_translation','pipeline_runtime','current_pricing','price_archive','source_fetch','source_identity','arena_source','arena_projection','cross_platform','developer_platform_registry','model_public_projection.TestProjectionContract','model_registry.TestProviderMap','public_export','public_retention','monitor_collection','formal_weekly_health','reliability']
SITE=['english-completeness','private-translation-refresh','account-password','admin-analytics-export','analytics','feedback','pro-scope','theme-preference','time-display','workspace-analytics','workspace-currency','workspace-share']
def run(args,cwd=ROOT):
 print('+ '+' '.join(map(str,args)),flush=True);subprocess.run(args,cwd=cwd,check=True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--suite',choices=['all','python','api','site'],default='all');ap.add_argument('--require-postgres',action='store_true');a=ap.parse_args()
 if (a.require_postgres or os.environ.get('CI')=='true') and not os.environ.get('MAAS_SHADOW_TEST_DSN'):raise SystemExit('PostgreSQL integration is required in CI')
 if a.suite in ('all','python'):
  run([sys.executable,'scripts/generate-public-contract.py','--check'])
  for name in PYTHON:
   run([sys.executable,'-m','unittest',f'test_{name}'],ROOT/'tests')
  run([sys.executable,'tests/test_pricing_extractors.py'])
 if a.suite in ('all','api'):
  run(['node','scripts/ensure-node-deps.mjs','services/agent-api']);run(['npm','run','build'],ROOT/'services/agent-api')
  files=sorted(str(p.relative_to(ROOT/'services/agent-api')) for p in (ROOT/'services/agent-api/dist/tests').glob('*.test.js') if p.name not in {'real.test.js','mcp-real.test.js'})
  run(['node','--test','--test-force-exit',*files],ROOT/'services/agent-api')
 if a.suite in ('all','site'):
  run(['node','scripts/ensure-node-deps.mjs','site'])
  run(['node','--test',*[f'tests/{name}.test.mjs' for name in SITE]],ROOT/'site')
  run(['npm','run','build:runtime'],ROOT/'site')
 print(json.dumps({'gate':'runtime','suite':a.suite,'postgresConfigured':bool(os.environ.get('MAAS_SHADOW_TEST_DSN')),'status':'passed'}))
if __name__=='__main__':main()
