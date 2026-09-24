from __future__ import annotations

from pathlib import Path
import sys
import unittest

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
    def test_collects_unique_articles_and_uses_observed_pagination(self) -> None:
        page = FakePage(
            [
                """
                TEXTOS SERVIÇO NOTICIOSO
                <a href="/texto/101">Primeira</a>
                <a href="/texto/102">Segunda</a>
                <a href="/texto/102/baixar">Download</a>
                """,
                '<a href="/texto/103">Terceira</a>',
                "<p>Sem resultados</p>",
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
