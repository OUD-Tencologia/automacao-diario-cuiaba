from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.news import NewsDraft, NewsStatus, StoredRawObject
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository


class FakeMappings:
    def __init__(self, row: dict[str, str] | None) -> None:
        self._row = row

    def one_or_none(self) -> dict[str, str] | None:
        return self._row

    def all(self) -> list[dict[str, str]]:
        return [self._row] if self._row else []


class FakeExecution:
    def __init__(self, row: dict[str, str] | None) -> None:
        self._row = row

    def mappings(self) -> FakeMappings:
        return FakeMappings(self._row)


class FakeConnection:
    def __init__(self, row: dict[str, str] | None) -> None:
        self._row = row
        self.statement: str | None = None
        self.parameters: dict[str, Any] | None = None

    def execute(self, statement: Any, parameters: dict[str, Any]) -> FakeExecution:
        self.statement = str(statement)
        self.parameters = parameters
        return FakeExecution(self._row)


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> FakeConnection:
        return self.connection

    def __exit__(self, *args: Any) -> None:
        return None


class FakeEngine:
    def __init__(self, row: dict[str, str] | None) -> None:
        self.connection = FakeConnection(row)

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


def build_draft() -> NewsDraft:
    return NewsDraft(
        source="Folhapress",
        source_id="2599841",
        published_at=datetime(2026, 9, 17, 9, 20, tzinfo=timezone.utc),
        title="Titulo sintetico",
        content="Texto sintetico da materia.",
        source_url="https://folhapress.example/texto/2599841",
        eyebrow="CHAPEU",
        location="Da FolhaPress - Brasilia",
        raw_metadata={"category": "politica"},
    )


def build_raw() -> StoredRawObject:
    return StoredRawObject(
        bucket="bronze-raw",
        object_key="folhapress/2599841/" + "a" * 64 + ".txt",
        sha256="a" * 64,
        size_bytes=42,
    )


def build_editorial_row() -> dict[str, Any]:
    now = datetime(2026, 9, 17, 12, 20, tzinfo=timezone.utc)
    return {
        "source": "folhapress",
        "id": "2599841",
        "dt_noticia": now,
        "ds_chapeu": "POLÍTICA",
        "ds_titulo": "Título sintético",
        "nm_autor": "Repórter",
        "ds_local": "Da FolhaPress - Brasília",
        "ds_noticia": "Texto de trabalho.",
        "ds_resumo": "Resumo sintético.",
        "destaque": False,
        "tipo_de_conteudo": "INTERNO",
        "publicar_imediatamente": False,
        "status": "FILA_EDITORIAL",
        "source_url": "https://folhapress.example/texto/2599841",
        "created_at": now,
        "update_at": now,
    }


class GoldNewsRepositoryTest(unittest.TestCase):
    def test_insert_uses_source_and_source_id_as_idempotency_key(self) -> None:
        engine = FakeEngine({"source": "folhapress", "id": "2599841"})
        result = GoldNewsRepository(engine).create_if_absent(build_draft(), build_raw())

        self.assertTrue(result.created)
        self.assertEqual(result.source, "folhapress")
        self.assertEqual(result.source_id, "2599841")
        self.assertIn("ON CONFLICT (source, id) DO NOTHING", engine.connection.statement)
        self.assertEqual(engine.connection.parameters["status"], "FILA_EDITORIAL")
        self.assertEqual(engine.connection.parameters["content_type"], "INTERNO")

    def test_existing_item_is_reported_without_update(self) -> None:
        engine = FakeEngine(None)
        result = GoldNewsRepository(engine).create_if_absent(build_draft(), build_raw())

        self.assertFalse(result.created)

    def test_list_filters_by_status_and_has_bounded_pagination_parameters(self) -> None:
        engine = FakeEngine(None)

        items = GoldNewsRepository(engine).list_articles(
            status=NewsStatus.QUEUE,
            limit=20,
            offset=40,
        )

        self.assertEqual(items, [])
        self.assertIn("ORDER BY dt_noticia DESC", engine.connection.statement)
        self.assertEqual(engine.connection.parameters["limit"], 20)
        self.assertEqual(engine.connection.parameters["offset"], 40)
        self.assertEqual(engine.connection.parameters["status"], "FILA_EDITORIAL")

    def test_list_maps_database_row_to_editorial_contract(self) -> None:
        engine = FakeEngine(build_editorial_row())

        items = GoldNewsRepository(engine).list_articles(status=None, limit=10, offset=0)

        self.assertEqual(items[0].id, "2599841")
        self.assertEqual(items[0].status, NewsStatus.QUEUE)
        self.assertEqual(items[0].ds_resumo, "Resumo sintético.")

    def test_update_uses_whitelisted_editorial_columns_only(self) -> None:
        engine = FakeEngine(None)

        result = GoldNewsRepository(engine).update_article(
            "Folhapress", "2599841", {"ds_titulo": "Título revisado"}
        )

        self.assertIsNone(result)
        self.assertIn("SET ds_titulo = :value_0", engine.connection.statement)
        self.assertNotIn("raw_sha256 =", engine.connection.statement)
        self.assertEqual(engine.connection.parameters["source"], "folhapress")
        self.assertEqual(engine.connection.parameters["source_id"], "2599841")

    def test_update_returns_the_persisted_editorial_record(self) -> None:
        engine = FakeEngine(build_editorial_row())

        result = GoldNewsRepository(engine).update_article(
            "folhapress", "2599841", {"ds_resumo": "Resumo revisado."}
        )

        self.assertEqual(result.id, "2599841")
        self.assertEqual(result.ds_resumo, "Resumo sintético.")
        self.assertIn("RETURNING source, id", engine.connection.statement)

    def test_update_rejects_non_editorial_fields(self) -> None:
        engine = FakeEngine(None)

        with self.assertRaisesRegex(ValueError, "campos editoriais não permitidos"):
            GoldNewsRepository(engine).update_article(
                "folhapress", "2599841", {"raw_sha256": "a" * 64}
            )
