from pathlib import Path
import unittest


SCRIPT = Path("scripts/provision_minio_buckets.ps1")


class MinioProvisioningContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_uses_the_three_configured_buckets(self) -> None:
        for variable in (
            "MINIO_BUCKET_BRONZE",
            "MINIO_BUCKET_SILVER",
            "MINIO_BUCKET_GOLD",
        ):
            self.assertIn(variable, self.script)

    def test_bronze_has_retention_and_all_buckets_are_versioned(self) -> None:
        self.assertIn("mc_cmd mb --ignore-existing --with-lock", self.script)
        self.assertIn("mc_cmd retention set --default GOVERNANCE", self.script)
        self.assertIn("mc_cmd version enable", self.script)

    def test_checks_upload_download_and_persistence(self) -> None:
        self.assertIn("docker run --rm -i --network", self.script)
        self.assertIn("mc_cmd pipe", self.script)
        self.assertIn("mc_cmd cat", self.script)
        self.assertIn("docker restart", self.script)
        self.assertIn("persistence_after_restart=ok", self.script)

    def test_never_reads_minio_secrets_from_the_local_env_file(self) -> None:
        self.assertNotIn('$configuration["MINIO_ROOT_PASSWORD"]', self.script)
        self.assertNotIn('$configuration["MINIO_SECRET_KEY"]', self.script)

    def test_removes_the_remote_client_configuration(self) -> None:
        self.assertIn("/tmp/automacao-editorial-mc.XXXXXX", self.script)
        self.assertIn("find /cleanup -mindepth 1 -delete", self.script)

    def test_is_idempotent_when_buckets_already_exist(self) -> None:
        self.assertIn("if ! mc_cmd mb", self.script)
        self.assertIn("if ! mc_cmd version enable", self.script)
        self.assertIn("mc_cmd version info", self.script)


if __name__ == "__main__":
    unittest.main()
