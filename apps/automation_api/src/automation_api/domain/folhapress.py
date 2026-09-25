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
        r"^(?P<location>[^()\n]{1,120}?)\s*\(FOLHAPRESS\)\s*[-–—]",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return _format_location_text(match.group("location"))

    explicit_match = re.match(
        r"^(?P<location>[^()\n]{1,120})\s*$",
        normalized,
        flags=re.IGNORECASE,
    )
    if explicit_match:
        explicit = explicit_match.group("location")
        if "," in explicit and re.fullmatch(
            r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'-]*(?:,\s*[A-Za-zÀ-ÿ]{2,30})(?:\s+e\s+[A-Za-zÀ-ÿ .'-]+(?:,\s*[A-Za-zÀ-ÿ]{2,30})?)?",
            explicit,
            re.IGNORECASE,
        ):
            return _format_location_text(explicit)
    # Nunca devolva texto arbitrário como local. A página da Folhapress possui
    # blocos técnicos (por exemplo, o JavaScript do datepicker) que podem ser
    # confundidos com conteúdo quando um seletor semântico não encontra a
    # matéria. Sem o padrão editorial, o valor é desconhecido.
    return None


def _format_location_text(value: str) -> str | None:
    normalized = " ".join(value.strip(" ,").split())
    if not normalized:
        return None
    abbreviations = set(re.findall(r"\b[A-Z]{2,3}\b", normalized))
    formatted = normalized.title()
    for abbreviation in abbreviations:
        formatted = re.sub(
            rf"\b{re.escape(abbreviation.title())}\b",
            abbreviation,
            formatted,
        )
    return " ".join(re.sub(r"(?:,\s*)?\bE\b\s+", " e ", formatted).split())
