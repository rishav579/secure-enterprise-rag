import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import (
    get_current_user,
    get_db,
    get_embedding_service,
    get_storage_service,
)
from backend.app.core.authorization import DocumentAccessPolicy
from backend.app.core.rate_limit import limiter
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.permission import DocumentPermission
from backend.app.models.user import User, UserRole
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentPermissionCreate,
    DocumentPermissionListResponse,
    DocumentPermissionResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from backend.app.services.embedding import (
    EmbeddingDimensionError,
    EmbeddingError,
    EmbeddingProviderError,
    EmbeddingService,
)
from backend.app.services.ingestion.chunker import DeterministicChunker
from backend.app.services.ingestion.exceptions import (
    EmptyPDFError,
    EncryptedPDFError,
    InvalidPDFError,
    PathTraversalError,
    PDFPageLimitExceededError,
    PDFSizeLimitExceededError,
)
from backend.app.services.ingestion.parser import SafePDFParser
from backend.app.services.ingestion.pii import RegexPIIScrubber
from backend.app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


async def _async_upload_file_chunks(file: UploadFile, chunk_size: int = 65536):
    """Yield file chunks from an UploadFile asynchronously."""
    while chunk := await file.read(chunk_size):
        yield chunk


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    min_role: UserRole = Form(UserRole.EMPLOYEE),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
):
    """Upload, parse, scrub PII, chunk, embed, and store a PDF document."""
    # 1. MIME Validation pre-check
    if file.content_type and file.content_type.lower() != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'application/pdf' files are accepted.",
        )

    doc_id = uuid.uuid4()
    tenant_id = current_user.tenant_id
    filename = file.filename or f"{doc_id}.pdf"

    # 2. Stream to storage while computing SHA-256 and byte length
    try:
        file_path, file_hash, file_size = await storage.save_stream(
            tenant_id=tenant_id,
            document_id=doc_id,
            stream=_async_upload_file_chunks(file),
        )
    except PDFSizeLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except PathTraversalError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Storage streaming error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stream file to storage.",
        )

    # 3. Deduplication check within tenant
    dup_query = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.file_hash == file_hash,
    )
    dup_result = await db.execute(dup_query)
    existing_doc = dup_result.scalar_one_or_none()

    if existing_doc:
        if existing_doc.status != "failed":
            # Active document (completed or processing) blocks duplicate upload
            await storage.delete_file(file_path)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "A document with identical content already exists in this tenant.",
                    "existing_document_id": str(existing_doc.id),
                },
            )
        else:
            # Previous attempt failed: clean up any orphaned file and remove failed DB row to allow clean retry
            if existing_doc.file_path and existing_doc.file_path != file_path:
                await storage.delete_file(existing_doc.file_path)
            await db.delete(existing_doc)
            await db.flush()

    # 4. Short DB Transaction 1: Create Document row in 'processing' state
    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        owner_id=current_user.id,
        filename=filename,
        file_path=file_path,
        file_hash=file_hash,
        file_size_bytes=file_size,
        mime_type="application/pdf",
        min_role=min_role,
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # 5. Process document outside of any open database transaction
    parser = SafePDFParser()
    scrubber = RegexPIIScrubber()
    chunker = DeterministicChunker()

    try:
        # A. Safe parsing page-by-page
        parse_result = parser.parse_file(file_path)

        # B. Pre-chunking PII scrubbing
        scrubbed_pages = []
        for page in parse_result.pages:
            scrub_res = scrubber.scrub(page.text)
            scrubbed_pages.append((page.page_number, scrub_res.scrubbed_text))

        # C. Deterministic chunking
        chunks = chunker.chunk_document(scrubbed_pages)
        if not chunks:
            raise EmptyPDFError("Document produced no usable text chunks.")

        # D. External Embedding Generation (NO open DB transaction!)
        chunk_texts = [c.content for c in chunks]
        embeddings = await embedding_service.embed_texts(chunk_texts)

        # E. Short DB Transaction 2: Bulk insert chunks & finalize document
        from sqlalchemy import func as sqlfunc
        is_postgresql = db.get_bind().dialect.name == "postgresql"

        for i, chunk_data in enumerate(chunks):
            chunk_rec = DocumentChunk(
                document_id=doc_id,
                tenant_id=tenant_id,
                chunk_index=chunk_data.chunk_index,
                content=chunk_data.content,
                embedding=embeddings[i],
                # Populate content_tsv for PostgreSQL lexical (FTS) retrieval
                content_tsv=sqlfunc.to_tsvector("english", chunk_data.content) if is_postgresql else None,
                chunk_metadata={
                    "page_number": chunk_data.page_number,
                    "char_start": chunk_data.char_start,
                    "char_end": chunk_data.char_end,
                    "char_count": chunk_data.char_count,
                },
            )
            # Validate tenant invariant before insert
            DocumentAccessPolicy.validate_chunk_tenant_invariant(doc, chunk_rec)
            db.add(chunk_rec)

        doc.status = "completed"
        doc.error_message = None
        await db.commit()
        await db.refresh(doc)

        return DocumentUploadResponse(
            id=doc.id,
            tenant_id=doc.tenant_id,
            owner_id=doc.owner_id,
            filename=doc.filename,
            file_hash=doc.file_hash,
            file_size_bytes=doc.file_size_bytes,
            mime_type=doc.mime_type,
            min_role=doc.min_role,
            status=doc.status,
            error_message=doc.error_message,
            doc_metadata=doc.doc_metadata,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            total_pages=parse_result.total_pages,
            total_chunks=len(chunks),
        )

    except Exception as exc:
        # Failure cleanup: remove orphaned stored file and record failure
        await storage.delete_file(file_path)

        # Mark document failed in database
        clean_error = f"Ingestion failed: {type(exc).__name__}"
        doc.status = "failed"
        doc.error_message = clean_error
        try:
            await db.commit()
        except Exception:
            await db.rollback()

        # Map to appropriate HTTP status codes
        if isinstance(exc, (InvalidPDFError, EncryptedPDFError, EmptyPDFError)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        elif isinstance(exc, PDFPageLimitExceededError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        elif isinstance(exc, EmbeddingDimensionError):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            )
        elif isinstance(exc, EmbeddingProviderError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Embedding service provider unavailable or failed.",
            )
        else:
            logger.error("Unhandled error during document ingestion: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal error occurred during document processing.",
            )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents visible to the authenticated user within their tenant."""
    policy_filter = DocumentAccessPolicy.build_document_filter(current_user)

    # Count total
    count_query = select(func.count(Document.id)).where(policy_filter)
    total_res = await db.execute(count_query)
    total = total_res.scalar_one()

    # Query items
    query = (
        select(Document)
        .where(policy_filter)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    res = await db.execute(query)
    documents = res.scalars().all()

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve document metadata by ID if authorized."""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # Check explicit permission
    perm_query = select(DocumentPermission.id).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.user_id == current_user.id,
        DocumentPermission.tenant_id == current_user.tenant_id,
    )
    perm_result = await db.execute(perm_query)
    has_perm = perm_result.scalar_one_or_none() is not None

    if not DocumentAccessPolicy.can_access_document(current_user, doc, has_perm):
        # 404 to avoid enumeration of restricted documents
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    """Delete a document, its raw PDF file, chunks, and permissions."""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    if not DocumentAccessPolicy.can_manage_document(current_user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the document owner or tenant administrator can delete this document.",
        )

    # Delete file from storage
    if doc.file_path:
        await storage.delete_file(doc.file_path)

    # Delete from database (cascades chunks and permissions)
    await db.delete(doc)
    await db.commit()


