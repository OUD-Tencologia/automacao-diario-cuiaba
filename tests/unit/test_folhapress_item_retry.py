from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.folhapress import ArticleReference, ExtractedArticle
from automation_api.infrastructure.folhapress.errors import (
    FolhapressDownloadError,
    FolhapressItemRetryError,
)
from automation_api.infrastructure.folhapress.item_retry import FreshSessionArticleRetry
from automation_api.settings import FolhapressConfiguration


def configuration() -> FolhapressConfiguration:
    return FolhapressConfiguration(
        base_url="https://folhapress.example",
        login_url="https://folhapress.example/login",
        catalog_url="https://folhapress.example/textos",
        username="user",
        password="password",
        article_link_selector='a[href*="/texto/"]',
        catalog_query=None,
        required_catalog_labels=("TEXTOS",),
        page_size=24,
        max_pages_per_cycle=1,
        navigation_timeout_ms=1_000,
        headless=True,
        login_username_selector=None,
        login_password_selector=None,
        login_submit_selector=None,
    )


class FakeSession:
    page = object()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return None


class FreshSessionArticleRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = ArticleReference.from_url(
            "/texto/101", base_url="https://folhapress.example"
        )
        self.article = ExtractedArticle(reference=self.reference, title="Sintético")

    def test_recreates_the_session_once_after_a_transient_download_error(self) -> None:
        first_download = MagicMock()
        first_download.download.side_effect = FolhapressDownloadError(
            "transient", diagnostic_code="download_timeout"
        )
        second_download = MagicMock()
        second_download.download.return_value = b"conteudo"
        extractor = MagicMock()
        extractor.extract.return_value = self.article
        session_factory = MagicMock(side_effect=[FakeSession(), FakeSession()])
        sleep = MagicMock()

        with (
            patch("automation_api.infrastructure.folhapress.item_retry.SourceHealth"),
            patch("automation_api.infrastructure.folhapress.item_retry.FolhapressAuth"),
            patch(
                "automation_api.infrastructure.folhapress.item_retry.ArticleExtractor",
                return_value=extractor,
            ),
            patch(
                "automation_api.infrastructure.folhapress.item_retry.TxtDownloader",
                side_effect=[first_download, second_download],
            ),
        ):
            result = FreshSessionArticleRetry(
                configuration(),
                attempts=2,
                delay_ms=1_000,
                session_factory=session_factory,
                sleep_fn=sleep,
            ).retry(self.reference)

        self.assertEqual(result, (self.article, b"conteudo"))
        self.assertEqual(session_factory.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_does_not_retry_a_deterministic_html_response(self) -> None:
        download = MagicMock()
        download.download.side_effect = FolhapressDownloadError(
            "html", diagnostic_code="html_response"
        )
        session_factory = MagicMock(return_value=FakeSession())

        with (
            patch("automation_api.infrastructure.folhapress.item_retry.SourceHealth"),
            patch("automation_api.infrastructure.folhapress.item_retry.FolhapressAuth"),
            patch("automation_api.infrastructure.folhapress.item_retry.ArticleExtractor"),
            patch("automation_api.infrastructure.folhapress.item_retry.TxtDownloader", return_value=download),
            self.assertRaises(FolhapressItemRetryError) as raised,
        ):
            FreshSessionArticleRetry(
                configuration(),
                attempts=2,
                delay_ms=0,
                session_factory=session_factory,
            ).retry(self.reference)

        self.assertEqual(session_factory.call_count, 1)
        self.assertEqual(raised.exception.capture_stage, "download")
        self.assertEqual(raised.exception.diagnostic_code, "html_response")


if __name__ == "__main__":
    unittest.main()
