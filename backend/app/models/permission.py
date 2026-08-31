import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base

if TYPE_CHECKING:
    from backend.app.models.document import Document
    from backend.app.models.user import User


class DocumentPermission(Base):
    """Explicit document-level access grant for individual users."""
    __tablename__ = "document_permissions"

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

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Denormalized tenant_id: ensures grants match the tenant boundary of both user and document
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    permission: Mapped[str] = mapped_column(
        String(32),
        default="read",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="permissions")
    user: Mapped["User"] = relationship("User", backref="document_permissions")

    __table_args__ = (
        UniqueConstraint("document_id", "user_id", name="uq_document_permissions_doc_user"),
        Index("ix_document_permissions_tenant_user", "tenant_id", "user_id"),
    )

    def __init__(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        tenant_id: str,
        permission: str = "read",
        id: Optional[uuid.UUID] = None,
        **kwargs,
    ):
        super().__init__(
            id=id or uuid.uuid4(),
            document_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            permission=permission,
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"<DocumentPermission id={self.id} doc={self.document_id} user={self.user_id} perm={self.permission}>"
