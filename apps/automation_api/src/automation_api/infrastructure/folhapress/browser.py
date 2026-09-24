from __future__ import annotations

from typing import Any

from automation_api.settings import FolhapressConfiguration


class FolhapressBrowserSession:
    """Sessão efêmera: cookies ficam somente na memória durante um ciclo."""

    def __init__(self, configuration: FolhapressConfiguration) -> None:
        self._configuration = configuration
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None

    @property
    def page(self) -> Any:
        if self._page is None:
            raise RuntimeError("A sessão Folhapress não está aberta")
        return self._page

    @property
    def context(self) -> Any:
        if self._context is None:
            raise RuntimeError("A sessão Folhapress não está aberta")
        return self._context

    def __enter__(self) -> FolhapressBrowserSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:  # pragma: no cover - validado na instalação
            raise RuntimeError(
                "Playwright não está instalado. Rode a instalação das dependências do projeto."
            ) from error

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._configuration.headless)
        self._context = self._browser.new_context(
            accept_downloads=True,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=self._configuration.user_agent,
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(self._configuration.navigation_timeout_ms)
        self._page.set_default_navigation_timeout(self._configuration.navigation_timeout_ms)
        return self

    def __exit__(self, *unused: object) -> None:
        try:
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
