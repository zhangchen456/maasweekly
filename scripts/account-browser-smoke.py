#!/usr/bin/env python3
"""Local account flow against real API/SQLite with file outbox; no external email."""
import argparse
import functools
import http.client
import http.server
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
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='maas-account-browser-') as private:
        private = Path(private)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            api_port = sock.getsockname()[1]
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
                if self.path.startswith('/api/'): self.proxy()
                else: super().do_GET()
            def do_POST(self): self.proxy()
        server = http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'site/dist')))
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        env = {**os.environ,'PORT':str(api_port),'HOST':'127.0.0.1','MAAS_DIAGNOSTICS':'0','RELOAD_INTERVAL_MS':'0',
            'MAAS_ACCOUNT_DB':str(private/'accounts.sqlite'),'MAAS_ACCOUNT_SECRET':'browser-test-secret-for-local-only-32-chars',
            'MAAS_ACCOUNT_ORIGIN':base,'MAAS_MAIL_MODE':'outbox','MAAS_MAIL_OUTBOX':str(private/'outbox'),
            'PUBLIC_DATA_ROOT':str(ROOT/'data/public/v1')}
        env.pop('MAAS_RELEASE_DIR',None);env.pop('NODE_ENV',None)
        log = open(private/'api.log','w')
        api = subprocess.Popen(['node',str(ROOT/'services/agent-api/dist/server.js')],env=env,stdout=log,stderr=log)
        report = {'scope':'Local Chromium + real account API/SQLite + private outbox; no external email','states':[], 'errors':[]}
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
                def login(page, address):
                    page.locator('#account-login-open').click()
                    page.locator('#account-login-email').fill(address)
                    page.locator('#account-global-send').click()
                    page.locator('#account-global-code-fields').wait_for(state='visible')
                    mails=[json.loads(f.read_text()) for f in (private/'outbox').glob('*.json')]
                    mail=next(m for m in reversed(mails) if address in str(m['to']))
                    code=re.search(r'\b\d{6}\b',mail['text'])[0]
                    page.locator('#account-login-code').fill(code)
                    page.locator('#account-global-verify').click()
                    page.locator('#account-user-menu').wait_for(state='visible')
                page.goto(base+'/')
                page.locator('#account-login-open').wait_for(state='visible')
                page.locator('#account-login-open').click()
                bounds=page.locator('#account-login-dialog').bounding_box()
                assert abs(bounds['x']+bounds['width']/2-720)<2 and abs(bounds['y']+bounds['height']/2-500)<2
                page.screenshot(path=str(args.output/'login-desktop.png'),full_page=False)
                page.locator('#account-login-close').click()
                page.set_viewport_size({'width':390,'height':844})
                page.locator('#account-login-open').click()
                bounds=page.locator('#account-login-dialog').bounding_box()
                assert abs(bounds['x']+bounds['width']/2-195)<2 and bounds['y']>=0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(args.output/'login-mobile.png'),full_page=False)
                page.locator('#account-login-close').click()
                page.set_viewport_size({'width':1440,'height':1000})
                login(page,'preview@example.test')
                assert page.url == base+'/'
                report['states'].append('global-email-login-keeps-current-page')
                page.locator('[data-currency="USD"]').click()
                page.locator('.theme-toggle').click()
                page.locator('[data-follow]').first.click()
                page.locator('#signal-search').fill('OpenAI')
                page.locator('#account-user-menu summary').click()
                page.locator('#account-user-menu a').click()
                page.locator('#workspace').wait_for(state='visible')
                state=context.request.get(base+'/api/account/me').json()['state']
                assert state['homePrices']['currency']=='USD'
                assert state['appearance']['theme']=='dark'
                report['states'].append('immediate-navigation-flushes-pending-settings')
                page.locator('#profile-name').fill('Preview User')
                page.locator('#profile-save').click()
                page.wait_for_function("document.querySelector('#account-user-name').textContent === 'Preview User'")
                with page.expect_download() as download:
                    page.locator('#account-export').click()
                exported=json.loads(Path(download.value.path()).read_text())
                assert 'session' not in json.dumps(exported).lower()
                report['states'].append('profile-and-safe-data-export')
                page.route('**/api/account/state',lambda route:route.fulfill(status=503,content_type='application/json',body='{"message":"Temporary test outage"}'))
                page.locator('.theme-toggle').click()
                page.locator('#account-sync-retry').wait_for(state='visible')
                page.unroute('**/api/account/state')
                page.locator('#account-sync-retry').click()
                page.wait_for_function("document.querySelector('#account-sync-status').textContent==='已同步'")
                assert context.request.get(base+'/api/account/me').json()['state']['appearance']['theme']=='light'
                page.locator('.theme-toggle').click()
                page.wait_for_function("document.querySelector('#account-sync-status').textContent==='已同步'")
                report['states'].append('failed-save-remains-pending-and-retry-persists')
                page.locator('.model-result button').first.wait_for(state='visible')
                page.locator('.model-result button').first.click();page.locator('.watch-row').wait_for(state='visible')
                assert page.locator('#watch-count').inner_text()=='1'
                model=page.locator('.watch-row a').inner_text()
                page.reload();page.locator('.watch-row').wait_for(state='visible');assert page.locator('.watch-row a').inner_text()==model
                report['states'].append('watch-persists-after-refresh')
                page.locator('.watch-row a').click()
                page.locator('[data-model-follow][aria-pressed=true]').wait_for(state='visible')
                page.locator('[data-model-follow]').click()
                page.locator('[data-model-follow][aria-pressed=false]').wait_for(state='visible')
                page.locator('[data-model-follow]').click()
                page.locator('[data-model-follow][aria-pressed=true]').wait_for(state='visible')
                page.goto(base+'/account/');page.locator('.watch-row').wait_for(state='visible')
                report['states'].append('model-detail-follow-and-unfollow-sync-to-account')
                page.locator('#email-enabled').check()
                page.wait_for_function("document.querySelector('#account-message').textContent.includes('已开启')")
                page.wait_for_function("!document.querySelector('#logout').disabled")
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})");page.wait_for_function('window.scrollY===0')
                page.screenshot(path=str(args.output/'watch-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.evaluate("window.scrollTo({top:0,behavior:'instant'})");page.wait_for_function('window.scrollY===0')
                page.screenshot(path=str(args.output/'watch-mobile.png'),full_page=True);report['states'].append('mobile-no-overflow')
                connection=sqlite3.connect(private/'accounts.sqlite')
                token=connection.execute('SELECT unsubscribeToken FROM users').fetchone()[0];connection.close()
                page.goto(base+'/account/unsubscribe/#'+token)
                page.locator('#unsubscribe-confirm').wait_for(state='visible')
                assert '#' not in page.url
                page.locator('#unsubscribe-confirm').click()
                page.wait_for_function("document.querySelector('#unsubscribe-message').textContent==='已关闭邮件提醒。'")
                page.goto(base+'/account/');page.locator('.watch-row').wait_for(state='visible')
                assert not page.locator('#email-enabled').is_checked();report['states'].append('unsubscribe-keeps-watch')
                page.goto(base+'/pricing/')
                page.locator('#search').fill('gpt')
                page.locator('[data-preset="5,1"]').click()
                page.wait_for_function("document.querySelector('#account-sync-status').textContent==='已同步'")
                page.reload()
                page.wait_for_function("document.querySelector('#search').value==='gpt'")
                assert page.locator('#input-volume').input_value()=='5'
                persisted=context.request.get(base+'/api/account/me').json()['state']
                assert persisted['priceWorkspace']['input']==5 and persisted['priceWorkspace']['query']=='gpt'
                report['states'].append('price-search-comparison-and-volumes-persist')
                page.goto(base+'/account/');page.locator('.watch-row').wait_for(state='visible')
                device=browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN')
                device.add_cookies(context.cookies())
                other=device.new_page()
                other.goto(base+'/')
                other.wait_for_function("document.querySelector('#account-user-name').textContent === 'Preview User'")
                other.wait_for_function("document.querySelector('[data-currency=USD]').getAttribute('aria-pressed') === 'true'")
                assert other.evaluate("document.documentElement.dataset.theme")=='dark'
                assert other.locator('#signal-search').input_value()=='OpenAI'
                assert other.locator('[data-follow][aria-pressed=true]').count()==1
                assert other.evaluate("localStorage.getItem('maas-guest-homePrices')") is None
                report['states'].append('fresh-browser-restores-account-preferences-without-local-storage')
                guest=browser.new_context()
                guest_page=guest.new_page();guest_page.goto(base+'/en/')
                assert guest_page.locator('#account-login-open').inner_text()=='Sign in'
                login(guest_page,'second@example.test')
                isolated=guest.request.get(base+'/api/account/me').json()
                assert isolated['state']=={} and isolated['watches']==[] and isolated['user']['displayName']==''
                report['states'].append('english-global-login-and-second-account-isolation')
                guest_page.goto(base+'/en/pricing/')
                guest_page.locator('#search').fill('DeepSeek')
                guest_page.wait_for_timeout(1100)
                assert guest.request.get(base+'/api/account/me').json()['state']['priceWorkspace']['query']=='DeepSeek'
                guest_page.goto(base+'/pricing/?lang=zh')
                assert guest_page.locator('#search').input_value()=='DeepSeek'
                assert guest_page.locator('footer a[href="mailto:zhangchen3508@gmail.com"]').count()==1
                guest_page.goto(base+'/en/')
                guest_page.set_viewport_size({'width':390,'height':844})
                assert guest_page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                report['states'].append('english-price-workspace-shares-settings-with-chinese-and-contact-link')
                page.locator('.watch-row button').click()
                page.wait_for_function("document.querySelector('#watch-count').textContent==='0'")
                with page.expect_response(lambda response: response.url.endswith('/api/account/logout-all')) as logout_response:
                    page.locator('#account-logout-all').click()
                assert logout_response.value.status==200,logout_response.value.json()
                page.locator('#login-panel').wait_for(state='visible')
                assert page.locator('#user-email').inner_text()==''
                other.reload();other.locator('#account-login-open').wait_for(state='visible')
                assert device.request.get(base+'/api/account/me').status==401
                assert guest.request.get(base+'/api/account/me').status==200
                report['states'].append('logout-all-revokes-other-devices-without-affecting-other-users')
                device.close();guest.close()
                assert not report['errors'],report['errors']
                context.close();browser.close()
        finally:
            api.terminate()
            try:api.wait(timeout=5)
            except subprocess.TimeoutExpired:api.kill();api.wait()
            log.close();server.shutdown();server.server_close()
        (args.output/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
