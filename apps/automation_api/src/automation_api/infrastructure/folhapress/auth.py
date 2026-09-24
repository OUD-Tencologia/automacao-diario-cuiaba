from __future__ import annotations

from time import perf_counter
from typing import Any

from automation_api.infrastructure.folhapress.errors import FolhapressAuthenticationError
from automation_api.infrastructure.folhapress.navigation import error_code, navigate_html, wait_for_catalog
from automation_api.settings import FolhapressConfiguration


class FolhapressAuth:
    """Autentica uma vez e confirma a sessão pelos elementos do catálogo."""

    _DEFAULT_USERNAME_SELECTOR = 'input[type="email"], input[name*="email" i], input[name*="login" i], input[name*="user" i], input[type="text"]'
    _DEFAULT_PASSWORD_SELECTOR = 'input[type="password"]'
    _DEFAULT_SUBMIT_SELECTOR = 'button[type="submit"], input[type="submit"]'

    def __init__(self, page: Any, configuration: FolhapressConfiguration) -> None:
        self._page = page
        self._configuration = configuration

    def login(self) -> None:
        config = self._configuration
        selectors = (
            config.login_username_selector or self._DEFAULT_USERNAME_SELECTOR,
            config.login_password_selector or self._DEFAULT_PASSWORD_SELECTOR,
            config.login_submit_selector or self._DEFAULT_SUBMIT_SELECTOR,
        )
        fields = [self._page.locator(selector).filter(visible=True).first for selector in selectors]

        def ready() -> None:
            deadline = perf_counter() + config.navigation_timeout_ms / 1000
            for field in fields:
                field.wait_for(state="visible", timeout=max(1, int((deadline - perf_counter()) * 1000)))

        navigate_html(
            self._page, config.login_url, stage="login_page",
            timeout_ms=config.navigation_timeout_ms, attempts=config.navigation_attempts,
            ready=ready,
        )
        try:
            fields[0].fill(config.username, timeout=config.navigation_timeout_ms)
            fields[1].fill(config.password, timeout=config.navigation_timeout_ms)
            # O clique aguarda a navegação nativa iniciada pelo formulário.
            # Não repetir o POST nem esperar load na página anterior.
            fields[2].click(timeout=config.navigation_timeout_ms)
        except Exception as error:
            raise FolhapressAuthenticationError(
                "A interação com o formulário de login falhou",
                diagnostic_code="login_submit_" + error_code(error),
            ) from None

        navigate_html(
            self._page, config.catalog_url, stage="login_catalog",
            timeout_ms=config.navigation_timeout_ms, attempts=config.navigation_attempts,
            ready=lambda: wait_for_catalog(self._page, config),
        )
