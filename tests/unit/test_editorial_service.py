from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.application.editorial import (
    ArticleNotFoundError,
    EditorialService,
    PublishedStatusUnavailableError,
)
from automation_api.application.publisher import DisabledTrinixPublisher, PublisherDisabledError
from automation_api.domain.editorial import EditorialArticle
from automation_api.domain.news import NewsStatus


def article(status: NewsStatus = NewsStatus.QUEUE) -> EditorialArticle:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    return EditorialArticle(
        source="folhapress",
        id="101",
        dt_noticia=now,
        ds_chapeu="POLÍTICA",
        ds_titulo="Título sintético",
        nm_autor="Repórter",
        ds_local="Da FolhaPress - Cuiabá",
        ds_noticia="Texto original de trabalho.",
        ds_resumo="Resumo curto.",
        destaque=False,
        tipo_de_conteudo="INTERNO",
        publicar_imediatamente=False,
        status=status,
        source_url="https://folhapress.example/texto/101",
        created_at=now,
        update_at=now,
    )


class FakeRepository:
    def __init__(self, value: EditorialArticle | None = None) -> None:
        self.value = value or article()
        self.changes: dict[str, object] | None = None

    def list_articles(self, *, status, limit, offset):
        if status is not None and self.value.status != status:
            return []
        return [self.value][:limit]

    def get_article(self, source: str, source_id: str):
        return self.value if (source, source_id) == (self.value.source, self.value.id) else None

    def update_article(self, source: str, source_id: str, changes: dict[str, object]):
        if self.get_article(source, source_id) is None:
            return None
        self.changes = changes
        if "status" in changes:
            self.value = article(changes["status"])
        return self.value


class EditorialServiceTest(unittest.TestCase):
    def test_lists_and_reads_editorial_articles(self) -> None:
        service = EditorialService(FakeRepository())

        self.assertEqual(service.list_articles()[0].id, "101")
        self.assertEqual(service.get_article("folhapress", "101").ds_titulo, "Título sintético")

    def test_updates_editorial_fields_without_raw_storage_fields(self) -> None:
        repository = FakeRepository()
        updated = EditorialService(repository).update_article(
            "folhapress",
            "101",
            {"ds_titulo": "Título revisado", "destaque": True},
        )

        self.assertEqual(updated.id, "101")
        self.assertEqual(repository.changes, {"ds_titulo": "Título revisado", "destaque": True})

    def test_discard_is_a_logical_status_update(self) -> None:
        repository = FakeRepository()

        result = EditorialService(repository).discard_article("folhapress", "101")

        self.assertEqual(result.status, NewsStatus.DISCARDED)
        self.assertEqual(repository.changes, {"status": NewsStatus.DISCARDED})

    def test_missing_article_raises_not_found(self) -> None:
        with self.assertRaises(ArticleNotFoundError):
            EditorialService(FakeRepository()).get_article("folhapress", "missing")

    def test_published_cannot_be_set_without_trinix_action(self) -> None:
        with self.assertRaises(PublishedStatusUnavailableError):
            EditorialService(FakeRepository()).update_article(
                "folhapress", "101", {"status": NewsStatus.PUBLISHED}
            )

    def test_trinix_port_is_disabled_and_never_publishes(self) -> None:
        publisher = DisabledTrinixPublisher()

        self.assertFalse(publisher.enabled)
        with self.assertRaises(PublisherDisabledError):
            publisher.publish(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
