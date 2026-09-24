from __future__ import annotations

from automation_api.application.capture_folhapress import CaptureFolhapress, CaptureResult
from automation_api.application.editorial_summary import SumyLsaEditorialSummary
from automation_api.infrastructure.folhapress import (
    ArticleExtractor,
    FolhapressAuth,
    FolhapressBrowserSession,
    FolhapressCatalog,
    SourceHealth,
    TxtDownloader,
)
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository
from automation_api.infrastructure.minio import RawStorage, build_s3_client
from automation_api.infrastructure.postgres import build_postgresql_engine
from automation_api.settings import Settings


def run_folhapress_capture(settings: Settings) -> CaptureResult:
    """Monta dependências de um único ciclo; a sessão e o engine são descartados."""

    configuration = settings.folhapress()
    engine = build_postgresql_engine(
        settings.resolved_database_url,
        settings.health_check_timeout_seconds,
    )
    try:
        raw_storage = RawStorage(
            settings.minio_bucket_bronze,
            build_s3_client(
                endpoint=settings.resolved_minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key.get_secret_value(),
                region=settings.minio_region,
                timeout_seconds=settings.health_check_timeout_seconds,
            ),
        )
        repository = GoldNewsRepository(engine)
        with FolhapressBrowserSession(configuration) as session:
            SourceHealth(session.page, configuration).check()
            FolhapressAuth(session.page, configuration).login()
            return CaptureFolhapress(
                catalog=FolhapressCatalog(session.page, configuration),
                extractor=ArticleExtractor(session.page),
                downloader=TxtDownloader(
                    session.context,
                    timeout_ms=configuration.navigation_timeout_ms,
                ),
                raw_storage=raw_storage,
                repository=repository,
                summary_generator=SumyLsaEditorialSummary(),
            ).run()
    finally:
        engine.dispose()
