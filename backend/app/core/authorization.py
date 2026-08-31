import uuid
from typing import Optional, Set

from sqlalchemy import and_, or_, select
from sqlalchemy.sql.elements import BinaryExpression

from backend.app.models.document import Document, DocumentChunk
from backend.app.models.permission import DocumentPermission
from backend.app.models.user import User, UserRole


class DocumentAccessPolicy:
    """Centralized Document Authorization Policy.
    
    Single source of truth for:
    - Document CRUD APIs
    - Ingestion pipeline
    - Retrieval query engine (hybrid & vector retrieval)
    """

    @staticmethod
    def build_document_filter(user: User):
        """Construct SQLAlchemy WHERE predicate for Document queries.
        
        Enforces tenant isolation first, followed by role, ownership, or explicit grant.
        """
        # Explicit permissions granted to the user in their tenant
        user_permission_subquery = (
            select(DocumentPermission.document_id)
            .where(
                and_(
                    DocumentPermission.user_id == user.id,
                    DocumentPermission.tenant_id == user.tenant_id,
                )
            )
            .scalar_subquery()
        )

        access_condition = or_(
            user.role == UserRole.ADMIN,
            Document.owner_id == user.id,
            Document.min_role == UserRole.EMPLOYEE,
            Document.id.in_(user_permission_subquery),
        )

        return and_(
            Document.tenant_id == user.tenant_id,
            access_condition,
        )

    @staticmethod
    def build_chunk_filter(user: User):
        """Construct SQLAlchemy WHERE predicate for DocumentChunk queries.
        
        Applied at the SQL query boundary to ensure unauthorized chunks never become
        retrieval or ranking candidates.
        """
        # Documents accessible via ownership or employee role in this tenant
        doc_accessible_subquery = (
            select(Document.id)
            .where(
                and_(
                    Document.tenant_id == user.tenant_id,
                    or_(
                        Document.owner_id == user.id,
                        Document.min_role == UserRole.EMPLOYEE,
                    ),
                )
            )
            .scalar_subquery()
        )

        # Documents accessible via explicit permission grant in this tenant
        doc_permitted_subquery = (
            select(DocumentPermission.document_id)
            .where(
                and_(
                    DocumentPermission.user_id == user.id,
                    DocumentPermission.tenant_id == user.tenant_id,
                )
            )
            .scalar_subquery()
        )

        access_condition = or_(
            user.role == UserRole.ADMIN,
            DocumentChunk.document_id.in_(doc_accessible_subquery),
            DocumentChunk.document_id.in_(doc_permitted_subquery),
        )

        return and_(
            DocumentChunk.tenant_id == user.tenant_id,
            access_condition,
        )

    @staticmethod
    def can_access_document(
        user: User,
        document: Document,
        granted_doc_ids: Optional[Set[uuid.UUID]] = None,
    ) -> bool:
        """Evaluate single-document access rights in Python.
        
        Tenant isolation is an absolute prerequisite.
        """
        if document.tenant_id != user.tenant_id:
            return False

        if user.role == UserRole.ADMIN:
            return True

        if document.owner_id == user.id:
            return True

        if document.min_role == UserRole.EMPLOYEE:
            return True

        if granted_doc_ids and document.id in granted_doc_ids:
            return True

        return False

    @staticmethod
    def can_manage_document(user: User, document: Document) -> bool:
        """Evaluate whether user can modify, share, or delete the document.
        
        Only the document owner or an administrator within the same tenant can manage.
        """
        if document.tenant_id != user.tenant_id:
            return False

        return user.role == UserRole.ADMIN or document.owner_id == user.id

    @staticmethod
    def validate_chunk_tenant_invariant(document: Document, chunk_tenant_id: str) -> None:
        """Enforce that a chunk's denormalized tenant_id strictly matches the parent document's tenant_id."""
        if chunk_tenant_id != document.tenant_id:
            raise ValueError(
                f"Tenant invariant violation: chunk tenant '{chunk_tenant_id}' "
                f"does not match parent document tenant '{document.tenant_id}'"
            )

    @staticmethod
    def validate_permission_tenant_invariant(
        document: Document,
        granted_user: User,
        permission_tenant_id: str,
    ) -> None:
        """Enforce that a permission grant matches both the document's tenant and the granted user's tenant."""
        if permission_tenant_id != document.tenant_id:
            raise ValueError(
                f"Tenant invariant violation: permission tenant '{permission_tenant_id}' "
                f"does not match document tenant '{document.tenant_id}'"
            )
        if granted_user.tenant_id != document.tenant_id:
            raise ValueError(
                f"Cross-tenant permission grant forbidden: user tenant '{granted_user.tenant_id}' "
                f"does not match document tenant '{document.tenant_id}'"
            )
