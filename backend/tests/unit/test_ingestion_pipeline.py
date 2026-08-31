import uuid
from pathlib import Path
import pytest

from backend.app.services.ingestion.exceptions import InvalidPDFError
from backend.app.services.ingestion.pipeline import DocumentIngestionPipeline
from backend.app.services.storage import LocalStorageService
from backend.tests.unit.test_pdf_parser import create_minimal_text_pdf


async def async_stream(data: bytes, chunk_size: int = 128):
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]


@pytest.mark.asyncio
async def test_pipeline_end_to_end_pii_scrubbing_and_chunking(tmp_path: Path):
    storage = LocalStorageService(base_dir=tmp_path)
    pipeline = DocumentIngestionPipeline(storage_service=storage)

    doc_id = uuid.uuid4()
    tenant = "tenant_alpha"

    # PDF containing PII
    text_with_pii = (
        "Internal confidential memorandum. "
        "The developer secret is sk-abcdef1234567890abcdef123456. "
        "Employee SSN record: 123-45-6789. "
        "Contact email: employee@enterprise.com."
    )
    pdf_bytes = create_minimal_text_pdf([text_with_pii])

    result = await pipeline.ingest_stream(
        tenant_id=tenant,
        document_id=doc_id,
        stream=async_stream(pdf_bytes),
    )

    # 1. File exists in storage
    assert Path(result.file_path).exists()
    assert result.total_pages == 1
    assert result.total_chunks >= 1
    assert result.redactions_count >= 3

    # 2. Strict PII verification: Unmasked PII must NOT exist in any chunk
    for chunk in result.chunks:
        assert "sk-abcdef1234567890abcdef123456" not in chunk.content
        assert "123-45-6789" not in chunk.content
        assert "employee@enterprise.com" not in chunk.content
        # Redaction tokens must be present
        assert "[REDACTED_API_KEY]" in chunk.content or "[REDACTED_SSN]" in chunk.content or "[REDACTED_EMAIL]" in chunk.content


@pytest.mark.asyncio
async def test_pipeline_failure_cleanup_prevents_orphaned_files(tmp_path: Path):
    storage = LocalStorageService(base_dir=tmp_path)
    pipeline = DocumentIngestionPipeline(storage_service=storage)

    doc_id = uuid.uuid4()
    tenant = "tenant_alpha"

    # Corrupt PDF payload that starts with %PDF- but is invalid structure
    corrupt_pdf_bytes = b"%PDF-1.4\nCorrupted byte stream that will fail parsing completely"

    expected_path = Path(storage.get_safe_path(tenant, doc_id))

    with pytest.raises(InvalidPDFError):
        await pipeline.ingest_stream(
            tenant_id=tenant,
            document_id=doc_id,
            stream=async_stream(corrupt_pdf_bytes),
        )

    # Invariant: On failure, the orphaned file must be cleaned up and deleted immediately
    assert not expected_path.exists(), "Orphaned file was not cleaned up after parser failure!"
