from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from automation_api.application.capture_folhapress import CaptureCycleError, CaptureResult
from automation_api.application.folhapress_runner import run_folhapress_capture
from automation_api.infrastructure.folhapress.errors import FolhapressSourceError
from automation_api.settings import get_settings


router = APIRouter(prefix="/automation", tags=["automation"])


class CaptureResponse(BaseModel):
    scanned: int = Field(ge=0)
    captured: int = Field(ge=0)
    skipped_existing: int = Field(ge=0)

    @classmethod
    def from_result(cls, result: CaptureResult) -> CaptureResponse:
        return cls(
            scanned=result.scanned,
            captured=result.captured,
            skipped_existing=result.skipped_existing,
        )


@router.post(
    "/folhapress/capture",
    summary="Executa um ciclo Folhapress para uso exclusivo do n8n",
    response_model=CaptureResponse,
    responses={
        502: {"description": "A fonte externa não pôde ser processada."},
        503: {"description": "A captura não está configurada ou a infraestrutura falhou."},
    },
)
def capture_folhapress() -> CaptureResponse:
    try:
        return CaptureResponse.from_result(run_folhapress_capture(get_settings()))
    except (FolhapressSourceError, CaptureCycleError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="A captura Folhapress falhou; o n8n deve reexecutar o ciclo.",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A captura Folhapress não está configurada.",
        ) from error
