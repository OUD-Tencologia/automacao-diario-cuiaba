from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Protocol

from automation_api.domain.folhapress import ArticleReference, ExtractedArticle, FolhapressDataError
from automation_api.domain.news import NewsDraft, StoredRawObject
from automation_api.infrastructure.gold_news_repository import PersistedNews


class ArticleCatalogPort(Protocol):
    def list_articles(self) -> list[ArticleReference]: ...


class ArticleExtractorPort(Protocol):
    def extract(self, reference: ArticleReference) -> ExtractedArticle: ...

    def build_draft(self, extracted: ExtractedArticle, original_text: bytes) -> NewsDraft: ...


class TxtDownloaderPort(Protocol):
    def download(self, reference: ArticleReference) -> bytes: ...


class RawStoragePort(Protocol):
    def store(self, source: str, source_id: str, content: bytes) -> StoredRawObject: ...


class NewsRepositoryPort(Protocol):
    def exists(self, source: str, source_id: str) -> bool: ...

    def create_if_absent(
        self,
        draft: NewsDraft,
        raw: StoredRawObject,
        summary: str | None,
    ) -> PersistedNews: ...


class EditorialSummaryPort(Protocol):
    def generate(self, content: str) -> str | None: ...


@dataclass(frozen=True)
class CaptureResult:
    capture_id: str
    scanned: int
    captured: int
    skipped_existing: int
    failed: int
    duration_ms: int


@dataclass(frozen=True)
class CaptureFailure:
    """Falha sanitizada e segura para operação; nunca contém texto ou segredo."""

    source_id: str | None
    stage: str
    diagnostic_code: str
    retryable: bool


class CaptureCycleError(RuntimeError):
    """Força o retry do n8n quando uma ou mais matérias não foram capturadas."""

    def __init__(self, result: CaptureResult, failures: list[CaptureFailure]) -> None:
        self.result = result
        self.failures = tuple(failures)
        self.failed_source_ids = tuple(
            failure.source_id for failure in failures if failure.source_id is not None
        )
        super().__init__("O ciclo Folhapress teve matérias não capturadas")


class CaptureSourceError(RuntimeError):
    """Falha antes ou fora de uma matéria individual da fonte externa."""

    def __init__(
        self,
        *,
        capture_id: str,
        stage: str,
        error: Exception,
        duration_ms: int,
    ) -> None:
        self.result = CaptureResult(
            capture_id=capture_id,
            scanned=0,
            captured=0,
            skipped_existing=0,
            failed=1,
            duration_ms=duration_ms,
        )
        self.failure = _capture_failure(None, stage, error)
        super().__init__("A preparação da captura Folhapress falhou")


class CaptureFolhapress:
    """Orquestra uma captura idempotente sem transferir regra de negócio ao n8n."""

    def __init__(
        self,
        *,
        catalog: ArticleCatalogPort,
        extractor: ArticleExtractorPort,
        downloader: TxtDownloaderPort,
        raw_storage: RawStoragePort,
        repository: NewsRepositoryPort,
        summary_generator: EditorialSummaryPort,
        capture_id: str,
    ) -> None:
        self._catalog = catalog
        self._extractor = extractor
        self._downloader = downloader
        self._raw_storage = raw_storage
        self._repository = repository
        self._summary_generator = summary_generator
        self._capture_id = capture_id

    def run(self) -> CaptureResult:
        started_at = perf_counter()
        references = self._catalog.list_articles()
        captured = 0
        skipped_existing = 0
        failures: list[CaptureFailure] = []
        logger = logging.getLogger(__name__)
        logger.info("capture_started capture_id=%s references=%s", self._capture_id, len(references))

        for reference in references:
            try:
                stage = "database"
                if self._repository.exists("folhapress", reference.source_id):
                    skipped_existing += 1
                    continue
                stage = "article"
                extracted = self._extractor.extract(reference)
                stage = "download"
                original_txt = self._downloader.download(reference)
                stage = "minio"
                raw = self._raw_storage.store("folhapress", reference.source_id, original_txt)
                stage = "draft"
                draft = self._extractor.build_draft(extracted, original_txt)
                stage = "database"
                persisted = self._repository.create_if_absent(
                    draft,
                    raw,
                    self._generate_summary(draft, logger),
                )
            except Exception as error:
                failure = _capture_failure(reference.source_id, stage, error)
                failures.append(failure)
                logger.warning(
                    "capture_item_failed capture_id=%s source_id=%s stage=%s code=%s retryable=%s",
                    self._capture_id,
                    reference.source_id,
                    failure.stage,
                    failure.diagnostic_code,
                    failure.retryable,
                )
                continue

            if persisted.created:
                captured += 1
            else:
                skipped_existing += 1

        result = CaptureResult(
            capture_id=self._capture_id,
            scanned=len(references),
            captured=captured,
            skipped_existing=skipped_existing,
            failed=len(failures),
            duration_ms=round((perf_counter() - started_at) * 1000),
        )
        logger.info(
            "capture_finished capture_id=%s scanned=%s captured=%s skipped_existing=%s failed=%s duration_ms=%s",
            result.capture_id,
            result.scanned,
            result.captured,
            result.skipped_existing,
            result.failed,
            result.duration_ms,
        )
        if failures:
            raise CaptureCycleError(result, failures)
        return result

    def _generate_summary(self, draft: NewsDraft, logger: logging.Logger) -> str | None:
        try:
            return self._summary_generator.generate(draft.content)
        except Exception:
            logger.warning(
                "summary_not_generated capture_id=%s source=%s source_id=%s",
                self._capture_id,
                draft.source,
                draft.source_id,
            )
            return None


_RETRYABLE_CODES = frozenset({
    "connection_reset",
    "download_failed",
    "download_timeout",
    "temporary_file_missing",
    "browser_download_exception",
    "navigation_timeout",
})


def _capture_failure(source_id: str | None, stage: str, error: Exception) -> CaptureFailure:
    """Converte qualquer erro em diagnóstico restrito ao contrato operacional."""

    code = getattr(error, "diagnostic_code", None)
    if not isinstance(code, str) or not code or not code.replace("_", "").isalnum():
        code = "invalid_source_data" if isinstance(error, FolhapressDataError) else "unexpected_error"
    return CaptureFailure(
        source_id=source_id,
        stage=stage,
        diagnostic_code=code.lower(),
        retryable=code.lower() in _RETRYABLE_CODES,
    )
