from __future__ import annotations

from functools import lru_cache

from automation_api.application.editorial import EditorialService
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository
from automation_api.infrastructure.postgres import build_postgresql_engine
from automation_api.settings import get_settings


@lru_cache
def get_editorial_service() -> EditorialService:
    settings = get_settings()
    engine = build_postgresql_engine(
        settings.resolved_database_url,
        settings.health_check_timeout_seconds,
    )
    return EditorialService(GoldNewsRepository(engine))
