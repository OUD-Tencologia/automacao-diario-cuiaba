from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
import unittest

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path("apps/automation_api/src").resolve()))

from automation_api.infrastructure.minio import RawStorage, RawStorageError


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.put_calls = 0

    def head_bucket(self, *, Bucket: str) -> None:
        return None

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            return self.objects[(Bucket, Key)]
        except KeyError as error:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject") from error

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls += 1
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
            "ContentLength": len(kwargs["Body"]),
            "Metadata": kwargs["Metadata"],
        }


class RawStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeS3Client()
        self.storage = RawStorage("bronze-raw", self.client)

    def test_stores_content_with_source_id_and_sha256_in_key(self) -> None:
        stored = self.storage.store("Folhapress", "2599841", b"texto sintetico")

        self.assertEqual(stored.bucket, "bronze-raw")
        self.assertEqual(stored.size_bytes, len(b"texto sintetico"))
        self.assertEqual(
            stored.object_key,
            f"folhapress/2599841/{stored.sha256}.txt",
        )
        self.assertEqual(self.client.put_calls, 1)

    def test_same_content_does_not_overwrite_existing_object(self) -> None:
        self.storage.store("folhapress", "2599841", b"texto sintetico")
        stored = self.storage.store("folhapress", "2599841", b"texto sintetico")

        self.assertEqual(self.client.put_calls, 1)
        self.assertIn(("bronze-raw", stored.object_key), self.client.objects)

    def test_rejects_object_key_path_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "caracteres inválidos"):
            self.storage.store("folhapress", "../2599841", b"texto")

    def test_rejects_integrity_mismatch_for_existing_object(self) -> None:
        stored = self.storage.store("folhapress", "2599841", b"texto sintetico")
        self.client.objects[("bronze-raw", stored.object_key)]["Metadata"]["sha256"] = "0" * 64

        with self.assertRaises(RawStorageError):
            self.storage.store("folhapress", "2599841", b"texto sintetico")
