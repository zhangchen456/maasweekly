"""T03 isolated UI flow, called by the shared admin acceptance. No paid calls."""
import json
import subprocess
from pathlib import Path

def weekly_flow(page, context, base, env, output, report, root):
    local_env = {**env, 'MAAS_EDITORIAL_ALLOW_PAID':'false'}
    local_env.pop('MAAS_EDITORIAL_CONFIG',None)
    local_env.pop('OPENAI_API_KEY',None)
    page.goto(base+'/admin/weekly/')
    page.wait_for_function("document.querySelector('#weekly-status').textContent.includes('尚无')")
    form=page.locator('#weekly-create')
    form.locator('[name=periodEnd]').fill('2026-09-28')
    form.locator('[name=selection]').fill('核对真实历史观察，模拟模型只验收工作流')
    form.locator('[name=budget]').fill('0')
    form.locator('[name=reason]').fill('T03隔离历史演练')
    form.locator('button').click()
    page.wait_for_function("document.querySelector('#weekly-summary')?.textContent.includes('2026-09-28')")
    page.locator('#weekly-reason').fill('隔离演练操作')
    page.locator('#weekly-prepare [name=coverageNote]').fill('历史数据覆盖受限；不能据此确认全市场变化或模型性能')
    if env.get('MAAS_COVERAGE_TEST'):
        page.locator('#weekly-prepare [name=coverage]').select_option('normal')
        page.locator('#weekly-prepare button').click()
        page.wait_for_function("document.querySelector('#weekly-status').textContent.includes('同窗口相关来源')")
        page.locator('#weekly-prepare [name=coverage]').select_option('partial')
        page.locator('#weekly-prepare button').click()
        page.wait_for_function("document.querySelector('#weekly-status').textContent.includes('同窗口相关来源')")
        assert 'google-vertex-changelog' in page.locator('#weekly-monitor').inner_text()
        assert 'projectionConflict' in page.locator('#weekly-monitor').inner_text()
        page.screenshot(path=str(output/'coverage-conflict.png'),full_page=True)
        page.locator('#weekly-monitor-ack').check()
    page.locator('#weekly-prepare button').click()
    page.wait_for_function("document.querySelector('#weekly-inputs').children.length>0")
    for stage in ('prepare','curate','analyze','verify'):
        page.locator(f'[data-stage={stage}]').click()
        page.wait_for_function(f"document.querySelector('#weekly-runs').textContent.includes('{stage} · queued')")
        subprocess.run(['node',str(root/'services/agent-api/dist/editorial-worker.js'),'--once'],env=local_env,check=True,capture_output=True)
        page.locator('#weekly-refresh').click()
        page.wait_for_function(f"document.querySelector('#weekly-runs').textContent.includes('{stage} · succeeded')")
    pack=json.loads(page.locator('#weekly-package').input_value())
    assert [c['kind'] for c in pack['contents']]==['briefing','explainer']
    # Real manual edit, with explicit limits; do not claim the simulation is a quality evaluation.
    for c in pack['contents']:
        c['body']+='\n\n编辑复核：本演练确认记录ID、URL、观察时间与冻结快照一致。未验证官方生效时间、价格比较、模型性能；本稿不能作为商业质量验收。'
    page.locator('#weekly-package').fill(json.dumps(pack,ensure_ascii=False,indent=2))
    page.locator('#weekly-save button').click()
    page.wait_for_function("document.querySelector('#weekly-summary').textContent.includes('稿件r2')")
    page.locator('#weekly-review-form [name=note]').fill('核对8条冻结引用与公开预览，保留模拟/历史覆盖限制')
    page.locator('#weekly-review-form button[value=submit]').click()
    page.wait_for_function("document.querySelector('#weekly-summary').textContent.includes('in_review')")
    for field in ('sources','conditions','conclusions','coverage','preview','attribution'):
        page.locator(f'#weekly-review-form [name={field}]').check()
    page.locator('#weekly-review-form button[value=approve]').click()
    page.wait_for_function("document.querySelector('#weekly-summary').textContent.includes('approved')")
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1'), 'editorial desktop overflow'
    page.screenshot(path=str(output/'weekly-approved.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1'), 'editorial mobile overflow'
    page.screenshot(path=str(output/'weekly-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#weekly-publish').click()
    page.wait_for_function("document.querySelector('#weekly-summary').textContent.includes('published')")
    page.locator('#weekly-compose').click()
    page.wait_for_function("document.querySelector('#weekly-publications').textContent.includes('succeeded')")
    page.screenshot(path=str(output/'weekly-published.png'),full_page=True)
    cid=pack['contents'][0]['id']
    detail=context.request.get(base+'/api/admin/weekly/weekly-2026-09-28').json()
    assert len(detail['publications'])==1
    assert detail['composition']['mail']==[]
    response=context.request.get(base+'/api/pro/catalog')
    assert '编辑复核' not in response.text()
    page.goto(base+'/pro/weekly/?id='+cid)
    page.wait_for_function("document.querySelector('#weekly-reader-status').textContent.includes('Plus 全文')")
    assert '编辑复核' in page.locator('#weekly-reader-body').inner_text()
    assert page.locator('#weekly-reader-body script').count()==0
    page.screenshot(path=str(output/'weekly-plus.png'),full_page=True)
    # Anonymous receives only preview from the same actual page/API.
    visitor=context.browser.new_context()
    try:
        free=visitor.new_page()
        free.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
        free.goto(base+'/pro/weekly/?id='+cid)
        free.wait_for_function("document.querySelector('#weekly-reader-status').textContent.includes('公共预览')")
        assert free.locator('#weekly-reader-body').inner_text()==''
        free.screenshot(path=str(output/'weekly-preview.png'),full_page=True)
    finally:
        visitor.close()
    (output/'weekly-evidence.json').write_text(json.dumps({'datasetVersion':detail['issue']['datasetVersion'],'inputHash':detail['issue']['inputHash'],'revision':detail['revision']['revision'],'outputHash':detail['revision']['outputHash'],'evidence':pack['contents'][0]['evidence'],'runs':detail['runs'],'publication':detail['publications'],'modelQuality':'Not evaluated: deterministic simulation only','cost':'Unknown price; no paid calls'},ensure_ascii=False,indent=2))
    report['states'].append('T03-real-history-create-freeze-stage-worker-edit-review-publish-compose-plus-preview')
