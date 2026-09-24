from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging

from automation_api.application.editorial_summary import SumyLsaEditorialSummary
from automation_api.domain.folhapress import FolhapressDataError
from automation_api.infrastructure.folhapress import (
    ArticleExtractor,
    FolhapressAuth,
    FolhapressBrowserSession,
    FolhapressCatalog,
    SourceHealth,
)
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository
from automation_api.infrastructure.minio import RawStorage, build_s3_client
from automation_api.infrastructure.postgres import build_postgresql_engine
from automation_api.observability import configure_automation_logging
from automation_api.settings import Settings


@dataclass(frozen=True)
class ReconciliationFailure:
    source_id: str
    diagnostic_code: str


@dataclass(frozen=True)
class ReconciliationResult:
    scanned: int
    repaired: int
    skipped: int
    failed: int
    failures: tuple[ReconciliationFailure, ...]


def run_folhapress_reconciliation(settings: Settings, *, limit: int = 100) -> ReconciliationResult:
    """Repara filas antigas com o TXT existente, sem endpoint HTTP ou exclusÃ£o."""

    if limit < 1:
        raise ValueError("limit deve ser maior que zero")

    configure_automation_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    configuration = settings.folhapress()
    engine = build_postgresql_engine(
        settings.resolved_database_url,
        settings.health_check_timeout_seconds,
    )
    try:
        repository = GoldNewsRepository(engine)
        candidates = repository.find_reconciliation_candidates(limit=limit)
        if not candidates:
            return ReconciliationResult(0, 0, 0, 0, ())

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
        repaired = 0
        skipped = 0
        failures: list[ReconciliationFailure] = []
        with FolhapressBrowserSession(configuration) as session:
            SourceHealth(session.page, configuration).check()
            FolhapressAuth(session.page, configuration).login()
            # O chapéu e o título editorial vêm do link visível do catálogo,
            # não da página técnica da matéria. Guarde a referência descoberta
            # para que a reconciliação use exatamente a mesma regra da captura.
            catalog_references = {
                reference.source_id: reference
                for reference in FolhapressCatalog(session.page, configuration).list_articles()
            }
            extractor = ArticleExtractor(
                session.page,
                timeout_ms=configuration.navigation_timeout_ms,
                navigation_attempts=configuration.navigation_attempts,
            )
            summary_generator = SumyLsaEditorialSummary()
            for candidate in candidates:
                try:
                    original_txt = raw_storage.load(candidate.minio_object_key)
                    if sha256(original_txt).hexdigest() != candidate.raw_sha256.lower():
                        raise FolhapressDataError(
                            "O TXT armazenado nÃ£o corresponde ao hash da fila",
                            diagnostic_code="raw_hash_mismatch",
                        )
                    reference = catalog_references.get(candidate.source_id)
                    if reference is None:
                        raise FolhapressDataError(
                            "A matéria não está no catálogo atual para extrair o chapéu",
                            diagnostic_code="catalog_reference_missing",
                        )
                    extracted = extractor.extract(reference)
                    draft = extractor.build_draft(extracted, original_txt)
                    try:
                        summary = summary_generator.generate(draft.content)
                    except Exception:
                        summary = None
                        logger.warning(
                            "reconciliation_summary_not_generated source_id=%s",
                            candidate.source_id,
                        )
                    if repository.repair_queue_item(candidate, draft, summary):
                        repaired += 1
                    else:
                        skipped += 1
                except Exception as error:
                    code = getattr(error, "diagnostic_code", "unexpected_error")
                    failures.append(ReconciliationFailure(candidate.source_id, str(code)))
                    logger.warning(
                        "reconciliation_item_failed source_id=%s code=%s",
                        candidate.source_id,
                        code,
                    )
        return ReconciliationResult(
            scanned=len(candidates),
            repaired=repaired,
            skipped=skipped,
            failed=len(failures),
            failures=tuple(failures),
        )
    finally:
        engine.dispose()
