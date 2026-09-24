from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.infrastructure.folhapress.catalog import FolhapressCatalog
from automation_api.infrastructure.folhapress.errors import FolhapressCatalogError
from automation_api.settings import FolhapressConfiguration


class FakeResponse:
    status = 200


class FakePage:
    def __init__(self, documents: list[str]) -> None:
        self.documents = documents
        self.urls: list[str] = []

    def goto(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse()

    def wait_for_selector(self, *args: object, **kwargs: object) -> None:
        return None

    def content(self) -> str:
        index = min(len(self.urls) - 1, len(self.documents) - 1)
        return self.documents[index]


def configuration() -> FolhapressConfiguration:
    return FolhapressConfiguration(
        base_url="https://folhapress.folha.com.br",
        login_url="https://folhapress.folha.com.br/",
        catalog_url="https://folhapress.folha.com.br/textos",
        username="user",
        password="password",
        article_link_selector='a[href*="/texto/"]',
        catalog_query="tipo=textos",
        required_catalog_labels=("TEXTOS", "SERVIÇO NOTICIOSO"),
        page_size=24,
        max_pages_per_cycle=3,
        navigation_timeout_ms=1_000,
        headless=True,
        login_username_selector=None,
        login_password_selector=None,
        login_submit_selector=None,
    )


class FolhapressCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        readiness = patch("automation_api.infrastructure.folhapress.catalog.wait_for_catalog")
        readiness.start()
        self.addCleanup(readiness.stop)

    def test_collects_unique_articles_and_uses_observed_pagination(self) -> None:
        page = FakePage(
            [
                """
                TEXTOS SERVIÇO NOTICIOSO
                <a href="/texto/101">Primeira</a>
                <a href="/texto/102">Segunda</a>
                <a href="/texto/102/baixar">Download</a>
                """,
                'TEXTOS SERVIÇO NOTICIOSO <a href="/texto/103">Terceira</a>',
                "TEXTOS SERVIÇO NOTICIOSO <p>Sem resultados</p>",
            ]
        )

        articles = FolhapressCatalog(page, configuration()).list_articles()

        self.assertEqual([item.source_id for item in articles], ["101", "102", "103"])
        self.assertIn("sr=1", page.urls[0])
        self.assertIn("sr=25", page.urls[1])
        self.assertIn("tipo=textos", page.urls[0])

    def test_rejects_catalog_without_required_labels(self) -> None:
        page = FakePage(['<a href="/texto/101">Primeira</a>'])

        with self.assertRaises(FolhapressCatalogError):
            FolhapressCatalog(page, configuration()).list_articles()

    def test_catalog_read_error_is_sanitized(self) -> None:
        page = FakePage([])
        with patch.object(page, "content", side_effect=RuntimeError("private-cookie")):
            with self.assertRaises(FolhapressCatalogError) as error:
                FolhapressCatalog(page, configuration()).list_articles()
        self.assertEqual(error.exception.diagnostic_code, "catalog_read_failed")
        self.assertNotIn("private-cookie", str(error.exception))

    def test_reports_when_a_full_last_page_reaches_the_configured_limit(self) -> None:
        links = "".join(f'<a href="/texto/{index}">Item</a>' for index in range(100, 124))
        page = FakePage([f"TEXTOS SERVIÇO NOTICIOSO {links}"])
        catalog = FolhapressCatalog(
            page,
            replace(configuration(), max_pages_per_cycle=1),
        )

        articles = catalog.list_articles()

        self.assertEqual(len(articles), 24)
        self.assertTrue(catalog.limit_reached)
