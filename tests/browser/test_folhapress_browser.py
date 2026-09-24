"""Regressão com Chromium e HTTP local. Sem .env, VPS ou Folhapress real."""

from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from threading import Thread
from time import sleep
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/automation_api/src"))

from playwright.sync_api import Error, sync_playwright
from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.folhapress.auth import FolhapressAuth
from automation_api.infrastructure.folhapress.catalog import FolhapressCatalog
from automation_api.infrastructure.folhapress.downloader import TxtDownloader
from automation_api.infrastructure.folhapress.errors import FolhapressSourceError, FolhapressDownloadError
from automation_api.infrastructure.folhapress.extractor import ArticleExtractor
from automation_api.infrastructure.folhapress.navigation import navigate_html
from automation_api.settings import FolhapressConfiguration


TXT = b'TITULO:\nNoticia sintetica\nDATA/HORA:\n24/09/2026 10h00\nAUTOR:\nTeste\nDESCRICAO:\nConteudo sintetico para teste de download.\n'
LABELS = 'TEXTOS SERVIÇO NOTICIOSO'


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    posts = 0
    retries = 0

    def log_message(self, *args):
        pass

    def send_body(self, body, *, status=200, attachment=False, delay=0):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain' if attachment else 'text/html; charset=utf-8')
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="synthetic.txt"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.flush()
        if delay:
            sleep(delay)
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def redirect(self, target):
        self.send_response(302)
        self.send_header('Location', target)
        self.end_headers()

    def do_POST(self):
        type(self).posts += 1
        values = parse_qs(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode())
        if values.get('email') == ['synthetic-user'] and values.get('password') == ['synthetic-password']:
            self.send_response(302)
            self.send_header('Set-Cookie', 'session=ok; Path=/; HttpOnly')
            self.send_header('Location', '/textos')
            self.end_headers()
        else:
            self.redirect('/login')

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        mode = parse_qs(parsed.query).get('mode', ['normal'])[0]
        if path == '/login':
            self.send_body(b'<form method="post" action="/login"><input name="email"><input name="password" type="password"><button type="submit">Entrar</button></form>')
            return
        if path == '/retry':
            type(self).retries += 1
            self.send_body(b'<p>synthetic</p>', status=503 if type(self).retries < 3 else 200)
            return
        if 'session=ok' not in self.headers.get('Cookie', ''):
            self.redirect('/login')
            return
        if path == '/textos':
            body = '<html><body>' + LABELS
            if mode != 'empty':
                body += '<a href="/texto/101">Noticia sintetica</a>'
            body += '</body></html>'
            self.send_body(body.encode(), delay=0.3 if mode == 'slow' else 1 if mode == 'stuck' else 0)
            return
        if path.endswith('/baixar'):
            article_id = path.split('/')[2]
            if article_id == '105':
                self.send_body(b'<html>unavailable</html>', status=503)
            elif article_id == '106':
                self.redirect('/login')
            elif article_id == '104':
                self.send_response(200)
                self.send_header('Content-Disposition', 'attachment; filename="synthetic.txt"')
                self.send_header('Content-Length', str(len(TXT) + 100))
                self.end_headers()
                self.wfile.write(TXT)
                self.wfile.flush()
                self.close_connection = True
            else:
                data = b'' if article_id == '102' else b'\xef\xbb\xbf<html>login</html>' if article_id == '103' else TXT
                self.send_body(data, attachment=True)
            return
        if path.startswith('/texto/'):
            article_id = path.split('/')[2]
            href = path + '/baixar'
            if article_id == '107':
                href = 'http://example.invalid' + href
            self.send_body(('<html><body><h1>Noticia sintetica</h1><a href="' + href + '">Baixar TXT</a></body></html>').encode())
            return
        self.send_body(b'<html>synthetic</html>')


class FolhapressBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        # Falha explícita se Chromium não estiver instalado; nunca skip silencioso.
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True)
        self.addCleanup(self.context.close)
        self.context.add_cookies([{'name': 'session', 'value': 'ok', 'url': self.base}])
        self.page = self.context.new_page()
        self.page.set_default_timeout(2000)
        self.config = FolhapressConfiguration(
            base_url=self.base, login_url=self.base + '/login', catalog_url=self.base + '/textos',
            username='synthetic-user', password='synthetic-password', article_link_selector='a[href*="/texto/"]',
            catalog_query=None, required_catalog_labels=('TEXTOS', 'SERVIÇO NOTICIOSO'),
            page_size=24, max_pages_per_cycle=1, navigation_timeout_ms=2000, navigation_attempts=1,
            headless=True, login_username_selector=None, login_password_selector=None, login_submit_selector=None,
        )

    def reference(self, article_id='101'):
        return ArticleReference.from_url('/texto/' + article_id, base_url=self.base)

    def test_legacy_navigation_raises_although_download_succeeds(self):
        ref = self.reference()
        self.page.goto(ref.article_url)
        with self.page.expect_download() as event:
            with self.assertRaises(Error):
                self.page.goto(ref.download_url, wait_until='commit')
        download = event.value
        try:
            self.assertIsNone(download.failure())
            self.assertEqual(Path(download.path()).read_bytes(), TXT)
        finally:
            download.delete()

    def test_corrected_downloader_preserves_session_bytes_and_removes_temporary(self):
        ref = self.reference()
        self.page.goto(ref.article_url)
        paths = []
        read_bytes = Path.read_bytes

        def observed_read(path):
            paths.append(path)
            return read_bytes(path)

        with patch.object(Path, 'read_bytes', observed_read):
            self.assertEqual(TxtDownloader(self.page, timeout_ms=2000).download(ref), TXT)
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())

    def test_invalid_downloads_are_rejected(self):
        for article_id, code in [('102', 'empty_body'), ('103', 'html_response'),
                                 ('104', 'download_failed'), ('105', 'download_timeout'),
                                 ('106', 'session_expired'), ('107', 'download_link_missing')]:
            with self.subTest(article_id=article_id):
                ref = self.reference(article_id)
                self.page.goto(ref.article_url)
                with self.assertRaises(FolhapressDownloadError) as error:
                    TxtDownloader(self.page, timeout_ms=700).download(ref)
                self.assertEqual(error.exception.diagnostic_code, code)

    def test_login_catalog_download_and_draft_without_external_services(self):
        self.context.clear_cookies()
        Handler.posts = 0
        FolhapressAuth(self.page, self.config).login()
        self.assertEqual(Handler.posts, 1)
        refs = FolhapressCatalog(self.page, self.config).list_articles()
        extractor = ArticleExtractor(self.page, timeout_ms=2000, navigation_attempts=1)
        article = extractor.extract(refs[0])
        data = TxtDownloader(self.page, timeout_ms=2000).download(refs[0])
        draft = extractor.build_draft(article, data)
        self.assertEqual(draft.title, 'Noticia sintetica')
        self.assertEqual(draft.published_at.year, 2026)

    def test_invalid_login_does_not_resubmit_credentials(self):
        self.context.clear_cookies()
        Handler.posts = 0
        with self.assertRaises(FolhapressSourceError) as error:
            FolhapressAuth(self.page, replace(self.config, password='wrong')).login()
        self.assertEqual(error.exception.diagnostic_code, 'session_expired')
        self.assertEqual(Handler.posts, 1)

    def test_legacy_async_poc_uses_corrected_download_and_cleans_temporary(self):
        spec = spec_from_file_location('folhapress_poc_test_target', Path('scripts/folhapress_poc.py'))
        poc = module_from_spec(spec)
        spec.loader.exec_module(poc)
        paths = []
        read_bytes = Path.read_bytes

        def observed_read(path):
            paths.append(path)
            return read_bytes(path)

        async def check():
            async with poc.async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(accept_downloads=True)
                    await context.add_cookies([{'name': 'session', 'value': 'ok', 'url': self.base}])
                    page = await context.new_page()
                    with patch.object(Path, 'read_bytes', observed_read):
                        report = await poc.temporary_download(page, self.base, '101', 2000)
                    self.assertEqual(report['content_size_bytes'], len(TXT))
                    self.assertEqual(report['content_sha256'], hashlib.sha256(TXT).hexdigest())
                    self.assertEqual(len(paths), 1)
                    self.assertFalse(paths[0].exists())
                finally:
                    await browser.close()

        # A API síncrona do Playwright já mantém um loop nesta thread.
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(lambda: asyncio.run(check())).result(timeout=30)

    def test_slow_catalog_waits_for_real_elements(self):
        refs = FolhapressCatalog(self.page, replace(self.config, catalog_query='mode=slow')).list_articles()
        self.assertEqual(len(refs), 1)

    def test_unfinished_catalog_is_not_empty_success(self):
        with self.assertRaises(FolhapressSourceError) as error:
            FolhapressCatalog(self.page, replace(self.config, catalog_query='mode=stuck', navigation_timeout_ms=100)).list_articles()
        self.assertEqual(error.exception.diagnostic_code, 'navigation_timeout')

    def test_completed_empty_catalog_is_valid(self):
        self.assertEqual(FolhapressCatalog(self.page, replace(self.config, catalog_query='mode=empty')).list_articles(), [])

    def test_transient_http_retries_are_bounded(self):
        Handler.retries = 0
        navigate_html(self.page, self.base + '/retry', stage='test', timeout_ms=2000, attempts=3)
        self.assertEqual(Handler.retries, 3)


if __name__ == '__main__':
    unittest.main()
