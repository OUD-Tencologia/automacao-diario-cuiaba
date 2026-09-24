from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL


def build_postgresql_engine(database_url: str | URL, timeout_seconds: int) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": timeout_seconds},
    )


class PostgreSQLProbe:
    """Adapter de conexão PostgreSQL compartilhado pelos futuros repositórios."""

    def __init__(self, database_url: str | URL, timeout_seconds: int) -> None:
        self._engine = build_postgresql_engine(database_url, timeout_seconds)

    def ping(self) -> None:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self._engine.dispose()


class CaptureAlreadyRunningError(RuntimeError):
    """Outra sessão já detém o lock da mesma fonte; não iniciar outro navegador."""


class PostgreSQLAdvisoryLock:
    """Lock de sessão PostgreSQL sem tabela operacional adicional."""

    def __init__(self, engine: Engine, key: str) -> None:
        self._engine = engine
        self._key = key
        self._connection = None

    def __enter__(self) -> PostgreSQLAdvisoryLock:
        connection = self._engine.connect()
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
            {"lock_key": self._key},
        ).scalar_one()
        if not acquired:
            connection.close()
            raise CaptureAlreadyRunningError("Já existe uma captura em andamento")
        self._connection = connection
        return self

    def __exit__(self, *unused: object) -> None:
        if self._connection is None:
            return
        try:
            self._connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                {"lock_key": self._key},
            )
        finally:
            self._connection.close()
            self._connection = None
