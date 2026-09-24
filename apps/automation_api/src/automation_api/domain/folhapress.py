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

    @classmethod
    def from_url(cls, article_url: str, *, base_url: str) -> ArticleReference:
        absolute_url = urljoin(base_url.rstrip("/") + "/", article_url)
        absolute_url = absolute_url.split("?", 1)[0]
        match = _ARTICLE_PATH_PATTERN.search(urlsplit(absolute_url).path)
        if not match:
            raise FolhapressDataError(
                "URL não possui o ID de uma matéria Folhapress",
                diagnostic_code="article_url_missing_id",
            )
        return cls(source_id=match.group("id"), article_url=absolute_url)

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
    """Converte a abertura da agência em um local adequado à interface editorial."""

    if not value:
        return None

    normalized = " ".join(value.split())
    match = re.match(
        r"^(?P<place>.+?)(?:,\s*[A-Z]{2})?\s*\(FOLHAPRESS\)\s*[-–]",
        normalized,
        flags=re.IGNORECASE,
    )
    if not match:
        return normalized or None

    place = " ".join(match.group("place").split()).title()
    return f"Da FolhaPress - {place}" if place else None
