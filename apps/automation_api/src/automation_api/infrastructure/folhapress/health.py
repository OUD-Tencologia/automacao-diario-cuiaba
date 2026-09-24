from __future__ import annotations

from typing import Any

from automation_api.infrastructure.folhapress.navigation import navigate_html
from automation_api.settings import FolhapressConfiguration


class SourceHealth:
    """Verifica que a origem responde antes de enviar credenciais."""

    def __init__(self, page: Any, configuration: FolhapressConfiguration) -> None:
        self._page = page
        self._configuration = configuration

    def check(self) -> None:
        navigate_html(
            self._page, self._configuration.base_url, stage="source_health",
            timeout_ms=self._configuration.navigation_timeout_ms,
            attempts=self._configuration.navigation_attempts,
        )
