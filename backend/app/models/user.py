import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class UserRole(str, Enum):
    """Supported roles for Role-Based Access Control (RBAC)."""
    ADMIN = "admin"
    EMPLOYEE = "employee"


class User(Base):
    """User account model establishing authentication and RBAC identity."""
    __tablename__ = "users"

    # UUIDv4 primary key: reduces predictable sequence enumeration and avoids ID leaks.
    # Note: True IDOR protection is enforced via authorization policy layers, not ID obscurity.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, length=32),
        default=UserRole.EMPLOYEE,
        nullable=False,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(64),
        default="default",
        index=True,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )

    def __init__(
        self,
        email: str,
        hashed_password: str,
        role: UserRole = UserRole.EMPLOYEE,
        tenant_id: str = "default",
        is_active: bool = True,
        id: uuid.UUID | None = None,
        **kwargs,
    ):
        super().__init__(
            id=id or uuid.uuid4(),
            email=email,
            hashed_password=hashed_password,
            role=role,
            tenant_id=tenant_id,
            is_active=is_active,
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role} tenant={self.tenant_id}>"
