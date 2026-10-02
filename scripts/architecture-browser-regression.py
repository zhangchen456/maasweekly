#!/usr/bin/env python3
"""Actual browser price-workspace behavior and desktop/mobile snapshots; local static release only."""
import argparse
import functools
import http.server
import json
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('site', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.site.resolve()))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'scope': 'Local Chromium, static built pages; no production requests', 'states': {}, 'errors': []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(locale='zh-CN', viewport={'width': 1440, 'height': 1000})
            context.grant_permissions(['clipboard-read', 'clipboard-write'])
            page = context.new_page()
            page.on('pageerror', lambda error: report['errors'].append(str(error)))
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(f'http://127.0.0.1:{server.server_port}/') else route.abort())
            base = f'http://127.0.0.1:{server.server_port}'
            def state(name):
                report['states'][name] = page.evaluate('''() => ({
                  title: document.querySelector('#provider-title').textContent,
                  rows: [...document.querySelectorAll('#models tr')].map(r => r.innerText),
                  selection: document.querySelector('#selection').innerText,
                  comparison: document.querySelector('#comparison-table').innerText,
                  plots: [...document.querySelectorAll('#plot .plot-price')].map(r => r.innerText),
                  error: document.querySelector('#filter-error').hidden ? null : document.querySelector('#filter-error').innerText,
                  model: document.querySelector('#model-filter').value,
                  family: document.querySelector('#family-filter').value,
                  fx: document.querySelector('#fx').value,
                  input: document.querySelector('#input-value').innerText
                })''')
            page.goto(base + '/pricing/')
            page.wait_for_selector('#models tr')
            state('default')
            page.screenshot(path=str(args.output/'pricing-desktop.png'), full_page=True)
            page.locator('#search').fill('deepseek')
            assert page.locator('#models tr').count() > 0
            state('search')
            page.locator('#search').fill('this-model-does-not-exist')
            assert page.locator('#models tr').count() == 0
            assert page.locator('#catalog-empty').is_visible()
            state('search-empty')
            page.locator('#search').fill('')
            page.locator('#model-filter').select_option('anthropic:claude-sonnet-4.5')
            assert 'modelId=' in page.url
            state('model-filter')
            page.locator('#family-filter').select_option('anthropic:claude-sonnet')
            assert page.locator('#model-filter').input_value() == ''
            state('family-filter')
            page.locator('#filter-summary button').click()
            page.locator('#sort').select_option('input')
            state('sort-input')
            page.locator('.details-btn').first.click()
            assert page.locator('#detail').evaluate('(d) => d.open')
            report['detail'] = page.locator('#facts').inner_text()
            page.keyboard.press('Escape')
            assert not page.locator('#detail').evaluate('(d) => d.open')
            page.locator('#clear').click()
            assert page.locator('#selection button').count() == 0
            page.locator('#search').fill('')
            for _ in range(5):
                if page.locator('#models .add:not(.selected)').count() == 0:
                    page.locator('#providers button').nth(1).click()
                page.locator('#models .add:not(.selected)').first.click()
            assert page.locator('#selection button').count() == 5
            if page.locator('#models .add:not(.selected)').count() == 0:
                page.locator('#providers button').nth(1).click()
            page.locator('#models .add:not(.selected)').first.click()
            assert page.locator('#selection button').count() == 5
            assert '最多对比' in page.locator('#toast').inner_text()
            state('compare-five')
            page.locator('[data-preset]').last.click()
            state('calculator-preset')
            page.locator('#fx').fill('8')
            page.locator('#fx').dispatch_event('change')
            state('currency-eight')
            page.locator('#fx').fill('0')
            page.locator('#fx').dispatch_event('change')
            assert page.locator('#fx').input_value() == '8'
            state('currency-invalid')
            page.goto(base+'/pricing/?modelId=deepseek:deepseek-flash')
            page.wait_for_function("document.querySelector('#model-filter').value === 'deepseek:deepseek-flash'")
            assert page.locator('#models tr').count() == 0
            state('known-empty')
            page.goto(base+'/pricing/?modelId=alibaba:ghost-model')
            page.wait_for_function("!document.querySelector('#filter-error').hidden")
            state('invalid-model')
            page.set_viewport_size({'width':390, 'height':844})
            page.goto(base+'/pricing/')
            page.wait_for_selector('#models tr')
            state('mobile-default')
            page.screenshot(path=str(args.output/'pricing-mobile.png'), full_page=True)
            report['mobileWidth'] = page.evaluate('({viewport:innerWidth, document:document.documentElement.scrollWidth})')
            page.goto(base+'/')
            page.wait_for_selector('.market-table tbody tr')
            report['home'] = {'prices':page.locator('.market-section').inner_text()}
            page.locator('[data-currency="USD"]').click()
            report['home']['usd'] = page.locator('.market-section').inner_text()
            page.locator('#copy-brief').click()
            page.wait_for_function("document.querySelector('#copy-status').textContent.includes('已复制')")
            report['home']['copyStatus'] = page.locator('#copy-status').inner_text()
            clipboard = page.evaluate('navigator.clipboard.readText()')
            assert 'MaaS Daily' in clipboard
            report['home']['clipboardBytes'] = len(clipboard.encode())
            page.locator('#signal-search').fill('no-such-model-xyz')
            assert page.locator('#filter-empty').is_visible()
            page.locator('#reset-filters').click()
            assert not page.locator('#filter-empty').is_visible()
            report['home']['searchReset'] = True
            report['models'] = {}
            for locale in ['', 'en/']:
                page.goto(base+'/'+locale+'model/deepseek:deepseek-v4-pro/')
                page.wait_for_selector('#current-prices tr')
                report['models'][locale or 'zh'] = {'table':page.locator('#current-prices').inner_text(),
                  'datasetVersion':page.locator('.model-detail').get_attribute('data-dataset-version'),
                  'evidence':[a.get_attribute('href') for a in page.locator('#current-prices a').all()]}
            assert report['models']['zh']['datasetVersion'] == report['models']['en/']['datasetVersion']
            browser.close()
        assert not report['errors'], report['errors']
        (args.output/'browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'states':len(report['states']), 'errors':report['errors'], 'output':str(args.output)}, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

if __name__ == '__main__':
    main()
