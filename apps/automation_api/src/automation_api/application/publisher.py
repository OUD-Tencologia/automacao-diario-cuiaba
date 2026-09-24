from __future__ import annotations

from typing import Protocol

from automation_api.domain.news import NewsDraft


class PublisherPort(Protocol):
    """Porta para uma futura integração editorial externa."""

    @property
    def enabled(self) -> bool: ...

    def publish(self, article: NewsDraft) -> str: ...


class PublisherDisabledError(RuntimeError):
    """A publicação externa está desabilitada até existir o contrato Trinix."""


class DisabledTrinixPublisher:
    """Adaptador explícito que impede chamadas acidentais ao Trinix."""

    @property
    def enabled(self) -> bool:
        return False

    def publish(self, article: NewsDraft) -> str:
        del article
        raise PublisherDisabledError("Publicação Trinix não está habilitada")
