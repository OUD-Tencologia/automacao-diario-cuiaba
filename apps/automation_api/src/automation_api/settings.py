from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr
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
    folhapress_enabled: bool = True
    folhapress_base_url: str = "https://folhapress.folha.com.br"
    folhapress_login_url: str = "https://folhapress.folha.com.br/login"
    folhapress_catalog_url: str = "https://folhapress.folha.com.br/textos"
    folhapress_username: SecretStr = SecretStr("")
    folhapress_password: SecretStr = SecretStr("")
    folhapress_article_link_selector: str = 'a[href*="/texto/"]'
    folhapress_catalog_query: str | None = None
    folhapress_required_catalog_labels: str = "TEXTOS,SERVIÇO NOTICIOSO"
    folhapress_page_size: int = Field(default=24, ge=1, le=100)
    folhapress_max_pages_per_cycle: int = Field(default=20, ge=1, le=100)
    folhapress_navigation_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    folhapress_navigation_attempts: int = Field(default=3, ge=1, le=5)
    folhapress_headless: bool = True
    folhapress_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    folhapress_login_username_selector: str | None = None
    folhapress_login_password_selector: str | None = None
    folhapress_login_submit_selector: str | None = None

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

    def folhapress(self) -> FolhapressConfiguration:
        return FolhapressConfiguration.from_settings(self)


@dataclass(frozen=True)
class FolhapressConfiguration:
    """Configuração específica da fonte, validada somente quando ela é usada."""

    base_url: str
    login_url: str
    catalog_url: str
    username: str
    password: str
    article_link_selector: str
    catalog_query: str | None
    required_catalog_labels: tuple[str, ...]
    page_size: int
    max_pages_per_cycle: int
    navigation_timeout_ms: int
    headless: bool
    login_username_selector: str | None
    login_password_selector: str | None
    login_submit_selector: str | None
    navigation_attempts: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    @classmethod
    def from_settings(cls, settings: Settings) -> FolhapressConfiguration:
        if not settings.folhapress_enabled:
            raise ValueError("Folhapress está desabilitada nesta configuração")

        username = settings.folhapress_username.get_secret_value().strip()
        password = settings.folhapress_password.get_secret_value()
        if not username or not password:
            raise ValueError("FOLHAPRESS_USERNAME e FOLHAPRESS_PASSWORD são obrigatórios")

        labels = tuple(
            label.strip()
            for label in settings.folhapress_required_catalog_labels.split(",")
            if label.strip()
        )
        return cls(
            base_url=settings.folhapress_base_url.rstrip("/"),
            login_url=settings.folhapress_login_url,
            catalog_url=settings.folhapress_catalog_url,
            username=username,
            password=password,
            article_link_selector=settings.folhapress_article_link_selector,
            catalog_query=_optional_config(settings.folhapress_catalog_query),
            required_catalog_labels=labels,
            page_size=settings.folhapress_page_size,
            max_pages_per_cycle=settings.folhapress_max_pages_per_cycle,
            navigation_timeout_ms=settings.folhapress_navigation_timeout_ms,
            headless=settings.folhapress_headless,
            login_username_selector=_optional_config(settings.folhapress_login_username_selector),
            login_password_selector=_optional_config(settings.folhapress_login_password_selector),
            login_submit_selector=_optional_config(settings.folhapress_login_submit_selector),
            navigation_attempts=settings.folhapress_navigation_attempts,
            user_agent=settings.folhapress_user_agent.strip(),
        )


def _optional_config(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