# --- Permission Management Endpoints ---


@router.post(
    "/{document_id}/permissions",
    response_model=DocumentPermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_document_permission(
    document_id: uuid.UUID,
    body: DocumentPermissionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant document read access to another user within the same tenant."""
    # 1. Fetch document and verify manage access
    doc_res = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_res.scalar_one_or_none()

    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not DocumentAccessPolicy.can_manage_document(current_user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the document owner or tenant administrator can manage permissions.",
        )

    # 2. Prevent self-grant
    if body.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot grant permission to yourself.",
        )

    # 3. Validate target user exists and belongs to the SAME tenant
    target_user_res = await db.execute(select(User).where(User.id == body.user_id))
    target_user = target_user_res.scalar_one_or_none()

    if not target_user or target_user.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target user not found in this tenant.",
        )

    # 4. Check for duplicate grant
    existing_res = await db.execute(
        select(DocumentPermission.id).where(
            DocumentPermission.document_id == document_id,
            DocumentPermission.user_id == body.user_id,
        )
    )
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permission grant for this user already exists.",
        )

    # 5. Insert permission
    perm = DocumentPermission(
        document_id=document_id,
        user_id=body.user_id,
        tenant_id=current_user.tenant_id,
        permission=body.permission,
    )
    DocumentAccessPolicy.validate_permission_tenant_invariant(doc, target_user, perm)
    db.add(perm)
    await db.commit()
    await db.refresh(perm)

    return DocumentPermissionResponse.model_validate(perm)


@router.get(
    "/{document_id}/permissions",
    response_model=DocumentPermissionListResponse,
)
async def list_document_permissions(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all explicit permission grants for a document."""
    doc_res = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_res.scalar_one_or_none()

    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not DocumentAccessPolicy.can_manage_document(current_user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the document owner or tenant administrator can view permissions.",
        )

    query = select(DocumentPermission).where(DocumentPermission.document_id == document_id)
    res = await db.execute(query)
    perms = res.scalars().all()

    return DocumentPermissionListResponse(
        items=[DocumentPermissionResponse.model_validate(p) for p in perms],
        total=len(perms),
    )


@router.delete(
    "/{document_id}/permissions/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_document_permission(
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a user's explicit permission grant for a document."""
    doc_res = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_res.scalar_one_or_none()

    if not doc or doc.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if not DocumentAccessPolicy.can_manage_document(current_user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the document owner or tenant administrator can revoke permissions.",
        )

    perm_res = await db.execute(
        select(DocumentPermission).where(
            DocumentPermission.document_id == document_id,
            DocumentPermission.user_id == user_id,
        )
    )
    perm = perm_res.scalar_one_or_none()
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission grant not found.",
        )

    await db.delete(perm)
    await db.commit()
