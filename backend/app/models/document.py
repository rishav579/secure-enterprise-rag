import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.user import UserRole


class Document(Base):
    """Document entity tracking file metadata, tenant isolation, and access status."""
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(64),
        default="application/pdf",
        nullable=False,
    )

    min_role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, length=32),
        default=UserRole.EMPLOYEE,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    permissions: Mapped[List["DocumentPermission"]] = relationship(
        "DocumentPermission",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_documents_tenant_file_hash", "tenant_id", "file_hash"),
    )

    def __init__(
        self,
        owner_id: uuid.UUID,
        filename: str,
        file_path: str,
        file_hash: str,
        file_size_bytes: int,
        tenant_id: str = "default",
        mime_type: str = "application/pdf",
        min_role: UserRole = UserRole.EMPLOYEE,
        status: str = "pending",
        error_message: Optional[str] = None,
        doc_metadata: Optional[Dict[str, Any]] = None,
        id: Optional[uuid.UUID] = None,
        **kwargs,
    ):
        super().__init__(
            id=id or uuid.uuid4(),
            owner_id=owner_id,
            filename=filename,
            file_path=file_path,
            file_hash=file_hash,
            file_size_bytes=file_size_bytes,
            tenant_id=tenant_id,
            mime_type=mime_type,
            min_role=min_role,
            status=status,
            error_message=error_message,
            doc_metadata=doc_metadata or {},
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename} tenant={self.tenant_id} min_role={self.min_role}>"


class DocumentChunk(Base):
    """Text chunk entity storing sanitized content, TSVector, and 768-d vector embeddings."""
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Denormalized tenant_id: ensures vector retrieval enforces tenant boundaries in a single indexed query
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_tsv: Mapped[Optional[Any]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"),
        nullable=True,
    )

    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768).with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    chunk_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_doc_chunk", "document_id", "chunk_index"),
    )

    def __init__(
        self,
        document_id: uuid.UUID,
        tenant_id: str,
        chunk_index: int,
        content: str,
        content_tsv: Optional[Any] = None,
        embedding: Optional[List[float]] = None,
        chunk_metadata: Optional[Dict[str, Any]] = None,
        id: Optional[uuid.UUID] = None,
        **kwargs,
    ):
        super().__init__(
            id=id or uuid.uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            chunk_index=chunk_index,
            content=content,
            content_tsv=content_tsv,
            embedding=embedding,
            chunk_metadata=chunk_metadata or {},
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} doc={self.document_id} idx={self.chunk_index} tenant={self.tenant_id}>"
