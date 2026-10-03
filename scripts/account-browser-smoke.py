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
                page.goto(base+'/account/');page.locator('#login-panel').wait_for(state='visible')
                page.screenshot(path=str(args.output/'login-desktop.png'),full_page=True);report['states'].append('login')
                page.locator('#email').fill('preview@example.test');page.locator('#send-code').click()
                page.locator('#code-fields').wait_for(state='visible')
                mail=json.loads(next((private/'outbox').glob('*.json')).read_text())
                code=re.search(r'\b\d{6}\b',mail['text'])[0]
                page.locator('#code').fill(code);page.locator('#login-form button[type=submit]').click()
                page.locator('#workspace').wait_for(state='visible')
                page.locator('.model-result button').first.wait_for(state='visible')
                page.locator('.model-result button').first.click();page.locator('.watch-row').wait_for(state='visible')
                assert page.locator('#watch-count').inner_text()=='1'
                model=page.locator('.watch-row a').inner_text()
                page.reload();page.locator('.watch-row').wait_for(state='visible');assert page.locator('.watch-row a').inner_text()==model
                report['states'].append('watch-persists-after-refresh')
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
                page.locator('.watch-row button').click()
                page.wait_for_function("document.querySelector('#watch-count').textContent==='0'")
                page.locator('#logout').click();page.locator('#login-panel').wait_for(state='visible')
                assert page.locator('#user-email').inner_text()==''
                report['states'].append('unwatch-and-logout')
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
