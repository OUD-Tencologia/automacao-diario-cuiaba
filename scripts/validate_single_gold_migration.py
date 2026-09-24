"""Valida a transição 001 -> 002 em banco temporário e o remove ao final."""

from __future__ import annotations

from pathlib import Path
import sys

from psycopg import connect, sql
from sqlalchemy.engine import URL, make_url

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.settings import get_settings


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "infra/migrations/001_initial_editorial_schema.sql",
    ROOT / "infra/migrations/002_mvp_single_gold_schema.sql",
)
TEST_DATABASE = "automacao_editorial_sprint1_validation"


def _connection_url(database: str) -> URL:
    configured = get_settings().resolved_database_url
    if not isinstance(configured, URL):
        configured = make_url(configured)
    return configured.set(database=database)


def _connect(url: URL, *, autocommit: bool = False):
    return connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        autocommit=autocommit,
    )


def main() -> None:
    admin_url = _connection_url("postgres")
    target_url = _connection_url(TEST_DATABASE)
    created = False

    with _connect(admin_url, autocommit=True) as admin:
        exists = admin.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
            (TEST_DATABASE,),
        ).fetchone()[0]
        if exists:
            raise RuntimeError(
                f"Banco temporário {TEST_DATABASE} já existe; remova-o manualmente antes de validar."
            )
        admin.execute(sql.SQL("CREATE DATABASE {}") .format(sql.Identifier(TEST_DATABASE)))
        created = True

    try:
        with _connect(target_url, autocommit=True) as target:
            for migration in MIGRATIONS:
                target.execute(migration.read_text(encoding="utf-8"))

            table_exists = target.execute(
                "SELECT to_regclass('gold.articles') IS NOT NULL"
            ).fetchone()[0]
            legacy_schema_count = target.execute(
                "SELECT count(*) FROM pg_namespace "
                "WHERE nspname IN ('operational', 'bronze', 'silver')"
            ).fetchone()[0]
            if not table_exists or legacy_schema_count != 0:
                raise RuntimeError("Estrutura final da Gold única não corresponde ao contrato")

            target.execute(
                """
                INSERT INTO gold.articles (
                    source, id, dt_noticia, ds_titulo, ds_noticia, source_url,
                    minio_bucket, minio_object_key, raw_sha256, raw_size_bytes
                ) VALUES (
                    'folhapress', '9990001', now(), 'Matéria sintética',
                    'Texto sintético de validação.', 'https://example.test/9990001',
                    'bronze-raw', 'folhapress/9990001/teste.txt', repeat('a', 64), 32
                )
                """
            )
            target.execute(
                "UPDATE gold.articles SET ds_titulo = 'Matéria editada' "
                "WHERE source = 'folhapress' AND id = '9990001'"
            )

            try:
                target.execute(
                    "DELETE FROM gold.articles WHERE source = 'folhapress' AND id = '9990001'"
                )
            except Exception as error:
                if "STATUS=DESCARTADO" not in str(error):
                    raise
            else:
                raise RuntimeError("DELETE da Gold deveria ser bloqueado")
    finally:
        if created:
            with _connect(admin_url, autocommit=True) as admin:
                admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (TEST_DATABASE,),
                )
                admin.execute(sql.SQL("DROP DATABASE {}") .format(sql.Identifier(TEST_DATABASE)))

    print("single_gold_migration=ok")


if __name__ == "__main__":
    main()
