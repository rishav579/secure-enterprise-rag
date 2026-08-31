import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.user import UserRole


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    owner_id: uuid.UUID
    filename: str
    file_hash: str
    file_size_bytes: int
    mime_type: str
    min_role: UserRole
    status: str
    error_message: Optional[str] = None
    doc_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUploadResponse(DocumentResponse):
    total_pages: int
    total_chunks: int


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int


class DocumentPermissionCreate(BaseModel):
    user_id: uuid.UUID
    permission: str = Field(default="read", pattern="^(read|write|admin)$")

    model_config = ConfigDict(extra="forbid")


class DocumentPermissionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: str
    permission: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentPermissionListResponse(BaseModel):
    items: List[DocumentPermissionResponse]
    total: int
