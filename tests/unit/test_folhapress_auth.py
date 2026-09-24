from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.infrastructure.folhapress.auth import FolhapressAuth
from automation_api.infrastructure.folhapress.errors import FolhapressConnectionError
from automation_api.infrastructure.folhapress.health import SourceHealth
from automation_api.settings import FolhapressConfiguration


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class FakeLocator:
    def __init__(self, page: FakePage, selector: str) -> None:
        self.page = page
        self.selector = selector
        self.first = self

    def filter(self, **kwargs: object) -> FakeLocator:
        return self

    def wait_for(self, **kwargs: object) -> None:
        return None

    def fill(self, value: str, **kwargs: object) -> None:
        self.page.filled[self.selector] = value

    def click(self, **kwargs: object) -> None:
        self.page.clicked.append(self.selector)

    def count(self) -> int:
        return 0 if self.page.current_url.endswith("/textos") else 1


class FakePage:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.responses = responses or [FakeResponse()]
        self.current_url = ""
        self.urls: list[str] = []
        self.filled: dict[str, str] = {}
        self.clicked: list[str] = []
        self.waits: list[int] = []

    def goto(self, url: str, **kwargs: object) -> FakeResponse:
        self.current_url = url
        self.urls.append(url)
        return self.responses.pop(0) if self.responses else FakeResponse()

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def wait_for_load_state(self, state: str) -> None:
        return None

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


def configuration() -> FolhapressConfiguration:
    return FolhapressConfiguration(
        base_url="https://folhapress.folha.com.br",
        login_url="https://folhapress.folha.com.br/login",
        catalog_url="https://folhapress.folha.com.br/textos",
        username="synthetic-user",
        password="synthetic-password",
        article_link_selector='a[href*="/texto/"]',
        catalog_query=None,
        required_catalog_labels=(),
        page_size=24,
        max_pages_per_cycle=1,
        navigation_timeout_ms=1_000,
        headless=True,
        login_username_selector=None,
        login_password_selector=None,
        login_submit_selector=None,
        navigation_attempts=2,
    )


class FolhapressAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        # Prontidão DOM é exercitada com Chromium em tests/browser.
        readiness = patch("automation_api.infrastructure.folhapress.auth.wait_for_catalog")
        readiness.start()
        self.addCleanup(readiness.stop)

    def test_auth_navigates_to_login_before_filling_credentials(self) -> None:
        page = FakePage()
        config = configuration()

        FolhapressAuth(page, config).login()

        self.assertEqual(page.urls, [config.login_url, config.catalog_url])
        self.assertEqual(page.filled['input[type="password"]'], "synthetic-password")
        self.assertEqual(len(page.clicked), 1)

    def test_auth_diagnostic_code_identifies_unavailable_login_page(self) -> None:
        page = FakePage([FakeResponse(503), FakeResponse(503)])

        with self.assertRaises(FolhapressConnectionError) as raised:
            FolhapressAuth(page, configuration()).login()

        self.assertEqual(raised.exception.diagnostic_code, "http_503")
        self.assertFalse(page.filled)

    def test_health_retries_transient_navigation_failure(self) -> None:
        page = FakePage([FakeResponse(503), FakeResponse(200)])

        SourceHealth(page, configuration()).check()

        self.assertEqual(page.urls, ["https://folhapress.folha.com.br"] * 2)
        self.assertEqual(page.waits, [500])
