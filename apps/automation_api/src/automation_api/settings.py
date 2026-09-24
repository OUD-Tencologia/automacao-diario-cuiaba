from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Configuração local; valores reais existem somente no .env ignorado."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    automation_api_host: str = "0.0.0.0"
    automation_api_port: int = 8000
    database_url: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    minio_endpoint: str
    minio_host: str = "minio"
    minio_port: int = 9000
    minio_access_key: str
    minio_secret_key: SecretStr
    minio_bucket_bronze: str
    minio_region: str = "us-east-1"
    vps_homologation_host: str | None = None
    health_check_timeout_seconds: int = 5

    @property
    def resolved_database_url(self) -> str | URL:
        """Prioriza URL explícita externa; aliases Docker usam o host da VPS."""

        if self.app_env == "development" and self.vps_homologation_host:
            return URL.create(
                drivername="postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password.get_secret_value(),
                host=self.vps_homologation_host,
                port=self.postgres_port,
                database=self.postgres_db,
            )

        configured_url = make_url(self.database_url)
        if configured_url.host and configured_url.host != "postgres":
            return self.database_url

        host = self._resolve_container_alias(self.postgres_host, "postgres")
        if host == "postgres":
            return self.database_url

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def resolved_minio_endpoint(self) -> str:
        """Mantém endpoint externo explícito ou troca somente o alias Docker."""

        configured_url = urlsplit(self.minio_endpoint)
        configured_host = configured_url.hostname
        if configured_host and configured_host != "minio":
            return self.minio_endpoint

        host = self._resolve_container_alias(self.minio_host, "minio")
        if host == "minio":
            return self.minio_endpoint

        scheme = configured_url.scheme or "http"
        port = configured_url.port or self.minio_port
        return urlunsplit((scheme, f"{host}:{port}", "", "", ""))

    def _resolve_container_alias(self, configured_host: str, alias: str) -> str:
        if (
            self.app_env == "development"
            and configured_host == alias
            and self.vps_homologation_host
        ):
            return self.vps_homologation_host
        return configured_host


@lru_cache
def get_settings() -> Settings:
    return Settings()
