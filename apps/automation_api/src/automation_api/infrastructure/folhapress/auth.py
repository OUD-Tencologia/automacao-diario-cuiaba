from __future__ import annotations

from typing import Any

from automation_api.infrastructure.folhapress.errors import FolhapressAuthenticationError
from automation_api.settings import FolhapressConfiguration


class FolhapressAuth:
    """Autentica a sessão em memória e confirma acesso ao catálogo protegido."""

    _DEFAULT_USERNAME_SELECTOR = 'input[type="email"], input[name*="email" i], input[name*="login" i], input[name*="user" i], input[type="text"]'
    _DEFAULT_PASSWORD_SELECTOR = 'input[type="password"]'
    _DEFAULT_SUBMIT_SELECTOR = 'button[type="submit"], input[type="submit"]'

    def __init__(self, page: Any, configuration: FolhapressConfiguration) -> None:
        self._page = page
        self._configuration = configuration

    def login(self) -> None:
        username_selector = (
            self._configuration.login_username_selector or self._DEFAULT_USERNAME_SELECTOR
        )
        password_selector = (
            self._configuration.login_password_selector or self._DEFAULT_PASSWORD_SELECTOR
        )
        submit_selector = (
            self._configuration.login_submit_selector or self._DEFAULT_SUBMIT_SELECTOR
        )
        try:
            response = self._page.goto(
                self._configuration.login_url,
                wait_until="domcontentloaded",
            )
            status_code = getattr(response, "status", None)
            if status_code is None or not 200 <= status_code < 400:
                raise FolhapressAuthenticationError(
                    "A página de login Folhapress não respondeu com sucesso"
                )
            self._page.locator(username_selector).first.fill(self._configuration.username)
            self._page.locator(password_selector).first.fill(self._configuration.password)
            self._page.locator(submit_selector).first.click()
            self._page.wait_for_load_state("domcontentloaded")
            response = self._page.goto(
                self._configuration.catalog_url,
                wait_until="domcontentloaded",
            )
        except Exception:
            raise FolhapressAuthenticationError("Não foi possível autenticar na Folhapress") from None

        status_code = getattr(response, "status", None)
        password_inputs = self._page.locator(self._DEFAULT_PASSWORD_SELECTOR).count()
        if status_code is None or not 200 <= status_code < 400 or password_inputs:
            raise FolhapressAuthenticationError("A sessão Folhapress não foi confirmada")
