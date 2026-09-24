from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel, Field

from automation_api.application.readiness import ReadinessService
from automation_api.infrastructure.minio import MinioProbe
from automation_api.infrastructure.postgres import PostgreSQLProbe
from automation_api.settings import Settings, get_settings


class ComponentHealthResponse(BaseModel):
    status: Literal["up", "down"]
    latency_ms: int = Field(ge=0)


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, ComponentHealthResponse]


def build_readiness_service(settings: Settings) -> ReadinessService:
    timeout = settings.health_check_timeout_seconds
    return ReadinessService(
        {
            "postgresql": PostgreSQLProbe(settings.resolved_database_url, timeout),
            "minio": MinioProbe(
                endpoint=settings.resolved_minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key.get_secret_value(),
                region=settings.minio_region,
                timeout_seconds=timeout,
                bucket_name=settings.minio_bucket_bronze,
            ),
        }
    )


@lru_cache
def get_readiness_service() -> ReadinessService:
    return build_readiness_service(get_settings())


def create_app(readiness_service: ReadinessService | None = None) -> FastAPI:
    app = FastAPI(
        title="Automation API — Diário Cuiabá",
        version="0.1.0",
        description=(
            "API de automação editorial. O n8n a utiliza como única porta "
            "para ingestão de conteúdo Folhapress e persistência na Gold única."
        ),
    )
    app.state.readiness_service = readiness_service

    @app.get("/health/live", tags=["health"], summary="Liveness da API")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/health/ready",
        tags=["health"],
        summary="Readiness de PostgreSQL e MinIO",
        response_model=ReadinessResponse,
        responses={503: {"description": "Uma dependência crítica está indisponível."}},
    )
    def readiness(request: Request, response: Response) -> ReadinessResponse:
        service: ReadinessService = (
            request.app.state.readiness_service or get_readiness_service()
        )
        result = service.check()
        if not result.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return ReadinessResponse(
            status="ready" if result.ready else "not_ready",
            dependencies={
                name: ComponentHealthResponse(
                    status=dependency.status,
                    latency_ms=dependency.latency_ms,
                )
                for name, dependency in result.dependencies.items()
            },
        )

    return app


app = create_app()
