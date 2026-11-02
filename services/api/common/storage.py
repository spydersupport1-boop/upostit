"""MinIO / S3 Object Storage client with tenant-isolated paths."""

import logging
import uuid
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from services.api.config import settings

logger = logging.getLogger("attendance.storage")


class StorageService:
    """Manages secure, tenant-isolated object storage operations targeting MinIO or AWS S3."""

    def __init__(self) -> None:
        self.bucket_name = settings.STORAGE_BUCKET
        self._s3_client: Any = None
        self._memory_store: dict[str, bytes] = {}

    def _get_client(self) -> Any:
        if self._s3_client is None:
            endpoint = settings.STORAGE_ENDPOINT if settings.STORAGE_ENDPOINT else None
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=settings.STORAGE_ACCESS_KEY,
                aws_secret_access_key=settings.STORAGE_SECRET_KEY,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                use_ssl=settings.STORAGE_USE_SSL,
            )
        return self._s3_client

    @staticmethod
    def get_tenant_import_path(tenant_id: uuid.UUID, job_id: uuid.UUID, filename: str) -> str:
        """Derives a strictly tenant-isolated S3 key for an import file."""
        clean_name = filename.strip().replace("..", "").replace("/", "").replace("\\", "")
        return f"tenants/{tenant_id}/imports/{job_id}/{clean_name}"

    @staticmethod
    def get_tenant_error_report_path(tenant_id: uuid.UUID, job_id: uuid.UUID) -> str:
        """Derives a strictly tenant-isolated S3 key for an import failure report."""
        return f"tenants/{tenant_id}/imports/{job_id}/errors.csv"

    def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Uploads raw file bytes to object storage. Falls back to memory cache if S3 daemon is offline."""
        try:
            client = self._get_client()
            client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            logger.info("Successfully uploaded %d bytes to S3 key %s", len(data), key)
        except (EndpointConnectionError, ClientError, Exception) as exc:
            is_dev_or_test = settings.ENVIRONMENT.lower() in ("development", "test")
            if is_dev_or_test and settings.STORAGE_ALLOW_MEMORY_FALLBACK:
                logger.warning(
                    "S3/MinIO endpoint unreachable (%s). Using local storage fallback for key: %s (DEVELOPMENT/TEST ONLY)",
                    exc,
                    key,
                )
                self._memory_store[key] = data
                return key
            logger.error("Durable S3/MinIO storage upload failed: %s", exc)
            raise RuntimeError(
                f"Durable object storage upload failed: {exc!s}. Production environments require configured S3/MinIO."
            ) from exc
        return key

    def download_file(self, key: str) -> bytes:
        """Downloads file bytes from object storage or memory cache in dev/test."""
        is_dev_or_test = settings.ENVIRONMENT.lower() in ("development", "test")
        if key in self._memory_store and is_dev_or_test and settings.STORAGE_ALLOW_MEMORY_FALLBACK:
            return self._memory_store[key]

        try:
            client = self._get_client()
            response = client.get_object(Bucket=self.bucket_name, Key=key)
            data: bytes = response["Body"].read()
            return data
        except (EndpointConnectionError, ClientError, Exception) as exc:
            if is_dev_or_test and settings.STORAGE_ALLOW_MEMORY_FALLBACK and key in self._memory_store:
                return self._memory_store[key]
            raise FileNotFoundError(f"Object not found in storage: {key}") from exc

    def delete_file(self, key: str) -> bool:
        """Deletes an object from storage."""
        self._memory_store.pop(key, None)
        try:
            client = self._get_client()
            client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception as exc:
            logger.warning("Could not delete S3 key %s: %s", key, exc)
            return False


storage_service = StorageService()
