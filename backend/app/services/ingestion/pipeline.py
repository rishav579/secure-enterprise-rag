import uuid
from typing import AsyncIterator, List, NamedTuple

from backend.app.services.ingestion.chunker import ChunkPayload, DeterministicChunker
from backend.app.services.ingestion.parser import SafePDFParser
from backend.app.services.ingestion.pii import PIIScrubber, RegexPIIScrubber
from backend.app.services.storage import LocalStorageService, StorageService


class IngestionResult(NamedTuple):
    file_path: str
    file_hash: str
    file_size_bytes: int
    total_pages: int
    total_chunks: int
    chunks: List[ChunkPayload]
    redactions_count: int


class DocumentIngestionPipeline:
    """End-to-end ingestion pipeline orchestrator.
    
    Coordinates:
    1. Streaming upload & SHA-256 calculation via StorageService
    2. Failure cleanup / orphan removal on any downstream error
    3. Safe page-by-page PDF parsing
    4. Pre-chunking PII scrubbing
    5. Deterministic page-scoped chunking
    """

    def __init__(
        self,
        storage_service: StorageService | None = None,
        parser: SafePDFParser | None = None,
        pii_scrubber: PIIScrubber | None = None,
        chunker: DeterministicChunker | None = None,
    ) -> None:
        self.storage = storage_service or LocalStorageService()
        self.parser = parser or SafePDFParser()
        self.scrubber = pii_scrubber or RegexPIIScrubber()
        self.chunker = chunker or DeterministicChunker()

    async def ingest_stream(
        self,
        tenant_id: str,
        document_id: uuid.UUID,
        stream: AsyncIterator[bytes],
        declared_content_type: str | None = "application/pdf",
        max_size_bytes: int = 10 * 1024 * 1024,
    ) -> IngestionResult:
        """Stream PDF to storage, validate, parse, scrub PII, and generate chunks.
        
        Guarantees failure cleanup: if parsing or scrubbing fails, the stored file is deleted immediately.
        """
        # Step 1: Stream bytes directly to storage, computing SHA-256 and byte length
        file_path, file_hash, file_size = await self.storage.save_stream(
            tenant_id=tenant_id,
            document_id=document_id,
            stream=stream,
            max_size_bytes=max_size_bytes,
        )

        try:
            # Step 2: Safe PDF parsing page-by-page
            parse_result = self.parser.parse_file(file_path)

            # Step 3: PII scrubbing BEFORE chunking (per page)
            total_redactions = 0
            scrubbed_pages: List[tuple[int, str]] = []

            for page in parse_result.pages:
                scrub_res = self.scrubber.scrub(page.text)
                total_redactions += scrub_res.redactions_count
                scrubbed_pages.append((page.page_number, scrub_res.scrubbed_text))

            # Step 4: Deterministic chunking on post-scrubbed text
            chunks = self.chunker.chunk_document(scrubbed_pages)

            return IngestionResult(
                file_path=file_path,
                file_hash=file_hash,
                file_size_bytes=file_size,
                total_pages=parse_result.total_pages,
                total_chunks=len(chunks),
                chunks=chunks,
                redactions_count=total_redactions,
            )

        except Exception:
            # Failure cleanup: remove orphaned file from disk
            await self.storage.delete_file(file_path)
            raise
