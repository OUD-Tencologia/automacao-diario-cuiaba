from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from fastapi.testclient import TestClient

from automation_api.application.readiness import ReadinessService
from automation_api.main import create_app
from automation_api.settings import Settings


class FakeProbe:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = 0

    def ping(self) -> None:
        self.calls += 1
        if self.should_fail:
            raise ConnectionError("synthetic dependency failure")


def build_client(postgres_fails: bool = False, minio_fails: bool = False) -> TestClient:
    readiness = ReadinessService(
        {
            "postgresql": FakeProbe(postgres_fails),
            "minio": FakeProbe(minio_fails),
        }
    )
    return TestClient(create_app(readiness))


class AutomationApiHealthTest(unittest.TestCase):
    def test_liveness_does_not_require_external_dependencies(self) -> None:
        response = build_client(postgres_fails=True, minio_fails=True).get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_is_healthy_when_postgres_and_minio_are_available(self) -> None:
        response = build_client().get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["dependencies"]["postgresql"]["status"], "up")
        self.assertEqual(response.json()["dependencies"]["minio"]["status"], "up")

    def test_readiness_returns_503_without_false_success(self) -> None:
        response = build_client(minio_fails=True).get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "not_ready")
        self.assertEqual(response.json()["dependencies"]["postgresql"]["status"], "up")
        self.assertEqual(response.json()["dependencies"]["minio"]["status"], "down")
        self.assertNotIn("synthetic dependency failure", response.text)

    def test_openapi_includes_the_initial_health_contract(self) -> None:
        response = build_client().get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/health/live", response.json()["paths"])
        self.assertIn("/health/ready", response.json()["paths"])
        self.assertIn("/automation/folhapress/capture", response.json()["paths"])
        self.assertIn("/editorial/articles", response.json()["paths"])
        self.assertIn("/editorial/articles/{source}/{source_id}", response.json()["paths"])
        self.assertEqual(response.json()["info"]["title"], "Automation API — Diário Cuiabá")

    def test_container_aliases_use_the_homologation_host_for_local_development(self) -> None:
        settings = Settings.model_validate(
            {
                "APP_ENV": "development",
                "DATABASE_URL": "postgresql+psycopg://editorial:secret@postgres:5432/editorial",
                "POSTGRES_HOST": "postgres",
                "POSTGRES_PORT": "5432",
                "POSTGRES_DB": "editorial",
                "POSTGRES_USER": "editorial",
                "POSTGRES_PASSWORD": "secret",
                "MINIO_ENDPOINT": "http://minio:9000",
                "MINIO_HOST": "minio",
                "MINIO_PORT": "9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
                "MINIO_BUCKET_BRONZE": "bronze-raw",
                "VPS_HOMOLOGATION_HOST": "homologation.example",
            }
        )

        self.assertIn("homologation.example", str(settings.resolved_database_url))
        self.assertEqual(settings.resolved_minio_endpoint, "http://homologation.example:9000")

    def test_explicit_external_endpoints_are_preserved(self) -> None:
        settings = Settings.model_validate(
            {
                "DATABASE_URL": "postgresql+psycopg://editorial:secret@db.example:5432/editorial",
                "POSTGRES_DB": "editorial",
                "POSTGRES_USER": "editorial",
                "POSTGRES_PASSWORD": "secret",
                "MINIO_ENDPOINT": "https://objects.example:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
                "MINIO_BUCKET_BRONZE": "bronze-raw",
                "VPS_HOMOLOGATION_HOST": "",
            }
        )

        self.assertEqual(settings.resolved_database_url, settings.database_url)
        self.assertEqual(settings.resolved_minio_endpoint, "https://objects.example:9000")

    def test_development_always_targets_the_configured_homologation_vps(self) -> None:
        settings = Settings.model_validate(
            {
                "APP_ENV": "development",
                "DATABASE_URL": "postgresql+psycopg://editorial:secret@stale.example:5432/editorial",
                "POSTGRES_DB": "editorial",
                "POSTGRES_USER": "editorial",
                "POSTGRES_PASSWORD": "secret",
                "MINIO_ENDPOINT": "http://minio:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
                "MINIO_BUCKET_BRONZE": "bronze-raw",
                "VPS_HOMOLOGATION_HOST": "homologation.example",
            }
        )

        self.assertIn("homologation.example", str(settings.resolved_database_url))

    def test_homologation_container_keeps_internal_docker_aliases(self) -> None:
        settings = Settings.model_validate(
            {
                "APP_ENV": "homologation",
                "DATABASE_URL": "postgresql+psycopg://editorial:secret@postgres:5432/editorial",
                "POSTGRES_DB": "editorial",
                "POSTGRES_USER": "editorial",
                "POSTGRES_PASSWORD": "secret",
                "MINIO_ENDPOINT": "http://minio:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
                "MINIO_BUCKET_BRONZE": "bronze-raw",
                "VPS_HOMOLOGATION_HOST": "homologation.example",
            }
        )

        self.assertEqual(settings.resolved_database_url, settings.database_url)
        self.assertEqual(settings.resolved_minio_endpoint, "http://minio:9000")


if __name__ == "__main__":
    unittest.main()
