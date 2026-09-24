from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Engine, text

from automation_api.domain.editorial import EditorialArticle
from automation_api.domain.news import NewsDraft, StoredRawObject
from automation_api.domain.news import NewsStatus


@dataclass(frozen=True)
class PersistedNews:
    source: str
    source_id: str
    created: bool


@dataclass(frozen=True)
class ReconciliationCandidate:
    """Registro antigo que pode ser reparado sem apagar o TXT original."""

    source: str
    source_id: str
    source_url: str
    minio_object_key: str
    raw_sha256: str


class GoldNewsRepository:
    """Persiste a única tabela editorial sem sobrescrever curadoria existente."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def exists(self, source: str, source_id: str) -> bool:
        """Evita baixar novamente uma matéria já entregue à fila editorial."""

        statement = text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM gold.articles
                WHERE source = :source AND id = :source_id
            )
            """
        )
        with self._engine.connect() as connection:
            return bool(
                connection.execute(
                    statement,
                    {"source": source.strip().lower(), "source_id": source_id.strip()},
                ).scalar_one()
            )

    def create_if_absent(
        self,
        draft: NewsDraft,
        raw: StoredRawObject,
        summary: str | None = None,
    ) -> PersistedNews:
        statement = text(
            """
            INSERT INTO gold.articles (
                source, id, dt_noticia, ds_chapeu, ds_titulo, nm_autor,
                ds_local, ds_noticia, ds_resumo, destaque, tipo_de_conteudo,
                publicar_imediatamente, status, source_url, minio_bucket,
                minio_object_key, raw_sha256, raw_size_bytes, raw_metadata
            ) VALUES (
                :source, :source_id, :published_at, :eyebrow, :title, :author,
                :location, :content, :summary, :featured, :content_type,
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
            "summary": _optional(summary),
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

    def find_reconciliation_candidates(self, *, limit: int) -> list[ReconciliationCandidate]:
        """Seleciona somente filas ainda nÃ£o editadas e gravadas pelo contrato antigo."""

        statement = text(
            """
            SELECT source, id, source_url, minio_object_key, raw_sha256
            FROM gold.articles
            WHERE source = 'folhapress'
              AND status = 'FILA_EDITORIAL'
              AND (
                    lower(ds_titulo) IN ('folhapress', 'folha press')
                    OR COALESCE(raw_metadata->>'extraction_contract_version', '0') = '0'
                  )
            ORDER BY created_at ASC, source, id
            LIMIT :limit
            """
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement, {"limit": limit}).mappings().all()
        return [
            ReconciliationCandidate(
                source=str(row["source"]),
                source_id=str(row["id"]),
                source_url=str(row["source_url"]),
                minio_object_key=str(row["minio_object_key"]),
                raw_sha256=str(row["raw_sha256"]),
            )
            for row in rows
        ]

    def repair_queue_item(
        self,
        candidate: ReconciliationCandidate,
        draft: NewsDraft,
        summary: str | None,
    ) -> bool:
        """Atualiza somente a fila tÃ©cnica antiga; nunca sobrescreve curadoria."""

        statement = text(
            """
            UPDATE gold.articles
            SET dt_noticia = :published_at,
                ds_chapeu = :eyebrow,
                ds_titulo = :title,
                nm_autor = :author,
                ds_local = :location,
                ds_noticia = :content,
                ds_resumo = :summary,
                source_url = :source_url,
                raw_metadata = CAST(:raw_metadata AS jsonb)
            WHERE source = :source
              AND id = :source_id
              AND source = 'folhapress'
              AND status = 'FILA_EDITORIAL'
              AND (
                    lower(ds_titulo) IN ('folhapress', 'folha press')
                    OR COALESCE(raw_metadata->>'extraction_contract_version', '0') = '0'
                  )
            RETURNING source, id
            """
        )
        parameters = {
            "source": candidate.source.strip().lower(),
            "source_id": candidate.source_id.strip(),
            "published_at": draft.published_at,
            "eyebrow": _optional(draft.eyebrow),
            "title": draft.title.strip(),
            "author": _optional(draft.author),
            "location": _optional(draft.location),
            "content": draft.content.strip(),
            "summary": _optional(summary),
            "source_url": draft.source_url.strip(),
            "raw_metadata": json.dumps(dict(draft.raw_metadata), ensure_ascii=False),
        }
        with self._engine.begin() as connection:
            row = connection.execute(statement, parameters).mappings().one_or_none()
        return row is not None

    def list_articles(
        self,
        *,
        status: NewsStatus | None,
        limit: int,
        offset: int,
    ) -> list[EditorialArticle]:
        where_clause = "WHERE status = :status" if status else ""
        parameters: dict[str, object] = {
            "limit": limit,
            "offset": offset,
        }
        if status:
            parameters["status"] = status.value
        statement = text(
            """
            SELECT source, id, dt_noticia, ds_chapeu, ds_titulo, nm_autor,
                   ds_local, ds_noticia, ds_resumo, destaque, tipo_de_conteudo,
                   publicar_imediatamente, status, source_url, created_at, update_at
            FROM gold.articles
            """
            + where_clause
            + """
            ORDER BY dt_noticia DESC, created_at DESC, source, id
            LIMIT :limit OFFSET :offset
            """
        )
        with self._engine.connect() as connection:
            rows = connection.execute(
                statement,
                parameters,
            ).mappings().all()
        return [_article_from_row(row) for row in rows]

    def get_article(self, source: str, source_id: str) -> EditorialArticle | None:
        statement = text(
            """
            SELECT source, id, dt_noticia, ds_chapeu, ds_titulo, nm_autor,
                   ds_local, ds_noticia, ds_resumo, destaque, tipo_de_conteudo,
                   publicar_imediatamente, status, source_url, created_at, update_at
            FROM gold.articles
            WHERE source = :source AND id = :source_id
            """
        )
        with self._engine.connect() as connection:
            row = connection.execute(
                statement,
                {"source": source.strip().lower(), "source_id": source_id.strip()},
            ).mappings().one_or_none()
        return _article_from_row(row) if row is not None else None

    def update_article(
        self,
        source: str,
        source_id: str,
        changes: dict[str, object],
    ) -> EditorialArticle | None:
        column_names = {
            "ds_chapeu": "ds_chapeu",
            "ds_titulo": "ds_titulo",
            "nm_autor": "nm_autor",
            "ds_local": "ds_local",
            "ds_noticia": "ds_noticia",
            "ds_resumo": "ds_resumo",
            "destaque": "destaque",
            "tipo_de_conteudo": "tipo_de_conteudo",
            "publicar_imediatamente": "publicar_imediatamente",
            "status": "status",
        }
        unknown = set(changes) - column_names.keys()
        if unknown:
            raise ValueError("A atualização contém campos editoriais não permitidos")
        if not changes:
            return self.get_article(source, source_id)

        assignments: list[str] = []
        parameters: dict[str, object] = {
            "source": source.strip().lower(),
            "source_id": source_id.strip(),
        }
        for index, (field_name, value) in enumerate(changes.items()):
            parameter_name = f"value_{index}"
            assignments.append(f"{column_names[field_name]} = :{parameter_name}")
            parameters[parameter_name] = value.value if isinstance(value, NewsStatus) else value

        statement = text(
            """
            UPDATE gold.articles
            SET """
            + ", ".join(assignments)
            + " WHERE source = :source AND id = :source_id "
            + "RETURNING source, id, dt_noticia, ds_chapeu, ds_titulo, nm_autor, "
            + "ds_local, ds_noticia, ds_resumo, destaque, tipo_de_conteudo, "
            + "publicar_imediatamente, status, source_url, created_at, update_at"
        )
        with self._engine.begin() as connection:
            row = connection.execute(statement, parameters).mappings().one_or_none()
        return _article_from_row(row) if row is not None else None


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _article_from_row(row: object) -> EditorialArticle:
    values = dict(row)
    values["status"] = NewsStatus(values["status"])
    return EditorialArticle(**values)
