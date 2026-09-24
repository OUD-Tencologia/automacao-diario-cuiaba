from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from automation_api.domain.folhapress import ArticleReference, ExtractedArticle
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

    def create_if_absent(self, draft: NewsDraft, raw: StoredRawObject) -> PersistedNews: ...


@dataclass(frozen=True)
class CaptureResult:
    scanned: int
    captured: int
    skipped_existing: int


class CaptureCycleError(RuntimeError):
    """Força o retry do n8n quando uma ou mais matérias não foram capturadas."""

    def __init__(self, failed_source_ids: list[str]) -> None:
        self.failed_source_ids = tuple(failed_source_ids)
        super().__init__("O ciclo Folhapress teve matérias não capturadas")


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
    ) -> None:
        self._catalog = catalog
        self._extractor = extractor
        self._downloader = downloader
        self._raw_storage = raw_storage
        self._repository = repository

    def run(self) -> CaptureResult:
        references = self._catalog.list_articles()
        captured = 0
        skipped_existing = 0
        failures: list[str] = []

        for reference in references:
            if self._repository.exists("folhapress", reference.source_id):
                skipped_existing += 1
                continue

            try:
                extracted = self._extractor.extract(reference)
                original_txt = self._downloader.download(reference)
                raw = self._raw_storage.store("folhapress", reference.source_id, original_txt)
                persisted = self._repository.create_if_absent(
                    self._extractor.build_draft(extracted, original_txt), raw
                )
            except Exception:
                # Não propagamos HTML/TXT/credencial em logs ou resposta. O ID é
                # suficiente para diagnóstico e o erro torna o ciclo reexecutável.
                failures.append(reference.source_id)
                continue

            if persisted.created:
                captured += 1
            else:
                skipped_existing += 1

        if failures:
            raise CaptureCycleError(failures)
        return CaptureResult(
            scanned=len(references),
            captured=captured,
            skipped_existing=skipped_existing,
        )
