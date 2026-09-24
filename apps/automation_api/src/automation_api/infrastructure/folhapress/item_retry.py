from __future__ import annotations

from time import sleep
from typing import Any, Callable, Protocol

from automation_api.domain.folhapress import ArticleReference, ExtractedArticle
from automation_api.infrastructure.folhapress.auth import FolhapressAuth
from automation_api.infrastructure.folhapress.browser import FolhapressBrowserSession
from automation_api.infrastructure.folhapress.downloader import TxtDownloader
from automation_api.infrastructure.folhapress.errors import (
    FolhapressItemRetryError,
    is_retryable_source_error,
)
from automation_api.infrastructure.folhapress.extractor import ArticleExtractor
from automation_api.infrastructure.folhapress.health import SourceHealth
from automation_api.settings import FolhapressConfiguration


class BrowserSessionFactory(Protocol):
    def __call__(self, configuration: FolhapressConfiguration) -> Any: ...


class FreshSessionArticleRetry:
    """Refaz uma única matéria em sessão nova, somente após falha transitória."""

    def __init__(
        self,
        configuration: FolhapressConfiguration,
        *,
        attempts: int,
        delay_ms: int,
        session_factory: BrowserSessionFactory = FolhapressBrowserSession,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts deve ser maior ou igual a 1")
        if delay_ms < 0:
            raise ValueError("delay_ms não pode ser negativo")
        self._configuration = configuration
        self._attempts = attempts
        self._delay_seconds = delay_ms / 1000
        self._session_factory = session_factory
        self._sleep = sleep_fn

    def retry(self, reference: ArticleReference) -> tuple[ExtractedArticle, bytes]:
        last_error: Exception | None = None
        stage = "article"
        for attempt in range(self._attempts):
            if attempt:
                self._sleep(self._delay_seconds * attempt)
            try:
                with self._session_factory(self._configuration) as session:
                    stage = "source_health"
                    SourceHealth(session.page, self._configuration).check()
                    stage = "login"
                    FolhapressAuth(session.page, self._configuration).login()
                    stage = "article"
                    extracted = ArticleExtractor(
                        session.page,
                        timeout_ms=self._configuration.navigation_timeout_ms,
                        navigation_attempts=self._configuration.navigation_attempts,
                    ).extract(reference)
                    stage = "download"
                    original_txt = TxtDownloader(
                        session.page,
                        timeout_ms=self._configuration.navigation_timeout_ms,
                    ).download(reference)
                    return extracted, original_txt
            except Exception as error:
                last_error = error
                if not is_retryable_source_error(error):
                    break

        raise FolhapressItemRetryError(
            stage=getattr(last_error, "capture_stage", stage),
            error=last_error or RuntimeError("retry sem erro"),
        ) from None
