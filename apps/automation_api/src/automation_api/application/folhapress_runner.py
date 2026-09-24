from __future__ import annotations

from time import perf_counter

from automation_api.application.capture_folhapress import (
    CaptureCycleError,
    CaptureFolhapress,
    CaptureResult,
    CaptureSourceError,
)
from automation_api.application.editorial_summary import SumyLsaEditorialSummary
from automation_api.infrastructure.folhapress import (
    ArticleExtractor,
    FolhapressAuth,
    FolhapressBrowserSession,
    FolhapressCatalog,
    FreshSessionArticleRetry,
    SourceHealth,
    TxtDownloader,
)
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository
from automation_api.infrastructure.minio import RawStorage, build_s3_client
from automation_api.infrastructure.postgres import build_postgresql_engine
from automation_api.infrastructure.postgres import CaptureAlreadyRunningError, PostgreSQLAdvisoryLock
from automation_api.settings import Settings


def run_folhapress_capture(settings: Settings, *, capture_id: str) -> CaptureResult:
    """Monta dependências de um único ciclo; a sessão e o engine são descartados."""

    configuration = settings.folhapress()
    engine = build_postgresql_engine(
        settings.resolved_database_url,
        settings.health_check_timeout_seconds,
    )
    started_at = perf_counter()
    stage = "browser"
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
        with PostgreSQLAdvisoryLock(engine, "folhapress_capture"):
            with FolhapressBrowserSession(configuration) as session:
                stage = "source_health"
                SourceHealth(session.page, configuration).check()
                stage = "login"
                FolhapressAuth(session.page, configuration).login()
                stage = "catalog"
                return CaptureFolhapress(
                    catalog=FolhapressCatalog(session.page, configuration),
                    extractor=ArticleExtractor(
                        session.page, timeout_ms=configuration.navigation_timeout_ms,
                        navigation_attempts=configuration.navigation_attempts,
                    ),
                    downloader=TxtDownloader(
                        session.page,
                        timeout_ms=configuration.navigation_timeout_ms,
                    ),
                    raw_storage=raw_storage,
                    repository=repository,
                    summary_generator=SumyLsaEditorialSummary(),
                    capture_id=capture_id,
                    item_retry=FreshSessionArticleRetry(
                        configuration,
                        attempts=configuration.item_retry_attempts,
                        delay_ms=configuration.item_retry_delay_ms,
                    ),
                    cycle_deadline_seconds=configuration.cycle_deadline_seconds,
                ).run()
    except (CaptureAlreadyRunningError, CaptureCycleError):
        raise
    except Exception as error:
        raise CaptureSourceError(
            capture_id=capture_id,
            stage=stage,
            error=error,
            duration_ms=round((perf_counter() - started_at) * 1000),
        ) from None
    finally:
        engine.dispose()
