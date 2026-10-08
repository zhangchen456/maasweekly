"""D01 focused local T05->T03 UI test. Imports synthetic monitoring, never fetches."""
import json
import runpy
import subprocess
from pathlib import Path

def coverage_flow(page,context,base,env,output,report,root):
    assert context.request.post(base+'/api/pro/beta',headers={'Origin':base},data={}).status==200
    at=1790503200000
    inbox=Path(env['MAAS_ACCOUNT_DB']).parent/'coverage-inbox';inbox.mkdir()
    record={'schemaVersion':1,'batchId':'d01-browser-failed','sources':[{'id':'google-vertex-changelog','name':'D01 isolated Google Vertex','platform':'google','kind':'changelog','budgetHours':48}], 'runs':[{'id':'d01-browser-run','kind':'prices','trigger':'manual','state':'failed','stage':'fetch','startedAt':at,'finishedAt':at+60000,'observedAt':at+60000,'inputVersion':None,'outputVersion':None,'result':'failed','validation':'unknown','publication':'not_run','errorCode':'fetch_failed','runLink':None,'sources':[{'sourceId':'google-vertex-changelog','attemptAt':at,'successAt':None,'dataThrough':None,'outcome':'fetch_failed','coverage':'missing','errorCode':'fetch_failed'}]}]}
    file=inbox/'d01.json';file.write_text(json.dumps(record))
    subprocess.run(['node',str(root/'services/agent-api/dist/monitor-cli.js'),'import',file.name],env={**env,'MAAS_MONITOR_INBOX':str(inbox.resolve())},check=True,capture_output=True)
    runpy.run_path(str(root/'scripts/admin-weekly-browser-flow.py'))['weekly_flow'](page,context,base,{**env,'MAAS_COVERAGE_TEST':'true'},output,report,root)
    report['states'].append('D01-T05-related-failure-normal-rejected-partial-acknowledged-publication')
