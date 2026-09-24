from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from automation_api.domain.news import NewsStatus


@dataclass(frozen=True)
class EditorialArticle:
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
