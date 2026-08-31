import hashlib
import uuid
import pytest
from pathlib import Path

from backend.app.services.ingestion.exceptions import PathTraversalError, PDFSizeLimitExceededError
from backend.app.services.storage import LocalStorageService


async def async_bytes_generator(data: bytes, chunk_size: int = 16):
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]


@pytest.mark.asyncio
async def test_storage_save_stream_and_get_stream(tmp_path: Path):
    service = LocalStorageService(base_dir=tmp_path)
    doc_id = uuid.uuid4()
    tenant = "tenant_alpha"
    content = b"Enterprise secure document stream test content."

    file_path, file_hash, total_bytes = await service.save_stream(
        tenant_id=tenant,
        document_id=doc_id,
        stream=async_bytes_generator(content),
    )

    assert Path(file_path).exists()
    assert total_bytes == len(content)
    assert file_hash == hashlib.sha256(content).hexdigest()
    assert f"tenant_alpha" in file_path
    assert f"{doc_id}.pdf" in file_path

    # Read back via get_stream
    chunks = []
    async for chunk in service.get_stream(file_path):
        chunks.append(chunk)
    assert b"".join(chunks) == content


@pytest.mark.asyncio
async def test_storage_path_traversal_prevention(tmp_path: Path):
    service = LocalStorageService(base_dir=tmp_path)
    doc_id = uuid.uuid4()

    # Path traversal via tenant_id
    with pytest.raises(PathTraversalError):
        await service.save_stream(
            tenant_id="../malicious",
            document_id=doc_id,
            stream=async_bytes_generator(b"test"),
        )

    with pytest.raises(PathTraversalError):
        await service.save_stream(
            tenant_id="tenant/subfolder",
            document_id=doc_id,
            stream=async_bytes_generator(b"test"),
        )


@pytest.mark.asyncio
async def test_storage_size_limit_exceeded_cleans_up_partial_file(tmp_path: Path):
    service = LocalStorageService(base_dir=tmp_path)
    doc_id = uuid.uuid4()
    content = b"A" * 1000

    # Max size = 500 bytes, content = 1000 bytes
    with pytest.raises(PDFSizeLimitExceededError):
        await service.save_stream(
            tenant_id="tenant_alpha",
            document_id=doc_id,
            stream=async_bytes_generator(content, chunk_size=200),
            max_size_bytes=500,
        )

    # Invariant: Partial file must NOT be left on disk
    expected_path = Path(service.get_safe_path("tenant_alpha", doc_id))
    assert not expected_path.exists()


@pytest.mark.asyncio
async def test_storage_delete_file(tmp_path: Path):
    service = LocalStorageService(base_dir=tmp_path)
    doc_id = uuid.uuid4()

    file_path, _, _ = await service.save_stream(
        tenant_id="tenant_alpha",
        document_id=doc_id,
        stream=async_bytes_generator(b"delete me"),
    )
    assert Path(file_path).exists()

    deleted = await service.delete_file(file_path)
    assert deleted is True
    assert not Path(file_path).exists()

    # Second delete returns False safely
    deleted_again = await service.delete_file(file_path)
    assert deleted_again is False
