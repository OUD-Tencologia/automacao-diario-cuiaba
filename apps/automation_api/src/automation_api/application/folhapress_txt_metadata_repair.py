"""Repara metadados Folhapress usando somente os TXT já guardados no MinIO."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging

from automation_api.infrastructure.folhapress.extractor import (
    decode_original_text,
    parse_folhapress_txt_header,
)
from automation_api.infrastructure.gold_news_repository import GoldNewsRepository
from automation_api.infrastructure.minio import RawStorage, build_s3_client
from automation_api.infrastructure.postgres import build_postgresql_engine
from automation_api.observability import configure_automation_logging
from automation_api.settings import Settings


@dataclass(frozen=True)
class TxtMetadataRepairResult:
    scanned: int
    repaired: int
    skipped: int
    failed: int


def run_folhapress_txt_metadata_repair(
    settings: Settings, *, limit: int = 100
) -> TxtMetadataRepairResult:
    """Atualiza cabeçalho, autor, local e data sem nova chamada à Folhapress."""

    if limit < 1:
        raise ValueError("limit deve ser maior que zero")

    configure_automation_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    engine = build_postgresql_engine(
        settings.resolved_database_url,
        settings.health_check_timeout_seconds,
    )
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
        repository = GoldNewsRepository(engine)
        candidates = repository.find_location_normalization_candidates(limit=limit)
        for candidate in candidates:
            try:
                raw = storage.load(candidate.minio_object_key)
                if sha256(raw).hexdigest().lower() != candidate.raw_sha256.lower():
                    raise ValueError("raw_sha256_mismatch")
                header = parse_folhapress_txt_header(decode_original_text(raw))
                if repository.repair_txt_header_metadata(
                    candidate,
                    eyebrow=header.eyebrow,
                    title=header.title,
                    published_at=header.published_at,
                    author=header.author,
                    location=header.location,
                ):
                    repaired += 1
                else:
                    skipped += 1
            except Exception as error:  # não interrompe nem apaga os demais itens
                failed += 1
                logger.warning(
                    "txt_metadata_repair_item_failed source_id=%s code=%s",
                    candidate.source_id,
                    getattr(error, "diagnostic_code", type(error).__name__),
                )
        return TxtMetadataRepairResult(
            scanned=len(candidates), repaired=repaired, skipped=skipped, failed=failed
        )
    finally:
        engine.dispose()
