from pathlib import Path
import unittest


MIGRATION = Path("infra/migrations/001_initial_editorial_schema.sql")


class InitialSchemaContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_physical_layers_are_created(self) -> None:
        for table in (
            "operational.ingestion_runs",
            "operational.object_receipts",
            "bronze.articles",
            "silver.articles",
            "gold.articles",
            "operational.audit_events",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", self.sql)

    def test_bronze_identity_and_integrity_are_enforced(self) -> None:
        self.assertIn("UNIQUE (source, source_id)", self.sql)
        self.assertIn("bronze_require_verified_object_trigger", self.sql)
        self.assertIn("Bronze exige objeto MinIO verificado", self.sql)

    def test_bronze_and_gold_are_immutable(self) -> None:
        self.assertIn("bronze_immutable_trigger", self.sql)
        self.assertIn("gold_immutable_trigger", self.sql)

    def test_gold_requires_author(self) -> None:
        self.assertIn("author_name TEXT NOT NULL", self.sql)

    def test_raw_metadata_uses_jsonb(self) -> None:
        self.assertIn("raw_metadata JSONB NOT NULL", self.sql)
        self.assertIn("normalized_metadata JSONB NOT NULL", self.sql)

    def test_operational_states_have_required_timestamps(self) -> None:
        self.assertIn("status <> 'running' AND finished_at IS NOT NULL", self.sql)
        self.assertIn("status NOT IN ('verified', 'linked')", self.sql)


if __name__ == "__main__":
    unittest.main()
