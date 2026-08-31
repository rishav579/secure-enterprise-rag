import uuid
import pytest

from backend.app.core.authorization import DocumentAccessPolicy
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.permission import DocumentPermission
from backend.app.models.user import User, UserRole


def test_document_model_defaults():
    owner_id = uuid.uuid4()
    doc = Document(
        owner_id=owner_id,
        filename="compliance_report.pdf",
        file_path=".local/storage/tenants/default/doc1.pdf",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=1024,
        tenant_id="tenant_alpha",
    )
    assert doc.id is not None
    assert doc.tenant_id == "tenant_alpha"
    assert doc.owner_id == owner_id
    assert doc.min_role == UserRole.EMPLOYEE
    assert doc.status == "pending"
    assert doc.mime_type == "application/pdf"
    assert doc.doc_metadata == {}
    assert "compliance_report.pdf" in repr(doc)


def test_document_chunk_defaults():
    doc_id = uuid.uuid4()
    chunk = DocumentChunk(
        document_id=doc_id,
        tenant_id="tenant_alpha",
        chunk_index=0,
        content="This is a test chunk content without PII.",
        chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 41},
    )
    assert chunk.id is not None
    assert chunk.document_id == doc_id
    assert chunk.tenant_id == "tenant_alpha"
    assert chunk.chunk_index == 0
    assert chunk.chunk_metadata["page_number"] == 1
    assert "tenant_alpha" in repr(chunk)


def test_document_permission_defaults():
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    perm = DocumentPermission(
        document_id=doc_id,
        user_id=user_id,
        tenant_id="tenant_alpha",
        permission="read",
    )
    assert perm.id is not None
    assert perm.document_id == doc_id
    assert perm.user_id == user_id
    assert perm.tenant_id == "tenant_alpha"
    assert perm.permission == "read"
    assert "read" in repr(perm)


def test_chunk_tenant_invariant_validation():
    doc = Document(
        owner_id=uuid.uuid4(),
        filename="test.pdf",
        file_path="path/test.pdf",
        file_hash="hash1",
        file_size_bytes=100,
        tenant_id="tenant_alpha",
    )
    # Valid matching tenant
    DocumentAccessPolicy.validate_chunk_tenant_invariant(doc, "tenant_alpha")

    # Mismatched tenant raises ValueError
    with pytest.raises(ValueError, match="Tenant invariant violation"):
        DocumentAccessPolicy.validate_chunk_tenant_invariant(doc, "tenant_beta")


def test_permission_tenant_invariant_validation():
    doc = Document(
        owner_id=uuid.uuid4(),
        filename="test.pdf",
        file_path="path/test.pdf",
        file_hash="hash1",
        file_size_bytes=100,
        tenant_id="tenant_alpha",
    )
    user_alpha = User(
        email="user@alpha.com",
        hashed_password="hash",
        tenant_id="tenant_alpha",
    )
    user_beta = User(
        email="user@beta.com",
        hashed_password="hash",
        tenant_id="tenant_beta",
    )

    # Valid: matching tenant across document, user, and permission
    DocumentAccessPolicy.validate_permission_tenant_invariant(doc, user_alpha, "tenant_alpha")

    # Invariant failure: permission tenant doesn't match document
    with pytest.raises(ValueError, match="Tenant invariant violation"):
        DocumentAccessPolicy.validate_permission_tenant_invariant(doc, user_alpha, "tenant_beta")

    # Invariant failure: user belongs to different tenant than document
    with pytest.raises(ValueError, match="Cross-tenant permission grant forbidden"):
        DocumentAccessPolicy.validate_permission_tenant_invariant(doc, user_beta, "tenant_alpha")
