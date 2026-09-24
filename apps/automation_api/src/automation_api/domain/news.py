from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class NewsStatus(StrEnum):
    QUEUE = "FILA_EDITORIAL"
    EDITING = "EM_EDICAO"
    REVIEW = "REVISAO"
    APPROVED = "APROVADO"
    DISCARDED = "DESCARTADO"
    PUBLISHED = "PUBLICADO"


def _required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} é obrigatório")
    return normalized


@dataclass(frozen=True)
class StoredRawObject:
    bucket: str
    object_key: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _required(self.bucket, "bucket")
        _required(self.object_key, "object_key")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256.lower()):
            raise ValueError("sha256 deve ter 64 caracteres hexadecimais")
        if self.size_bytes < 0:
            raise ValueError("size_bytes não pode ser negativo")


@dataclass(frozen=True)
class NewsDraft:
    source: str
    source_id: str
    published_at: datetime
    title: str
    content: str
    source_url: str
    eyebrow: str | None = None
    author: str | None = None
    location: str | None = None
    raw_metadata: Mapping[str, object] = field(default_factory=dict)
    featured: bool = False
    content_type: str = "INTERNO"
    publish_immediately: bool = False
    status: NewsStatus = NewsStatus.QUEUE

    def __post_init__(self) -> None:
        _required(self.source, "source")
        _required(self.source_id, "source_id")
        _required(self.title, "title")
        _required(self.content, "content")
        _required(self.source_url, "source_url")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at deve conter fuso horário")
        if self.content_type not in {"PUBLICO", "INTERNO"}:
            raise ValueError("content_type deve ser PUBLICO ou INTERNO")
