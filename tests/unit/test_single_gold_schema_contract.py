from pathlib import Path
import unittest


MIGRATION = Path("infra/migrations/002_mvp_single_gold_schema.sql")


class SingleGoldSchemaContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_creates_only_the_gold_editorial_table(self) -> None:
        self.assertIn("CREATE TABLE gold.articles", self.sql)
        self.assertNotIn("CREATE TABLE bronze.articles", self.sql)
        self.assertNotIn("CREATE TABLE silver.articles", self.sql)

    def test_preserves_the_editorial_and_raw_contract(self) -> None:
        for column in (
            "dt_noticia TIMESTAMPTZ NOT NULL",
            "ds_chapeu TEXT",
            "ds_noticia TEXT NOT NULL",
            "ds_resumo TEXT CHECK",
            "minio_object_key TEXT NOT NULL",
            "raw_metadata JSONB NOT NULL",
        ):
            self.assertIn(column, self.sql)

    def test_deduplication_and_editing_guards_are_explicit(self) -> None:
        self.assertIn("PRIMARY KEY (source, id)", self.sql)
        self.assertIn("gold_articles_touch_update_at_trigger", self.sql)
        self.assertIn("gold_articles_prevent_delete_trigger", self.sql)
        self.assertIn("STATUS=DESCARTADO", self.sql)

    def test_legacy_data_blocks_destructive_transition(self) -> None:
        self.assertIn("transição para a Gold única foi bloqueada", self.sql)
        self.assertIn("SELECT EXISTS (SELECT 1 FROM %s)", self.sql)
