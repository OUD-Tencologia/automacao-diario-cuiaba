from __future__ import annotations

from typing import Any

from automation_api.infrastructure.folhapress.errors import FolhapressConnectionError
from automation_api.settings import FolhapressConfiguration


class SourceHealth:
    """Verifica que a origem responde antes de enviar credenciais."""

    def __init__(self, page: Any, configuration: FolhapressConfiguration) -> None:
        self._page = page
        self._configuration = configuration

    def check(self) -> None:
        last_error: Exception | None = None
        for attempt in range(self._configuration.navigation_attempts):
            try:
                response = self._page.goto(
                    self._configuration.base_url,
                    wait_until="domcontentloaded",
                )
                status_code = getattr(response, "status", None)
                if status_code is not None and 200 <= status_code < 400:
                    return
                last_error = FolhapressConnectionError(
                    "A Folhapress não respondeu com sucesso"
                )
            except Exception as error:
                last_error = error

            if attempt + 1 < self._configuration.navigation_attempts:
                self._page.wait_for_timeout(500 * (attempt + 1))

        raise FolhapressConnectionError("A Folhapress está indisponível") from last_error
