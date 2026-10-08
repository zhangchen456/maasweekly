#!/usr/bin/env python3
"""Local admin flow against real API/SQLite with file outbox; no external email."""
import argparse
import base64
import functools
import http.client
import http.server
import runpy
import json
import os
import re
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--focus', choices=['all','delivery','problems','payments','coverage'], default='all')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='maas-admin-browser-') as private:
        private = Path(private)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            api_port = sock.getsockname()[1]
        umami={'fail':False}
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_): pass
            def proxy(self):
                connection = http.client.HTTPConnection('127.0.0.1', api_port, timeout=20)
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                headers = {k:v for k,v in self.headers.items() if k.lower() not in ('host','connection')}
                try:
                    connection.request(self.command, self.path, body=body, headers=headers)
                    response = connection.getresponse()
                    data = response.read()
                    self.send_response(response.status)
                    for key,value in response.getheaders():
                        if key.lower() not in ('transfer-encoding','connection','content-length'):
                            self.send_header(key,value)
                    self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
                finally: connection.close()
            def do_GET(self):
                if self.path.startswith('/mock-umami/'):
                    from urllib.parse import urlparse,parse_qs
                    url=urlparse(self.path)
                    data={'pageviews':{'value':12},'visitors':{'value':3},'visits':{'value':5}} if url.path.endswith('/stats') else [{'x':'/pro/' if parse_qs(url.query).get('type')==['path'] else 'https://example.test/source','y':4}]
                    payload=json.dumps(data).encode()
                    self.send_response(503 if umami['fail'] else 200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
                elif self.path.startswith('/api/'): self.proxy()
                else: super().do_GET()
            def do_POST(self): self.proxy()
        server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'site/dist')))
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        env = {**os.environ,'PORT':str(api_port),'HOST':'127.0.0.1','MAAS_DIAGNOSTICS':'0','RELOAD_INTERVAL_MS':'0',
            'MAAS_ACCOUNT_DB':str(private/'accounts.sqlite'),'MAAS_ACCOUNT_SECRET':'browser-test-secret-for-local-only-32-chars',
            'MAAS_ACCOUNT_ORIGIN':base,'MAAS_MAIL_MODE':'outbox','MAAS_MAIL_OUTBOX':str(private/'outbox'),
            'PUBLIC_DATA_ROOT':str(ROOT/'data/public/v1'),'MAAS_EDITORIAL_ALLOW_PAID':'false', 'MAAS_UMAMI_ENDPOINT':base+'/mock-umami','MAAS_UMAMI_TOKEN':'PRIVATE_UMAMI_BROWSER_TOKEN','MAAS_UMAMI_WEBSITE_ID':'local-test','MAAS_UMAMI_VERSION':'v3'}
        env['MAAS_PAYMENT_MODE']='simulator' if args.focus=='payments' else 'disabled';env.pop('MAAS_PAYMENT_WEBHOOK_SECRET',None)
        env.pop('MAAS_DIAGNOSTIC_CONFIG',None);env['MAAS_DIAGNOSTIC_ALLOW_PAID']='false';env.pop('MAAS_EDITORIAL_CONFIG',None);env.pop('OPENAI_API_KEY',None);env.pop('MAAS_RELEASE_DIR',None);env.pop('NODE_ENV',None)
        log = open(private/'api.log','w')
        api = subprocess.Popen(['node',str(ROOT/'services/agent-api/dist/server.js')],env=env,stdout=log,stderr=log)
        report = {'scope':'Local Chromium + real admin/account API/SQLite + private outbox; no external email','states':[], 'errors':[]}
        try:
            for _ in range(100):
                if api.poll() is not None: raise RuntimeError('Local API failed to start')
                try:
                    with socket.create_connection(('127.0.0.1',api_port),timeout=.1): break
                except OSError: time.sleep(.1)
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
                page=context.new_page();page.on('pageerror',lambda error:report['errors'].append(str(error)))
                page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                def login(address):
                    page.locator('#account-login-open').click()
                    page.locator('#account-mode-register').click()
                    page.locator('#account-login-email').fill(address)
                    page.locator('#account-global-send').click()
                    page.locator('#account-global-code-fields').wait_for(state='visible')
                    mails=[json.loads(f.read_text()) for f in (private/'outbox').glob('*.json')]
                    code=re.search(r'\b\d{6}\b',next(m for m in reversed(mails) if address in str(m['to']))['text'])[0]
                    page.locator('#account-login-code').fill(code)
                    page.locator('#account-global-verify').click()
                    page.locator('#account-login-password').fill('Local-preview-password-01')
                    page.locator('#account-password-confirm').fill('Local-preview-password-01')
                    page.locator('#account-global-verify').click()
                    page.locator('#account-user-menu').wait_for(state='visible')
                def cli(command, user):
                    subprocess.run(['node',str(ROOT/'services/agent-api/dist/admin-cli.js'),command,'--user-id',user,'--actor','browser-operator','--reason','isolated browser acceptance'],env=env,check=True,capture_output=True)
                page.goto(base+'/admin/')
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('请使用')")
                assert page.locator('#admin-private').is_hidden()
                report['states'].append('anonymous-login-entry')
                login('admin-preview@example.test')
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('无后台访问权限')")
                with sqlite3.connect(private/'accounts.sqlite') as db:
                    user=db.execute("SELECT id FROM users WHERE email=?",('admin-preview@example.test',)).fetchone()[0]
                cli('grant',user)
                page.locator('#admin-retry').click()
                page.locator('#admin-overview').wait_for(state='visible')
                assert '可用' in page.locator('#admin-overview').inner_text()
                page.screenshot(path=str(args.output/'admin-overview.png'),full_page=True)
                report['states'].append('existing-login-cli-grant-real-overview')
                page.goto(base+'/admin/audit/')
                page.locator('#admin-audit-items tr').wait_for(state='visible')
                assert 'admin.grant' in page.locator('#admin-audit-items').inner_text()
                page.locator('input[name=action]').fill('no-such-action')
                page.locator('#admin-audit-filter button').click()
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('没有符合')")
                page.locator('input[name=action]').fill('')
                page.locator('#admin-audit-filter button').click()
                page.locator('#admin-audit-items tr').wait_for(state='visible')
                page.screenshot(path=str(args.output/'admin-audit.png'),full_page=True)
                report['states'].append('audit-real-record-and-empty-filter')
                if args.focus in ('delivery','problems','payments','coverage'):
                    flow=args.focus
                    runpy.run_path(str(ROOT/f'scripts/admin-{flow}-browser-flow.py'))[flow+'_flow'](page,context,base,env,args.output,report,ROOT)
                    for artifact in (ROOT/'site/dist/admin').rglob('*.html'):
                        html=artifact.read_text()
                        assert user not in html and 'admin-preview@example.test' not in html and 'PRIVATE_MAIL_WITH_UNSUBSCRIBE' not in html
                        assert 'noindex' in html
                    assert not report['errors'],report['errors']
                    context.close();browser.close()
                    (args.output/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                    print(json.dumps(report,ensure_ascii=False))
                    return

                # T02 real user/feedback workflow through the actual static pages and API.
                page.goto(base+'/admin/users/')
                page.locator('#ops-items article').wait_for(state='visible')
                page.locator('#ops-filter input[name=q]').fill('admin-preview')
                page.locator('#ops-filter button').click()
                page.wait_for_function("document.querySelector('#ops-items').children.length===1")
                page.locator('#ops-items article a').click()
                page.wait_for_function("document.querySelector('#ops-status').textContent.includes('已加载')")
                entitlement=page.locator('#ops-entitlement')
                entitlement.locator('[name=starts]').fill('2026-01-01T00:00:00Z')
                entitlement.locator('[name=ends]').fill('2027-01-01T00:00:00Z')
                entitlement.locator('[name=reason]').fill('isolated manual grant')
                entitlement.locator('button').click()
                page.wait_for_function("document.querySelector('#ops-status').textContent.includes('操作已提交')")
                page.screenshot(path=str(args.output/'admin-user-detail.png'),full_page=True)
                try:
                    runpy.run_path(str(ROOT/'scripts/admin-weekly-browser-flow.py'))['weekly_flow'](page,context,base,env,args.output,report,ROOT)
                except Exception:
                    page.screenshot(path=str(args.output/'weekly-error.png'),full_page=True)
                    (args.output/'weekly-error.txt').write_text(page.locator('body').inner_text())
                    raise
                runpy.run_path(str(ROOT/'scripts/admin-analytics-browser-flow.py'))['analytics_flow'](page,context,base,env,args.output,report,ROOT,umami)
                runpy.run_path(str(ROOT/'scripts/admin-monitor-browser-flow.py'))['monitor_flow'](page,context,base,env,args.output,report,ROOT)
                page.goto(base+'/admin/users/detail/?id='+user)
                page.wait_for_function("document.querySelector('#ops-status').textContent.includes('已加载')")
                image=page.screenshot()
                response=context.request.post(base+'/api/account/feedback',headers={'Origin':base},data={'title':'T02 isolated code issue','description':'Reproducible problem checked against the real isolated admin workflow.','images':[{'mime':'image/png','data':base64.b64encode(image).decode()}]})
                assert response.status==201,response.text()
                feedback_id=response.json()['id']
                page.locator('#ops-feedback-link').click()
                page.locator('#ops-items article a').wait_for(state='visible')
                page.locator('#ops-items article a').click()
                page.wait_for_function("document.querySelector('#ops-status').textContent.includes('已加载')")
                assert context.request.get(base+f'/api/admin/feedback/{feedback_id}/images/0').status==200
                page.wait_for_function("document.querySelector('#ops-images img')?.naturalWidth>0")
                stale=context.new_page()
                stale.on('pageerror',lambda error:report['errors'].append(str(error)))
                stale.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                stale.goto(base+f'/admin/feedback/detail/?id={feedback_id}')
                stale.wait_for_function("document.querySelector('#ops-status').textContent.includes('已加载')")
                notes=page.locator('form[data-action=notes]')
                notes.locator('[name=body]').fill('PRIVATE T02 INTERNAL NOTE')
                notes.locator('[name=reason]').fill('isolated triage')
                notes.locator('button').click()
                page.wait_for_function("document.querySelector('#ops-notes').textContent.includes('PRIVATE T02')")
                stale.locator('#ops-update [name=publicReply]').fill('stale reply must not overwrite')
                stale.locator('#ops-update [name=reason]').fill('isolated stale window')
                stale.locator('#ops-update button').click()
                stale.wait_for_function("document.querySelector('#ops-status').textContent.includes('对象已更新')")
                stale.close()
                report['states'].append('T02-two-browser-windows-version-conflict')
                update=page.locator('#ops-update')
                update.locator('[name=stage]').select_option('resolved')
                update.locator('[name=resolutionType]').select_option('code')
                update.locator('[name=publicReply]').fill('公开处理说明：修复已发布并通过线上验证。')
                update.locator('[name=reason]').fill('attempt without validation')
                update.locator('button').click()
                page.wait_for_function("document.querySelector('#ops-status').textContent.includes('缺少通过')")
                verification=page.locator('form[data-action=verify]')
                verification.locator('[name=artifactRef]').fill('commit-isolated-demo')
                verification.locator('[name=releaseRef]').fill('rl-isolated-demo')
                verification.locator('[name=note]').fill('Isolated acceptance fixture: deployed behavior verified; not a real production release.')
                verification.locator('[name=reason]').fill('isolated verification record')
                verification.locator('button').click()
                page.wait_for_function("document.querySelector('#ops-verifications').textContent.includes('rl-isolated-demo')")
                update.locator('[name=stage]').select_option('resolved')
                update.locator('[name=resolutionType]').select_option('code')
                update.locator('[name=publicReply]').fill('公开处理说明：修复已发布并通过线上验证。')
                update.locator('[name=reason]').fill('isolated resolve')
                update.locator('button').click()
                page.wait_for_function("document.querySelector('#ops-status').textContent.includes('操作已提交') && document.querySelector('#ops-items').textContent.includes('resolved')")
                page.screenshot(path=str(args.output/'admin-feedback-detail.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert update.locator('button').is_visible()
                assert verification.locator('button').is_visible()
                page.screenshot(path=str(args.output/'admin-feedback-mobile.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})
                report['states'].append('T02-user-search-grant-private-image-note-public-reply-verification-resolve')
                page.goto(base+'/admin/audit/')
                page.locator('#admin-audit-items tr').first.wait_for(state='visible')
                page.set_viewport_size({'width':390,'height':844})
                assert page.locator('#admin-audit-filter button').is_visible()
                page.screenshot(path=str(args.output/'admin-mobile.png'),full_page=True)
                cli('revoke',user)
                page.locator('#admin-retry').click()
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('无后台访问权限')")
                assert page.locator('#admin-audit-items').inner_text()==''
                page.goto(base+'/feedback/')
                page.locator('#feedback-history').wait_for(state='visible')
                page.wait_for_function("document.querySelector('#feedback-history').textContent.includes('公开处理说明')")
                assert 'PRIVATE T02' not in page.locator('#feedback-history').inner_text()
                assert context.request.get(base+f'/api/admin/feedback/{feedback_id}/images/0').status==403
                assert context.request.get(base+f'/api/account/feedback/{feedback_id}/image/0').status==200
                page.screenshot(path=str(args.output/'user-feedback-result.png'),full_page=True)
                report['states'].append('T02-ordinary-owner-sees-public-result-without-internal-note')
                cli('grant',user)
                page.goto(base+'/admin/audit/')
                page.wait_for_function("document.querySelector('#admin-audit-items').children.length>0")
                page.locator('#account-user-menu summary').click()
                page.locator('#account-sign-out').click()
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('请使用')")
                assert page.locator('#admin-private').is_hidden()
                assert page.locator('#admin-audit-items').inner_text()==''
                report['states'].append('revocation-and-logout-clear-private-dom')
                login('free-preview@example.test')
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('无后台访问权限')")
                response=context.request.post(base+'/api/pro/beta',headers={'Origin':base},data={})
                assert response.status==200 and response.json()['entitlement']['status']=='active'
                page.locator('#admin-retry').click()
                page.wait_for_function("document.querySelector('#admin-status').textContent.includes('无后台访问权限')")
                assert page.locator('#admin-private').is_hidden()
                assert context.request.get(base+f'/api/account/feedback/{feedback_id}/image/0').status==404
                report['states'].append('free-plus-no-admin-permission')
                for artifact in (ROOT/'site/dist/admin').rglob('*.html'):
                    html=artifact.read_text()
                    assert 'admin-preview@example.test' not in html and user not in html and 'PRIVATE T02 INTERNAL NOTE' not in html
                    assert 'noindex' in html
                assert not report['errors'],report['errors']
                context.close();browser.close()
        except Exception as error:
            report['errors'].append(str(error))
            (args.output/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            raise
        finally:
            api.terminate()
            try:api.wait(timeout=5)
            except subprocess.TimeoutExpired:api.kill();api.wait()
            log.close();server.shutdown();server.server_close()
        (args.output/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
