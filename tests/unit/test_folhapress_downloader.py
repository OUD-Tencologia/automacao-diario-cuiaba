from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.folhapress.downloader import TxtDownloader
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError


class FakeDownload:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.deleted = False

    def path(self) -> str:
        return str(self._path)

    def failure(self) -> None:
        return None

    def delete(self) -> None:
        self._path.unlink(missing_ok=True)
        self.deleted = True


class FakeDownloadInfo:
    def __init__(self, download: FakeDownload | None, error: Exception | None) -> None:
        self.value = download
        self._error = error

    def __enter__(self) -> FakeDownloadInfo:
        if self._error:
            raise self._error
        return self

    def __exit__(self, *unused: object) -> None:
        return None


class FakePage:
    def __init__(self, download: FakeDownload | None = None, error: Exception | None = None) -> None:
        self.download = download
        self.error = error
        self.urls: list[str] = []
        self.wait_until: str | None = None
        self.timeout_ms: int | None = None

    def expect_download(self, *, timeout: int) -> FakeDownloadInfo:
        self.timeout_ms = timeout
        return FakeDownloadInfo(self.download, self.error)

    def goto(self, *args, **kwargs) -> None:
        raise AssertionError("O downloader não deve usar goto para iniciar o download")


class FakeLink:
    def __init__(self, page: FakePage, url: str) -> None:
        self.page, self.url = page, url

    def click(self, *, timeout: int) -> None:
        self.page.urls.append(self.url)
        self.page.timeout_ms = timeout


class FolhapressDownloaderTest(unittest.TestCase):
    def setUp(self) -> None:
        finder = patch(
            "automation_api.infrastructure.folhapress.downloader.wait_for_download_link",
            side_effect=lambda page, url, timeout: FakeLink(page, url),
        )
        self.find_link = finder.start()
        self.addCleanup(finder.stop)
        self.reference = ArticleReference.from_url(
            "/texto/101", base_url="https://folhapress.folha.com.br"
        )

    def test_downloads_authenticated_txt_and_deletes_temporary_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.txt"
            path.write_bytes(b"texto sintetico")
            download = FakeDownload(path)
            page = FakePage(download)

            content = TxtDownloader(page, timeout_ms=1_000).download(self.reference)

            self.assertEqual(content, b"texto sintetico")
            self.assertEqual(page.urls, [self.reference.download_url])
            self.assertIsNone(page.wait_until)
            self.assertEqual(page.timeout_ms, 1_000)
            self.assertTrue(download.deleted)
            self.assertFalse(path.exists())

    def test_rejects_html_login_page_instead_of_txt(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.html"
            path.write_bytes(b"<html>login</html>")
            download = FakeDownload(path)

            with self.assertRaises(FolhapressDownloadError) as raised:
                TxtDownloader(FakePage(download), timeout_ms=1_000).download(self.reference)

            self.assertEqual(raised.exception.diagnostic_code, "html_response")
            self.assertTrue(download.deleted)
            self.assertFalse(path.exists())

    def test_download_timeout_has_safe_diagnostic_code(self) -> None:
        page = FakePage(error=TimeoutError())

        with self.assertRaises(FolhapressDownloadError) as raised:
            TxtDownloader(page, timeout_ms=1_000).download(self.reference)

        self.assertEqual(raised.exception.diagnostic_code, "download_timeout")

    def test_missing_link_has_distinct_diagnostic_code(self) -> None:
        self.find_link.side_effect = TimeoutError()
        with self.assertRaises(FolhapressDownloadError) as raised:
            TxtDownloader(FakePage(), timeout_ms=1_000).download(self.reference)
        self.assertEqual(raised.exception.diagnostic_code, "download_link_missing")


if __name__ == "__main__":
    unittest.main()
