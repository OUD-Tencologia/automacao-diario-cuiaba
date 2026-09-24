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
