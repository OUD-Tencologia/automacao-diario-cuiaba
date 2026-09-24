from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from fastapi.testclient import TestClient

from automation_api.application.editorial import EditorialService
from automation_api.domain.editorial import EditorialArticle
from automation_api.domain.news import NewsStatus
from automation_api.main import create_app


def article(status: NewsStatus = NewsStatus.QUEUE, **changes: object) -> EditorialArticle:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    fields: dict[str, object] = {
        "source": "folhapress",
        "id": "101",
        "dt_noticia": now,
        "ds_chapeu": "POLÍTICA",
        "ds_titulo": "Título sintético",
        "nm_autor": "Repórter",
        "ds_local": "Da FolhaPress - Cuiabá",
        "ds_noticia": "Texto de trabalho.",
        "ds_resumo": "Resumo curto.",
        "destaque": False,
        "tipo_de_conteudo": "INTERNO",
        "publicar_imediatamente": False,
        "status": status,
        "source_url": "https://folhapress.example/texto/101",
        "created_at": now,
        "update_at": now,
    }
    fields.update(changes)
    return EditorialArticle(**fields)


class FakeRepository:
    def __init__(self) -> None:
        self.value = article()
        self.changes: dict[str, object] = {}

    def list_articles(self, *, status, limit, offset):
        if status and status != self.value.status:
            return []
        return [self.value][offset : offset + limit]

    def get_article(self, source: str, source_id: str):
        return self.value if source == self.value.source and source_id == self.value.id else None

    def update_article(self, source: str, source_id: str, changes: dict[str, object]):
        if self.get_article(source, source_id) is None:
            return None
        self.changes = changes
        self.value = article(**{
            "status": changes.get("status", self.value.status),
            **{
                field: value
                for field, value in changes.items()
                if field != "status"
            },
        })
        return self.value


class EditorialApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.service = EditorialService(self.repository)
        self.client = TestClient(create_app())
        self.patcher = patch(
            "automation_api.presentation.editorial.get_editorial_service",
            return_value=self.service,
        )
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_list_and_get_endpoints_return_editorial_contract(self) -> None:
        listed = self.client.get("/editorial/articles?status=FILA_EDITORIAL&limit=10")
        fetched = self.client.get("/editorial/articles/folhapress/101")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"][0]["id"], "101")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["source"], "folhapress")

    def test_patch_updates_only_editorial_fields(self) -> None:
        response = self.client.patch(
            "/editorial/articles/folhapress/101",
            json={"ds_titulo": "Título editado", "destaque": True},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repository.changes, {"ds_titulo": "Título editado", "destaque": True})

    def test_patch_rejects_technical_storage_fields(self) -> None:
        response = self.client.patch(
            "/editorial/articles/folhapress/101",
            json={"raw_sha256": "a" * 64},
        )

        self.assertEqual(response.status_code, 422)

    def test_patch_rejects_null_in_required_fields_and_long_summary(self) -> None:
        title = self.client.patch(
            "/editorial/articles/folhapress/101",
            json={"ds_titulo": None},
        )
        summary = self.client.patch(
            "/editorial/articles/folhapress/101",
            json={"ds_resumo": "x" * 151},
        )

        self.assertEqual(title.status_code, 422)
        self.assertEqual(summary.status_code, 422)

    def test_publicado_cannot_be_set_and_discard_is_logical(self) -> None:
        published = self.client.patch(
            "/editorial/articles/folhapress/101",
            json={"status": "PUBLICADO"},
        )
        discarded = self.client.post("/editorial/articles/folhapress/101/discard")

        self.assertEqual(published.status_code, 409)
        self.assertEqual(discarded.status_code, 200)
        self.assertEqual(discarded.json()["status"], "DESCARTADO")

    def test_unknown_article_returns_404(self) -> None:
        response = self.client.get("/editorial/articles/folhapress/missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
