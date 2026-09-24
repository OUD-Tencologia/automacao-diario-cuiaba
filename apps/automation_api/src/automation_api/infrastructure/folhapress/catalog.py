from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from automation_api.domain.folhapress import ArticleReference, FolhapressDataError
from automation_api.infrastructure.folhapress.errors import FolhapressCatalogError
from automation_api.infrastructure.folhapress.navigation import navigate_html, wait_for_catalog
from automation_api.settings import FolhapressConfiguration


class FolhapressCatalog:
    """Navega o catálogo de textos, respeitando paginação e contrato de filtros."""

    def __init__(self, page: Any, configuration: FolhapressConfiguration) -> None:
        self._page = page
        self._configuration = configuration
        self.limit_reached = False

    def list_articles(self) -> list[ArticleReference]:
        references: dict[str, ArticleReference] = {}
        for page_number in range(self._configuration.max_pages_per_cycle):
            url = self._catalog_page_url(page_number)
            navigate_html(
                self._page, url, stage="catalog",
                timeout_ms=self._configuration.navigation_timeout_ms,
                attempts=self._configuration.navigation_attempts,
                ready=lambda: wait_for_catalog(self._page, self._configuration),
            )
            try:
                html = self._page.content()
            except Exception:
                raise FolhapressCatalogError(
                    "Não foi possível ler o catálogo Folhapress",
                    diagnostic_code="catalog_read_failed",
                ) from None
            self._assert_required_labels(html)
            found_on_page = self._references_from_html(html)
            added = 0
            for reference in found_on_page:
                if reference.source_id not in references:
                    references[reference.source_id] = reference
                    added += 1

            if not found_on_page or added == 0:
                break
            if (
                page_number + 1 == self._configuration.max_pages_per_cycle
                and len(found_on_page) >= self._configuration.page_size
            ):
                self.limit_reached = True

        return list(references.values())

    def _catalog_page_url(self, page_number: int) -> str:
        parsed = urlsplit(self._configuration.catalog_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if self._configuration.catalog_query:
            query.update(parse_qsl(self._configuration.catalog_query, keep_blank_values=True))
        query["sr"] = str(1 + page_number * self._configuration.page_size)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))

    def _assert_required_labels(self, html: str) -> None:
        normalized = " ".join(_text_from_html(html).split()).casefold()
        missing = [
            label
            for label in self._configuration.required_catalog_labels
            if label.casefold() not in normalized
        ]
        if missing:
            raise FolhapressCatalogError(
                "O catálogo não contém os filtros esperados",
                diagnostic_code="catalog_markup_invalid",
            )

    def _references_from_html(self, html: str) -> list[ArticleReference]:
        references: list[ArticleReference] = []
        parser = _CatalogAnchorParser()
        parser.feed(html)
        parser.close()
        for href, anchor_text in parser.anchors:
            if "/texto/" not in href or "/baixar" in href:
                continue
            eyebrow, title = _split_catalog_headline(anchor_text)
            try:
                references.append(
                    ArticleReference.from_url(
                        href,
                        base_url=self._configuration.base_url,
                        catalog_eyebrow=eyebrow,
                        catalog_title=title,
                    )
                )
            except FolhapressDataError:
                continue
        return references


def _text_from_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(html))


def _split_catalog_headline(value: str) -> tuple[str | None, str | None]:
    """Separa ``CHAPÉU: título`` exatamente como exibido no catálogo.

    O horário pode fazer parte do texto do link em algumas variações do HTML;
    ele não é chapéu nem título e por isso é removido antes da separação.
    """

    normalized = " ".join(value.split())
    normalized = re.sub(r"^(?:\d{1,2}:\d{2}\s+)+", "", normalized)
    eyebrow, separator, title = normalized.partition(":")
    if separator and eyebrow.strip() and title.strip():
        return eyebrow.strip(), title.strip()
    return None, normalized or None


class _CatalogAnchorParser(HTMLParser):
    """Lê o texto visível de cada link sem depender de regex sobre HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        attributes = {name.casefold(): value or "" for name, value in attrs}
        href = attributes.get("href", "").strip()
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text_parts)))
            self._href = None
            self._text_parts = []
