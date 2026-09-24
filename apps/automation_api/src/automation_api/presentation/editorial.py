from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from automation_api.application.editorial import (
    ArticleNotFoundError,
    PublishedStatusUnavailableError,
)
from automation_api.application.editorial_runner import get_editorial_service
from automation_api.domain.editorial import EditorialArticle
from automation_api.domain.news import NewsStatus


router = APIRouter(prefix="/editorial/articles", tags=["editorial"])


class EditorialArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    id: str
    dt_noticia: datetime
    ds_chapeu: str | None
    ds_titulo: str
    nm_autor: str | None
    ds_local: str | None
    ds_noticia: str
    ds_resumo: str | None
    destaque: bool
    tipo_de_conteudo: str
    publicar_imediatamente: bool
    status: NewsStatus
    source_url: str
    created_at: datetime
    update_at: datetime

    @classmethod
    def from_article(cls, article: EditorialArticle) -> EditorialArticleResponse:
        return cls.model_validate(article)


class EditorialArticleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ds_chapeu: str | None = None
    ds_titulo: str | None = Field(default=None, min_length=1, max_length=500)
    nm_autor: str | None = Field(default=None, max_length=300)
    ds_local: str | None = Field(default=None, max_length=300)
    ds_noticia: str | None = Field(default=None, min_length=1)
    ds_resumo: str | None = Field(default=None, max_length=150)
    destaque: bool | None = None
    tipo_de_conteudo: Literal["PUBLICO", "INTERNO"] | None = None
    publicar_imediatamente: bool | None = None
    status: NewsStatus | None = None

    @field_validator("ds_titulo", "ds_noticia")
    @classmethod
    def required_text_cannot_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("O campo não pode ficar vazio")
        return value.strip() if value is not None else None

    @field_validator("ds_chapeu", "nm_autor", "ds_local", "ds_resumo")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def prevent_null_for_non_nullable_columns(self) -> EditorialArticleUpdate:
        non_nullable_fields = {
            "ds_titulo",
            "ds_noticia",
            "destaque",
            "tipo_de_conteudo",
            "publicar_imediatamente",
            "status",
        }
        null_fields = {
            field_name
            for field_name in self.model_fields_set & non_nullable_fields
            if getattr(self, field_name) is None
        }
        if null_fields:
            raise ValueError("Campos obrigatórios não podem receber null")
        return self


class EditorialArticleListResponse(BaseModel):
    items: list[EditorialArticleResponse]
    limit: int
    offset: int


@router.get("", summary="Lista notícias da fila editorial", response_model=EditorialArticleListResponse)
def list_editorial_articles(
    article_status: NewsStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EditorialArticleListResponse:
    articles = get_editorial_service().list_articles(
        status=article_status,
        limit=limit,
        offset=offset,
    )
    return EditorialArticleListResponse(
        items=[EditorialArticleResponse.from_article(article) for article in articles],
        limit=limit,
        offset=offset,
    )


@router.get("/{source}/{source_id}", summary="Consulta uma notícia editorial", response_model=EditorialArticleResponse)
def get_editorial_article(source: str, source_id: str) -> EditorialArticleResponse:
    try:
        article = get_editorial_service().get_article(source, source_id)
    except ArticleNotFoundError as error:
        raise HTTPException(status_code=404, detail="Notícia não encontrada") from error
    return EditorialArticleResponse.from_article(article)


@router.patch(
    "/{source}/{source_id}",
    summary="Edita campos editoriais permitidos",
    response_model=EditorialArticleResponse,
    responses={404: {"description": "Notícia não encontrada."}},
)
def update_editorial_article(
    source: str,
    source_id: str,
    payload: EditorialArticleUpdate,
) -> EditorialArticleResponse:
    changes = payload.model_dump(exclude_unset=True)
    try:
        article = get_editorial_service().update_article(source, source_id, changes)
    except ArticleNotFoundError as error:
        raise HTTPException(status_code=404, detail="Notícia não encontrada") from error
    except PublishedStatusUnavailableError as error:
        raise HTTPException(
            status_code=409,
            detail="PUBLICADO só poderá ser registrado após ação humana no Trinix",
        ) from error
    return EditorialArticleResponse.from_article(article)


@router.post(
    "/{source}/{source_id}/discard",
    summary="Descarta logicamente uma notícia",
    response_model=EditorialArticleResponse,
    responses={404: {"description": "Notícia não encontrada."}},
)
def discard_editorial_article(source: str, source_id: str) -> EditorialArticleResponse:
    try:
        article = get_editorial_service().discard_article(source, source_id)
    except ArticleNotFoundError as error:
        raise HTTPException(status_code=404, detail="Notícia não encontrada") from error
    return EditorialArticleResponse.from_article(article)
