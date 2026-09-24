from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from automation_api.domain.news import StoredRawObject


class S3Client(Protocol):
    def head_bucket(self, *, Bucket: str) -> Any: ...

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...

    def put_object(self, **kwargs: Any) -> Any: ...


class RawStorageError(RuntimeError):
    """Indica uma divergência entre o arquivo enviado e o objeto persistido."""


class MinioProbe:
    """Confirma acesso ao bucket usado pelo MVP, sem exigir acesso administrativo."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str,
        timeout_seconds: int,
        bucket_name: str,
        client: S3Client | None = None,
    ) -> None:
        self._client = client or build_s3_client(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            timeout_seconds=timeout_seconds,
        )
        self._bucket_name = bucket_name

    def ping(self) -> None:
        self._client.head_bucket(Bucket=self._bucket_name)


class RawStorage:
    """Armazena TXT original de forma determinística e verifica sua integridade."""

    def __init__(self, bucket_name: str, client: S3Client) -> None:
        if not bucket_name.strip():
            raise ValueError("bucket_name é obrigatório")
        self._bucket_name = bucket_name.strip()
        self._client = client

    @staticmethod
    def build_object_key(source: str, source_id: str, content_sha256: str) -> str:
        normalized_source = _safe_path_component(source, "source")
        normalized_id = _safe_path_component(source_id, "source_id")
        if not re.fullmatch(r"[a-f0-9]{64}", content_sha256):
            raise ValueError("content_sha256 deve ter 64 caracteres hexadecimais")
        return f"{normalized_source}/{normalized_id}/{content_sha256}.txt"

    def store(self, source: str, source_id: str, content: bytes) -> StoredRawObject:
        if not content:
            raise ValueError("TXT original não pode estar vazio")

        digest = sha256(content).hexdigest()
        object_key = self.build_object_key(source, source_id, digest)

        try:
            head = self._client.head_object(Bucket=self._bucket_name, Key=object_key)
        except ClientError as error:
            if _is_missing_object(error):
                self._client.put_object(
                    Bucket=self._bucket_name,
                    Key=object_key,
                    Body=content,
                    ContentType="text/plain; charset=utf-8",
                    Metadata={"sha256": digest, "source": source.strip().lower(), "source-id": source_id.strip()},
                )
                head = self._client.head_object(Bucket=self._bucket_name, Key=object_key)
            else:
                raise

        _assert_integrity(head, content_size=len(content), digest=digest, object_key=object_key)
        return StoredRawObject(
            bucket=self._bucket_name,
            object_key=object_key,
            sha256=digest,
            size_bytes=len(content),
        )

    def load(self, object_key: str) -> bytes:
        """LÃª um original jÃ¡ armazenado, sem criar ou sobrescrever objetos."""

        response = self._client.get_object(Bucket=self._bucket_name, Key=object_key)
        body = response.get("Body")
        content = body.read() if body is not None else b""
        if not isinstance(content, bytes) or not content:
            raise RawStorageError("O objeto MinIO nÃ£o possui TXT vÃ¡lido")
        return content


def build_s3_client(
    *, endpoint: str, access_key: str, secret_key: str, region: str, timeout_seconds: int
) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            retries={"max_attempts": 0},
            s3={"addressing_style": "path"},
        ),
    )


def _safe_path_component(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
        raise ValueError(f"{field_name} contém caracteres inválidos para chave MinIO")
    return normalized


def _is_missing_object(error: ClientError) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchObject"}


def _assert_integrity(
    head: dict[str, Any], *, content_size: int, digest: str, object_key: str
) -> None:
    remote_size = head.get("ContentLength")
    remote_hash = str(head.get("Metadata", {}).get("sha256", "")).lower()
    if remote_size != content_size or remote_hash != digest:
        raise RawStorageError(
            f"Objeto MinIO incompatível para {object_key}: tamanho ou hash divergente"
        )
