from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.folhapress import ArticleReference
from automation_api.infrastructure.folhapress.extractor import (
    build_news_draft,
    extract_article_from_html,
)


class FolhapressExtractorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = ArticleReference.from_url(
            "/texto/2599841", base_url="https://folhapress.folha.com.br"
        )

    def test_txt_headers_populate_the_editorial_contract(self) -> None:
        extracted = extract_article_from_html(
            """
            <html><head>
            <meta property="og:title" content="Título da página">
            <meta property="article:published_time" content="2026-09-17T09:20:00-03:00">
            </head><body><article><p>Cuiabá, MT (FOLHAPRESS) - Texto.</p></article></body></html>
            """,
            self.reference,
        )
        original = """
CHAPEU:
POLÍTICA NACIONAL

TITULO:
Título sintético da notícia

DATA/HORA:
17/09/2026 09h20

AUTOR:
AUTOR SINTÉTICO

LOCAL:
CUIABÁ, MT (FOLHAPRESS) -

DESCRICAO:
Primeira frase sintética. Segunda frase sintética.

DESTAQUE:
NAO
""".strip().encode()

        draft = build_news_draft(extracted, original)

        self.assertEqual(draft.source_id, "2599841")
        self.assertEqual(draft.eyebrow, "POLÍTICA NACIONAL")
        self.assertEqual(draft.title, "Título sintético da notícia")
        self.assertEqual(draft.location, "Da FolhaPress - Cuiabá")
        self.assertEqual(draft.published_at.tzinfo.key, "America/Sao_Paulo")
        self.assertNotIn("DESTAQUE", draft.content)

    def test_json_ld_supplies_page_metadata_when_txt_has_only_body(self) -> None:
        extracted = extract_article_from_html(
            """
            <script type="application/ld+json">
            {"headline":"Título JSON", "datePublished":"2026-09-17T09:20:00-03:00",
             "author":{"name":"Autora"}, "articleBody":"Cuiabá, MT (FOLHAPRESS) - Corpo."}
            </script>
            """,
            self.reference,
        )

        draft = build_news_draft(extracted, b"Texto original sem cabecalho.")

        self.assertEqual(draft.title, "Título JSON")
        self.assertEqual(draft.author, "Autora")
        self.assertEqual(draft.location, "Da FolhaPress - Cuiabá")
        self.assertEqual(draft.content, "Cuiabá, MT (FOLHAPRESS) - Corpo.")

    def test_download_url_is_derived_from_the_article_id(self) -> None:
        self.assertEqual(
            self.reference.download_url,
            "https://folhapress.folha.com.br/texto/2599841/baixar",
        )

    def test_download_route_is_not_a_valid_article_reference(self) -> None:
        with self.assertRaisesRegex(ValueError, "URL não possui"):
            ArticleReference.from_url(
                "/texto/2599841/baixar", base_url="https://folhapress.folha.com.br"
            )
