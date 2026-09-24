"""Normaliza locais existentes usando somente o TXT original no MinIO."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging

from automation_api.domain.folhapress import normalize_location
from automation_api.infrastructure.folhapress.extractor import decode_original_text
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository
from automation_api.infrastructure.minio import RawStorage, build_s3_client
from automation_api.infrastructure.postgres import build_postgresql_engine
from automation_api.observability import configure_automation_logging
from automation_api.settings import Settings


@dataclass(frozen=True)
class LocationNormalizationResult:
    scanned: int
    repaired: int
    skipped: int
    failed: int


def run_folhapress_location_normalization(
    settings: Settings, *, limit: int = 100
) -> LocationNormalizationResult:
    """Converte abertura Folhapress em ``Cidade, UF`` sem navegar na fonte."""

    if limit < 1:
        raise ValueError("limit deve ser maior que zero")

    configure_automation_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    engine = build_postgresql_engine(
        settings.resolved_database_url,
        settings.health_check_timeout_seconds,
    )
    repository = GoldNewsRepository(engine)
    storage = RawStorage(
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
    failed = 0
    try:
        candidates = repository.find_location_normalization_candidates(limit=limit)
        for candidate in candidates:
            try:
                raw = storage.load(candidate.minio_object_key)
                if sha256(raw).hexdigest().lower() != candidate.raw_sha256.lower():
                    raise ValueError("raw_sha256_mismatch")
                location = normalize_location(decode_original_text(raw))
                if location is None:
                    skipped += 1
                elif repository.repair_location_from_raw(candidate, location):
                    repaired += 1
                else:
                    skipped += 1
            except Exception as error:  # prossegue sem apagar nem corromper a fila
                failed += 1
                logger.warning(
                    "location_normalization_item_failed source_id=%s code=%s",
                    candidate.source_id,
                    getattr(error, "diagnostic_code", type(error).__name__),
                )
        return LocationNormalizationResult(
            scanned=len(candidates), repaired=repaired, skipped=skipped, failed=failed
        )
    finally:
        engine.dispose()
