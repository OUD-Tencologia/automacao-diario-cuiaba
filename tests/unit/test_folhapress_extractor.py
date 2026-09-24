from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.domain.folhapress import ArticleReference, ExtractedArticle, FolhapressDataError
from automation_api.infrastructure.folhapress.extractor import (
    build_news_draft,
    extract_article_from_html,
    parse_folhapress_datetime,
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
        self.assertEqual(draft.content, "Texto original sem cabecalho.")

    def test_generic_portal_title_is_rejected_instead_of_persisted(self) -> None:
        extracted = extract_article_from_html(
            '<h1>Folhapress</h1><time datetime="2026-09-24T14:35:00-03:00">agora</time>',
            self.reference,
        )

        with self.assertRaises(FolhapressDataError) as error:
            build_news_draft(extracted, b"Texto original da materia.")

        self.assertEqual(error.exception.diagnostic_code, "generic_article_title")

    def test_txt_body_is_preferred_to_generic_html_content(self) -> None:
        extracted = extract_article_from_html(
            """
            <meta property="og:title" content="Titulo especifico">
            <time datetime="2026-09-24T14:35:00-03:00">agora</time>
            <div class="article-content">HTML generico que nao e o original.</div>
            """,
            self.reference,
        )

        draft = build_news_draft(extracted, b"Brasilia, DF (FOLHAPRESS) - TXT original definitivo.")

        self.assertEqual(draft.content, "Brasilia, DF (FOLHAPRESS) - TXT original definitivo.")
        self.assertEqual(draft.location, "Da FolhaPress - Brasilia")
        self.assertEqual(draft.raw_metadata["metadata_sources"]["content"], "txt")

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

    def test_missing_fields_are_reported_without_source_content(self) -> None:
        with self.assertRaises(FolhapressDataError) as error:
            build_news_draft(ExtractedArticle(reference=self.reference), b"texto sem metadados")

        self.assertEqual(error.exception.diagnostic_code, "required_fields_missing")
        self.assertEqual(error.exception.missing_fields, ("title", "published_at"))
        self.assertNotIn("texto sem metadados", str(error.exception))

    def test_invalid_date_has_a_distinct_diagnostic_code(self) -> None:
        original = b"TITULO: Sintetico\nDATA/HORA: formato desconhecido\nDESCRICAO: Corpo"
        with self.assertRaises(FolhapressDataError) as error:
            build_news_draft(ExtractedArticle(reference=self.reference), original)

        self.assertEqual(error.exception.diagnostic_code, "invalid_published_at")

    def test_semantic_time_supplies_date_when_txt_has_only_body(self) -> None:
        extracted = extract_article_from_html(
            '<h1>Título semântico</h1><time datetime="2026-09-24T14:35:00-03:00">agora</time>',
            self.reference,
        )

        draft = build_news_draft(extracted, b"Corpo sintetico sem cabecalhos.")

        self.assertEqual(draft.published_at.isoformat(), "2026-09-24T14:35:00-03:00")

    def test_itemprop_date_and_decorated_display_date_are_supported(self) -> None:
        extracted = extract_article_from_html(
            '<meta itemprop="datePublished" content="24/09/2026 às 09h20">'
            '<h1>Título sintético</h1>',
            self.reference,
        )
        draft = build_news_draft(extracted, b"Corpo sintetico.")

        self.assertEqual(draft.published_at.hour, 9)
        self.assertEqual(parse_folhapress_datetime("Publicado em 24/09/2026 - 7h05").minute, 5)

    def test_observed_text_info_uses_first_editorial_datetime_only(self) -> None:
        extracted = extract_article_from_html(
            """
            <h1>Título sintético</h1>
            <div class="text-info clearfix"><ul>
              <li>24/09/2026 14h35</li>
              <li>Atualizado em 24/09/2026 15h10</li>
            </ul></div>
            <li class="item text"><a><span class="date">01/01/2020 08h00</span></a></li>
            """,
            self.reference,
        )

        draft = build_news_draft(extracted, b"Corpo sintetico sem data.")

        self.assertEqual(draft.published_at.hour, 14)
        self.assertEqual(draft.published_at.minute, 35)
