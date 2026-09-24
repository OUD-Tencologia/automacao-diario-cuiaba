from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.folhapress.downloader import TxtDownloader
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def body(self) -> bytes:
        return self._body


class FakeRequest:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.urls: list[str] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        return self.response


class FakeContext:
    def __init__(self, response: FakeResponse) -> None:
        self.request = FakeRequest(response)


class FolhapressDownloaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = ArticleReference.from_url(
            "/texto/101", base_url="https://folhapress.folha.com.br"
        )

    def test_downloads_the_authenticated_txt_without_writing_a_local_file(self) -> None:
        context = FakeContext(FakeResponse(200, b"texto sintetico"))

        content = TxtDownloader(context, timeout_ms=1_000).download(self.reference)

        self.assertEqual(content, b"texto sintetico")
        self.assertEqual(context.request.urls, [self.reference.download_url])

    def test_rejects_html_login_page_instead_of_txt(self) -> None:
        context = FakeContext(FakeResponse(200, b"<html>login</html>"))

        with self.assertRaises(FolhapressDownloadError):
            TxtDownloader(context, timeout_ms=1_000).download(self.reference)

    def test_download_error_has_a_safe_diagnostic_code(self) -> None:
        context = FakeContext(FakeResponse(200, b"<html>login</html>"))

        with self.assertRaises(FolhapressDownloadError) as raised:
            TxtDownloader(context, timeout_ms=1_000).download(self.reference)

        self.assertEqual(raised.exception.diagnostic_code, "html_response")
