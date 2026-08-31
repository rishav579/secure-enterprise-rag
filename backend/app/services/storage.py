import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import AsyncIterator, Protocol

from backend.app.services.ingestion.exceptions import PathTraversalError, PDFSizeLimitExceededError

TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class StorageService(Protocol):
    """Storage abstraction for saving, reading, and deleting raw documents."""

    async def save_stream(
        self,
        tenant_id: str,
        document_id: uuid.UUID,
        stream: AsyncIterator[bytes],
        max_size_bytes: int = 10 * 1024 * 1024,
    ) -> tuple[str, str, int]:
        """Stream bytes directly to storage without loading the full payload into memory.
        
        Returns:
            tuple[file_path, sha256_hash, total_bytes]
        """
        ...

    async def get_stream(self, file_path: str) -> AsyncIterator[bytes]:
        """Read stored document content as a stream."""
        ...

    async def delete_file(self, file_path: str) -> bool:
        """Delete stored file if it exists. Returns True if deleted, False if not found."""
        ...

    def get_safe_path(self, tenant_id: str, document_id: uuid.UUID) -> str:
        """Resolve a safe relative/canonical path for the document."""
        ...


class LocalStorageService:
    """Local filesystem storage implementation storing files in application-data directory."""

    def __init__(self, base_dir: str | Path = ".local/storage") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _validate_tenant(self, tenant_id: str) -> str:
        if not TENANT_ID_PATTERN.match(tenant_id):
            raise PathTraversalError(f"Invalid tenant identifier: '{tenant_id}'")
        return tenant_id

    def get_safe_path(self, tenant_id: str, document_id: uuid.UUID) -> str:
        sanitized_tenant = self._validate_tenant(tenant_id)
        target_path = (self.base_dir / "tenants" / sanitized_tenant / f"{document_id}.pdf").resolve()
        if not target_path.is_relative_to(self.base_dir):
            raise PathTraversalError("Path traversal attempt detected")
        return str(target_path)

    async def save_stream(
        self,
        tenant_id: str,
        document_id: uuid.UUID,
        stream: AsyncIterator[bytes],
        max_size_bytes: int = 10 * 1024 * 1024,
    ) -> tuple[str, str, int]:
        target_path_str = self.get_safe_path(tenant_id, document_id)
        target_path = Path(target_path_str)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(target_path, "wb") as f:
                async for chunk in stream:
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        raise PDFSizeLimitExceededError(
                            f"File size exceeded {max_size_bytes} bytes limit ({total_bytes} bytes received)"
                        )
                    hasher.update(chunk)
                    f.write(chunk)
        except Exception:
            # Failure cleanup: remove partial/incomplete file on stream error or limit violation
            if target_path.exists():
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            raise

        return str(target_path), hasher.hexdigest(), total_bytes

    async def get_stream(self, file_path: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        target_path = Path(file_path).resolve()
        if not target_path.is_relative_to(self.base_dir):
            raise PathTraversalError("Path traversal attempt detected")
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(target_path, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    async def delete_file(self, file_path: str) -> bool:
        target_path = Path(file_path).resolve()
        if not target_path.is_relative_to(self.base_dir):
            raise PathTraversalError("Path traversal attempt detected")

        if target_path.exists() and target_path.is_file():
            try:
                os.remove(target_path)
                return True
            except OSError:
                return False
        return False
