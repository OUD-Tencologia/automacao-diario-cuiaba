from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.application.capture_folhapress import CaptureCycleError, CaptureFolhapress
from automation_api.domain.folhapress import ArticleReference, ExtractedArticle
from automation_api.domain.news import NewsDraft, StoredRawObject
from automation_api.infrastructure.folhapress.errors import FolhapressDownloadError
from automation_api.infrastructure.gold_news_repository import PersistedNews


class FakeCatalog:
    def __init__(self, references: list[ArticleReference]) -> None:
        self.references = references

    def list_articles(self) -> list[ArticleReference]:
        return self.references


class FakeExtractor:
    def extract(self, reference: ArticleReference) -> ExtractedArticle:
        return ExtractedArticle(
            reference=reference,
            title=f"Titulo {reference.source_id}",
            published_at=datetime(2026, 9, 24, 9, 20, tzinfo=ZoneInfo("America/Sao_Paulo")),
            content="Texto sintetico.",
        )

    def build_draft(self, extracted: ExtractedArticle, original_text: bytes) -> NewsDraft:
        return NewsDraft(
            source="folhapress",
            source_id=extracted.reference.source_id,
            published_at=extracted.published_at,
            title=extracted.title or "",
            content=original_text.decode(),
            source_url=extracted.reference.article_url,
        )


class FakeDownloader:
    def __init__(self, failing_ids: set[str] | None = None) -> None:
        self.failing_ids = failing_ids or set()
        self.downloaded_ids: list[str] = []

    def download(self, reference: ArticleReference) -> bytes:
        self.downloaded_ids.append(reference.source_id)
        if reference.source_id in self.failing_ids:
            raise FolhapressDownloadError("synthetic download failure", diagnostic_code="download_timeout")
        return f"texto-{reference.source_id}".encode()


class FakeRawStorage:
    def __init__(self) -> None:
        self.stored_ids: list[str] = []

    def store(self, source: str, source_id: str, content: bytes) -> StoredRawObject:
        self.stored_ids.append(source_id)
        return StoredRawObject(
            bucket="bronze-raw",
            object_key=f"folhapress/{source_id}/" + "a" * 64 + ".txt",
            sha256="a" * 64,
            size_bytes=len(content),
        )


class FakeRepository:
    def __init__(self, existing_ids: set[str] | None = None) -> None:
        self.ids = existing_ids or set()
        self.created_ids: list[str] = []
        self.summaries: list[str | None] = []

    def exists(self, source: str, source_id: str) -> bool:
        return source_id in self.ids

    def create_if_absent(
        self,
        draft: NewsDraft,
        raw: StoredRawObject,
        summary: str | None,
    ) -> PersistedNews:
        del raw
        if draft.source_id in self.ids:
            return PersistedNews(source="folhapress", source_id=draft.source_id, created=False)
        self.ids.add(draft.source_id)
        self.created_ids.append(draft.source_id)
        self.summaries.append(summary)
        return PersistedNews(source="folhapress", source_id=draft.source_id, created=True)


class FakeSummary:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def generate(self, content: str) -> str | None:
        if self.should_fail:
            raise RuntimeError("synthetic summary failure")
        return content[:150] or None


class FakeItemRetry:
    def __init__(self) -> None:
        self.retried_ids: list[str] = []

    def retry(self, reference: ArticleReference) -> tuple[ExtractedArticle, bytes]:
        self.retried_ids.append(reference.source_id)
        return (
            FakeExtractor().extract(reference),
            f"texto-recuperado-{reference.source_id}".encode(),
        )


def references() -> list[ArticleReference]:
    return [
        ArticleReference.from_url(f"/texto/{source_id}", base_url="https://folhapress.folha.com.br")
        for source_id in ("101", "102")
    ]


class CaptureFolhapressTest(unittest.TestCase):
    def test_existing_article_is_skipped_before_download(self) -> None:
        downloader = FakeDownloader()
        raw_storage = FakeRawStorage()
        repository = FakeRepository(existing_ids={"101"})
        result = CaptureFolhapress(
            catalog=FakeCatalog(references()),
            extractor=FakeExtractor(),
            downloader=downloader,
            raw_storage=raw_storage,
            repository=repository,
            summary_generator=FakeSummary(),
            capture_id="test-existing",
        ).run()

        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.captured, 1)
        self.assertEqual(result.skipped_existing, 1)
        self.assertEqual(downloader.downloaded_ids, ["102"])
        self.assertEqual(raw_storage.stored_ids, ["102"])

    def test_failure_does_not_create_an_incomplete_item(self) -> None:
        downloader = FakeDownloader(failing_ids={"102"})
        raw_storage = FakeRawStorage()
        repository = FakeRepository()
        capture = CaptureFolhapress(
            catalog=FakeCatalog(references()),
            extractor=FakeExtractor(),
            downloader=downloader,
            raw_storage=raw_storage,
            repository=repository,
            summary_generator=FakeSummary(),
            capture_id="test-failure",
        )

        with self.assertRaises(CaptureCycleError) as raised:
            capture.run()

        self.assertEqual(raised.exception.failed_source_ids, ("102",))
        self.assertEqual(raised.exception.result.capture_id, "test-failure")
        self.assertEqual(raised.exception.result.failed, 1)
        self.assertEqual(raised.exception.failures[0].stage, "download")
        self.assertEqual(raised.exception.failures[0].diagnostic_code, "download_timeout")
        self.assertTrue(raised.exception.failures[0].retryable)
        self.assertEqual(repository.created_ids, ["101"])
        self.assertEqual(raw_storage.stored_ids, ["101"])

    def test_summary_failure_does_not_block_capture(self) -> None:
        repository = FakeRepository()

        result = CaptureFolhapress(
            catalog=FakeCatalog(references()[:1]),
            extractor=FakeExtractor(),
            downloader=FakeDownloader(),
            raw_storage=FakeRawStorage(),
            repository=repository,
            summary_generator=FakeSummary(should_fail=True),
            capture_id="test-summary",
        ).run()

        self.assertEqual(result.captured, 1)
        self.assertEqual(repository.summaries, [None])

    def test_retryable_download_is_recovered_for_only_the_failed_item(self) -> None:
        retry = FakeItemRetry()
        result = CaptureFolhapress(
            catalog=FakeCatalog(references()),
            extractor=FakeExtractor(),
            downloader=FakeDownloader(failing_ids={"102"}),
            raw_storage=FakeRawStorage(),
            repository=FakeRepository(),
            summary_generator=FakeSummary(),
            capture_id="test-item-retry",
            item_retry=retry,
        ).run()

        self.assertEqual(result.captured, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(retry.retried_ids, ["102"])
