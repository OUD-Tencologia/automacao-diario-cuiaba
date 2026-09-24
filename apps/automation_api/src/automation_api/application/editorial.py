from __future__ import annotations

from typing import Protocol

from automation_api.domain.editorial import EditorialArticle
from automation_api.domain.news import NewsStatus


class EditorialRepositoryPort(Protocol):
    def list_articles(
        self,
        *,
        status: NewsStatus | None,
        limit: int,
        offset: int,
    ) -> list[EditorialArticle]: ...

    def get_article(self, source: str, source_id: str) -> EditorialArticle | None: ...

    def update_article(
        self,
        source: str,
        source_id: str,
        changes: dict[str, object],
    ) -> EditorialArticle | None: ...


class ArticleNotFoundError(LookupError):
    """A notícia não existe para a fonte e ID informados."""


class PublishedStatusUnavailableError(ValueError):
    """PUBLICADO só pode ser marcado após integração e ação editorial externa."""


class EditorialService:
    """Regras de edição editorial sem acesso ao armazenamento do TXT original."""

    def __init__(self, repository: EditorialRepositoryPort) -> None:
        self._repository = repository

    def list_articles(
        self,
        *,
        status: NewsStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EditorialArticle]:
        return self._repository.list_articles(status=status, limit=limit, offset=offset)

    def get_article(self, source: str, source_id: str) -> EditorialArticle:
        article = self._repository.get_article(source, source_id)
        if article is None:
            raise ArticleNotFoundError
        return article

    def update_article(
        self,
        source: str,
        source_id: str,
        changes: dict[str, object],
    ) -> EditorialArticle:
        if changes.get("status") == NewsStatus.PUBLISHED:
            raise PublishedStatusUnavailableError
        article = self._repository.update_article(source, source_id, changes)
        if article is None:
            raise ArticleNotFoundError
        return article

    def discard_article(self, source: str, source_id: str) -> EditorialArticle:
        article = self._repository.update_article(
            source,
            source_id,
            {"status": NewsStatus.DISCARDED},
        )
        if article is None:
            raise ArticleNotFoundError
        return article
