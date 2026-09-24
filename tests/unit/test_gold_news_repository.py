from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.news import NewsDraft, StoredRawObject
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository


class FakeMappings:
    def __init__(self, row: dict[str, str] | None) -> None:
        self._row = row

    def one_or_none(self) -> dict[str, str] | None:
        return self._row


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
