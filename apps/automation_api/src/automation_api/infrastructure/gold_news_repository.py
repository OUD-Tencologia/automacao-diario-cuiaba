from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Engine, text

from automation_api.domain.news import NewsDraft, StoredRawObject


@dataclass(frozen=True)
class PersistedNews:
    source: str
    source_id: str
    created: bool


class GoldNewsRepository:
    """Persiste a única tabela editorial sem sobrescrever curadoria existente."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_if_absent(self, draft: NewsDraft, raw: StoredRawObject) -> PersistedNews:
        statement = text(
            """
            INSERT INTO gold.articles (
                source, id, dt_noticia, ds_chapeu, ds_titulo, nm_autor,
                ds_local, ds_noticia, destaque, tipo_de_conteudo,
                publicar_imediatamente, status, source_url, minio_bucket,
                minio_object_key, raw_sha256, raw_size_bytes, raw_metadata
            ) VALUES (
                :source, :source_id, :published_at, :eyebrow, :title, :author,
                :location, :content, :featured, :content_type,
                :publish_immediately, :status, :source_url, :bucket,
                :object_key, :sha256, :size_bytes, CAST(:raw_metadata AS jsonb)
            )
            ON CONFLICT (source, id) DO NOTHING
            RETURNING source, id
            """
        )
        parameters = {
            "source": draft.source.strip().lower(),
            "source_id": draft.source_id.strip(),
            "published_at": draft.published_at,
            "eyebrow": _optional(draft.eyebrow),
            "title": draft.title.strip(),
            "author": _optional(draft.author),
            "location": _optional(draft.location),
            "content": draft.content.strip(),
            "featured": draft.featured,
            "content_type": draft.content_type,
            "publish_immediately": draft.publish_immediately,
            "status": draft.status.value,
            "source_url": draft.source_url.strip(),
            "bucket": raw.bucket,
            "object_key": raw.object_key,
            "sha256": raw.sha256,
            "size_bytes": raw.size_bytes,
            "raw_metadata": json.dumps(dict(draft.raw_metadata), ensure_ascii=False),
        }

        with self._engine.begin() as connection:
            row = connection.execute(statement, parameters).mappings().one_or_none()

        return PersistedNews(
            source=parameters["source"],
            source_id=parameters["source_id"],
            created=row is not None,
        )


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None
