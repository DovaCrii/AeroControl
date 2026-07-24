"""Document storage backends.

The local backend keeps development and existing installations unchanged. The
S3 backend stores only an object key in ``Document.file_path`` and keeps the
bucket private; views remain responsible for authorization before opening an
object.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

import boto3
from botocore.exceptions import ClientError
from django.conf import settings


class DocumentStorageError(RuntimeError):
    """Base exception for storage failures."""


class DocumentStorageNotFound(DocumentStorageError):
    """Raised when a document object does not exist."""


class DocumentStorage(Protocol):
    def save(self, key: str, uploaded: BinaryIO) -> None: ...

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


def normalize_storage_key(key: str) -> str:
    """Reject absolute and traversal paths before touching a backend."""
    path = PurePosixPath(str(key))
    if not key or path.is_absolute() or ".." in path.parts:
        raise DocumentStorageError("Invalid document storage key")
    return path.as_posix()


class LocalDocumentStorage:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        normalized = normalize_storage_key(key)
        path = (self.root / normalized).resolve()
        if self.root not in path.parents:
            raise DocumentStorageError("Document path escaped configured storage root")
        return path

    def save(self, key: str, uploaded: BinaryIO) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.part")
        try:
            uploaded.seek(0)
            with temporary.open("wb") as destination:
                for chunk in iter(lambda: uploaded.read(1024 * 1024), b""):
                    destination.write(chunk)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def open(self, key: str) -> BinaryIO:
        path = self._path(key)
        try:
            return path.open("rb")
        except FileNotFoundError as exc:
            raise DocumentStorageNotFound(key) from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3DocumentStorage:
    def __init__(self):
        self.bucket = settings.DOCUMENTS_STORAGE_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.DOCUMENTS_STORAGE_ENDPOINT_URL or None,
            region_name=settings.DOCUMENTS_STORAGE_REGION or None,
            aws_access_key_id=settings.DOCUMENTS_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.DOCUMENTS_STORAGE_SECRET_KEY,
        )

    def save(self, key: str, uploaded: BinaryIO) -> None:
        try:
            uploaded.seek(0)
            self.client.upload_fileobj(
                uploaded,
                self.bucket,
                normalize_storage_key(key),
                ExtraArgs={
                    "ContentType": getattr(uploaded, "content_type", None)
                    or "application/octet-stream"
                },
            )
        except ClientError as exc:
            raise DocumentStorageError("Could not save document") from exc

    def open(self, key: str) -> BinaryIO:
        try:
            response = self.client.get_object(
                Bucket=self.bucket, Key=normalize_storage_key(key)
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise DocumentStorageNotFound(key) from exc
            raise DocumentStorageError("Could not open document") from exc
        return response["Body"]

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=normalize_storage_key(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NotFound"}:
                return False
            raise DocumentStorageError("Could not inspect document") from exc
        return True

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=normalize_storage_key(key))
        except ClientError as exc:
            raise DocumentStorageError("Could not delete document") from exc


def get_document_storage() -> DocumentStorage:
    backend = settings.DOCUMENTS_STORAGE_BACKEND.lower()
    if backend == "local":
        return LocalDocumentStorage(settings.DOCUMENTS_ROOT)
    if backend == "s3":
        return S3DocumentStorage()
    raise DocumentStorageError(f"Unsupported document storage backend: {backend}")
