from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from automation_api.application.capture_folhapress import (
    CaptureCycleError,
    CaptureFailure,
    CaptureResult,
    CaptureSourceError,
)
from automation_api.application.folhapress_runner import run_folhapress_capture
from automation_api.settings import get_settings


router = APIRouter(prefix="/automation", tags=["automation"])


class CaptureResponse(BaseModel):
    capture_id: str = Field(min_length=1)
    scanned: int = Field(ge=0)
    captured: int = Field(ge=0)
    skipped_existing: int = Field(ge=0)
    failed: int = Field(ge=0)
    duration_ms: int = Field(ge=0)

    @classmethod
    def from_result(cls, result: CaptureResult) -> CaptureResponse:
        return cls(
            capture_id=result.capture_id,
            scanned=result.scanned,
            captured=result.captured,
            skipped_existing=result.skipped_existing,
            failed=result.failed,
            duration_ms=result.duration_ms,
        )


class CaptureFailureResponse(BaseModel):
    source_id: str | None
    stage: str
    diagnostic_code: str
    retryable: bool

    @classmethod
    def from_failure(cls, failure: CaptureFailure) -> CaptureFailureResponse:
        return cls(
            source_id=failure.source_id,
            stage=failure.stage,
            diagnostic_code=failure.diagnostic_code,
            retryable=failure.retryable,
        )


class CaptureErrorResponse(BaseModel):
    detail: str
    result: CaptureResponse
    failures: list[CaptureFailureResponse]


@router.post(
    "/folhapress/capture",
    summary="Executa um ciclo Folhapress para uso exclusivo do n8n",
    response_model=CaptureResponse,
    responses={
        502: {
            "description": "A captura teve falha parcial ou a fonte não pôde ser processada.",
            "model": CaptureErrorResponse,
        },
        503: {"description": "A captura não está configurada ou a infraestrutura falhou."},
    },
)
def capture_folhapress() -> CaptureResponse | JSONResponse:
    capture_id = uuid4().hex
    try:
        return CaptureResponse.from_result(
            run_folhapress_capture(get_settings(), capture_id=capture_id)
        )
    except CaptureCycleError as error:
        return _capture_error_response(error)
    except CaptureSourceError as error:
        return _capture_error_response(
            CaptureCycleError(error.result, [error.failure])
        )
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "A captura Folhapress não está configurada.", "capture_id": capture_id},
        )


def _capture_error_response(error: CaptureCycleError) -> JSONResponse:
    payload = CaptureErrorResponse(
        detail="A captura Folhapress teve itens não processados; consulte os códigos sanitizados.",
        result=CaptureResponse.from_result(error.result),
        failures=[CaptureFailureResponse.from_failure(failure) for failure in error.failures],
    )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=payload.model_dump(mode="json"),
    )
