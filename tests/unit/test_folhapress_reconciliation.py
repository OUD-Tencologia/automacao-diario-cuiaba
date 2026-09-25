from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.application.folhapress_reconciliation import _reference_for_candidate
from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.gold_news_repository import ReconciliationCandidate


class FolhapressReconciliationReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = ReconciliationCandidate(
            source="folhapress",
            source_id="2600605",
            source_url="https://folhapress.folha.com.br/texto/2600605",
            minio_object_key="folhapress/2600605/example.txt",
            raw_sha256="a" * 64,
        )

    def test_prefers_catalog_reference_with_editorial_headline(self) -> None:
        catalog_reference = ArticleReference.from_url(
            "/texto/2600605",
            base_url="https://folhapress.folha.com.br",
            catalog_eyebrow="BRASIL-ONU",
            catalog_title="Título editorial",
        )

        reference = _reference_for_candidate(
            self.candidate,
            {"2600605": catalog_reference},
            base_url="https://folhapress.folha.com.br",
        )

        self.assertIs(reference, catalog_reference)

    def test_uses_canonical_article_url_when_catalog_entry_expired(self) -> None:
        reference = _reference_for_candidate(
            self.candidate,
            {},
            base_url="https://folhapress.folha.com.br",
        )

        self.assertEqual(reference.source_id, "2600605")
        self.assertIsNone(reference.catalog_eyebrow)
        self.assertIsNone(reference.catalog_title)


if __name__ == "__main__":
    unittest.main()
