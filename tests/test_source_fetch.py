"""Official article fallback must reject challenge shells, errors and redirects."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_fetch', ROOT/'pipeline/scripts/fetch_sources.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class SourceFetchTests(unittest.TestCase):
    def test_http_error_body_and_challenge_cannot_become_a_successful_snapshot(self):
        response = SimpleNamespace(returncode=22, stdout='<p>'+'error '*100+'</p>', stderr='')
        with patch('subprocess.run', return_value=response):
            text, error = fetch.fetch_via_curl('https://example.com/doc')
        self.assertIsNone(text)
        self.assertIn('curl_exit=22', error)
        response.returncode = 0
        response.stdout = '<html>Performing security verification</html>'
        with patch('subprocess.run', return_value=response):
            self.assertIsNone(fetch.fetch_via_curl('https://example.com/doc')[0])

    def test_renderer_is_only_used_for_known_official_doc_origins(self):
        with patch.object(fetch, 'fetch_via_curl', return_value=(None, 'short')), patch.object(fetch, 'fetch_rendered_doc', return_value=('official article', None)) as render:
            self.assertEqual(fetch._fetch_page('https://www.volcengine.com/docs/82379/1330310')[0], 'official article')
            self.assertEqual(fetch._fetch_page('https://cloud.tencent.com/document/product/1729/104753')[0], 'official article')
            self.assertIsNone(fetch._fetch_page('https://www.volcengine.com.attacker.test/docs/82379/1330310')[0])
            self.assertIsNone(fetch._fetch_page('https://example.com/document/product/1729/104753')[0])
            self.assertEqual(render.call_count, 2)

    def test_rendering_keeps_article_and_closes_browser_on_rejected_redirect(self):
        url = 'https://cloud.tencent.com/document/product/1729/104753'
        page = SimpleNamespace(url=url, goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                               wait_for_function=AsyncMock())
        article = SimpleNamespace(wait_for=AsyncMock(), inner_html=AsyncMock(return_value='<p>'+'Official model document. '*20+'</p>'))
        page.locator = MagicMock(return_value=article)
        browser = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser))))
        context.__aexit__ = AsyncMock(return_value=False)
        with patch('playwright.async_api.async_playwright', return_value=context):
            text, error = fetch.fetch_rendered_doc(url, '.J-markdown-box', fetch.is_tencent_doc)
            self.assertIn('Official model document', text)
            self.assertIsNone(error)
            page.url = 'https://example.com/login'
            self.assertIsNone(fetch.fetch_rendered_doc(url, '.J-markdown-box', fetch.is_tencent_doc)[0])
        self.assertEqual(browser.close.await_count, 2)
        self.assertEqual(article.inner_html.await_count, 1)


if __name__ == '__main__':
    unittest.main()
