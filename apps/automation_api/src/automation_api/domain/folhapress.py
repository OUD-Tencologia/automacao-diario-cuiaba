from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Mapping
from urllib.parse import urljoin, urlsplit


FOLHAPRESS_SOURCE = "folhapress"
_ARTICLE_PATH_PATTERN = re.compile(r"/texto/(?P<id>\d+)/?$")


class FolhapressDataError(ValueError):
    """Indica que uma página ou TXT não contém os campos mínimos esperados."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic_code: str = "invalid_source_data",
        missing_fields: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code
        self.missing_fields = missing_fields


@dataclass(frozen=True)
class ArticleReference:
    """Referência estável de uma matéria descoberta no catálogo da fonte."""

    source_id: str
    article_url: str
    # O catálogo da Folhapress contém o título editorial mais confiável que o
    # título técnico da página. Esses valores são somente metadados da
    # descoberta; a chave de idempotência continua sendo source_id.
    catalog_eyebrow: str | None = None
    catalog_title: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.isdigit():
            raise FolhapressDataError(
                "O ID Folhapress deve ser numérico", diagnostic_code="invalid_source_id"
            )
        match = _ARTICLE_PATH_PATTERN.search(urlsplit(self.article_url).path)
        if not match or match.group("id") != self.source_id:
            raise FolhapressDataError(
                "A URL da matéria não corresponde ao ID Folhapress",
                diagnostic_code="article_url_id_mismatch",
            )

        for attribute in ("catalog_eyebrow", "catalog_title"):
            value = getattr(self, attribute)
            if value is not None:
                normalized = " ".join(value.split()) or None
                object.__setattr__(self, attribute, normalized)

    @classmethod
    def from_url(
        cls,
        article_url: str,
        *,
        base_url: str,
        catalog_eyebrow: str | None = None,
        catalog_title: str | None = None,
    ) -> ArticleReference:
        absolute_url = urljoin(base_url.rstrip("/") + "/", article_url)
        absolute_url = absolute_url.split("?", 1)[0]
        match = _ARTICLE_PATH_PATTERN.search(urlsplit(absolute_url).path)
        if not match:
            raise FolhapressDataError(
                "URL não possui o ID de uma matéria Folhapress",
                diagnostic_code="article_url_missing_id",
            )
        return cls(
            source_id=match.group("id"),
            article_url=absolute_url,
            catalog_eyebrow=catalog_eyebrow,
            catalog_title=catalog_title,
        )

    @property
    def download_url(self) -> str:
        return self.article_url.rstrip("/") + "/baixar"


@dataclass(frozen=True)
class ExtractedArticle:
    """Metadados de página que serão combinados ao TXT original baixado."""

    reference: ArticleReference
    title: str | None = None
    published_at: datetime | None = None
    eyebrow: str | None = None
    author: str | None = None
    location: str | None = None
    content: str | None = None
    raw_metadata: Mapping[str, object] = field(default_factory=dict)


def normalize_location(value: str | None) -> str | None:
    """Extrai somente ``Cidade, UF`` da abertura editorial da Folhapress."""

    if not value:
        return None

    normalized = " ".join(value.split())
    match = re.match(
        r"^(?P<city>[^,()\n]+?)(?:\s*,\s*(?P<state>[A-Z]{2}))?\s*"
        r"\(FOLHAPRESS\)\s*[-–—]",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return _format_location(match.group("city"), match.group("state"))

    explicit_match = re.match(
        r"^(?P<city>[^,()\n]+?)(?:\s*,\s*(?P<state>[A-Z]{2}))?\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if explicit_match:
        return _format_location(explicit_match.group("city"), explicit_match.group("state"))
    return normalized or None


def _format_location(city: str, state: str | None) -> str | None:
    normalized_city = " ".join(city.split()).title()
    if not normalized_city:
        return None
    return f"{normalized_city}, {state.upper()}" if state else normalized_city
