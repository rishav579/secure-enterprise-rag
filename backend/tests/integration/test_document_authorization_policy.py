import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.authorization import DocumentAccessPolicy
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.permission import DocumentPermission
from backend.app.models.user import User, UserRole


async def seed_test_hierarchy(db: AsyncSession):
    """Seed users, documents, and chunks across tenants and roles."""
    # Tenant Alpha Users
    admin_alpha = User(
        email="admin@alpha.com",
        hashed_password="hash",
        role=UserRole.ADMIN,
        tenant_id="alpha",
    )
    emp1_alpha = User(
        email="emp1@alpha.com",
        hashed_password="hash",
        role=UserRole.EMPLOYEE,
        tenant_id="alpha",
    )
    emp2_alpha = User(
        email="emp2@alpha.com",
        hashed_password="hash",
        role=UserRole.EMPLOYEE,
        tenant_id="alpha",
    )

    # Tenant Beta User
    emp_beta = User(
        email="emp@beta.com",
        hashed_password="hash",
        role=UserRole.EMPLOYEE,
        tenant_id="beta",
    )

    db.add_all([admin_alpha, emp1_alpha, emp2_alpha, emp_beta])
    await db.flush()

    # Documents in Tenant Alpha
    # Doc 1: Employee-visible, owned by emp1_alpha
    doc_emp_visible = Document(
        tenant_id="alpha",
        owner_id=emp1_alpha.id,
        filename="public_guide.pdf",
        file_path=".local/storage/tenants/alpha/doc1.pdf",
        file_hash="hash_doc1",
        file_size_bytes=1000,
        min_role=UserRole.EMPLOYEE,
        status="completed",
    )

    # Doc 2: Admin-only, owned by admin_alpha
    doc_admin_only = Document(
        tenant_id="alpha",
        owner_id=admin_alpha.id,
        filename="confidential_audit.pdf",
        file_path=".local/storage/tenants/alpha/doc2.pdf",
        file_hash="hash_doc2",
        file_size_bytes=2000,
        min_role=UserRole.ADMIN,
        status="completed",
    )

    # Doc 3: Admin-only, owned by emp2_alpha (private draft by employee)
    doc_emp2_private = Document(
        tenant_id="alpha",
        owner_id=emp2_alpha.id,
        filename="emp2_private_draft.pdf",
        file_path=".local/storage/tenants/alpha/doc3.pdf",
        file_hash="hash_doc3",
        file_size_bytes=1500,
        min_role=UserRole.ADMIN,
        status="completed",
    )

    # Doc 4: Document in Tenant Beta
    doc_beta = Document(
        tenant_id="beta",
        owner_id=emp_beta.id,
        filename="beta_manual.pdf",
        file_path=".local/storage/tenants/beta/doc4.pdf",
        file_hash="hash_doc4",
        file_size_bytes=3000,
        min_role=UserRole.EMPLOYEE,
        status="completed",
    )

    db.add_all([doc_emp_visible, doc_admin_only, doc_emp2_private, doc_beta])
    await db.flush()

    # Add Chunks for each document with 768-d mock vectors
    mock_vector = [0.0] * 768
    chunk1 = DocumentChunk(
        document_id=doc_emp_visible.id,
        tenant_id="alpha",
        chunk_index=0,
        content="Alpha employee guide content",
        embedding=mock_vector,
    )
    chunk2 = DocumentChunk(
        document_id=doc_admin_only.id,
        tenant_id="alpha",
        chunk_index=0,
        content="Alpha confidential audit content",
        embedding=mock_vector,
    )
    chunk3 = DocumentChunk(
        document_id=doc_emp2_private.id,
        tenant_id="alpha",
        chunk_index=0,
        content="Alpha employee 2 private content",
        embedding=mock_vector,
    )
    chunk4 = DocumentChunk(
        document_id=doc_beta.id,
        tenant_id="beta",
        chunk_index=0,
        content="Beta manual content",
        embedding=mock_vector,
    )

    db.add_all([chunk1, chunk2, chunk3, chunk4])
    await db.flush()

    return {
        "admin_alpha": admin_alpha,
        "emp1_alpha": emp1_alpha,
        "emp2_alpha": emp2_alpha,
        "emp_beta": emp_beta,
        "doc_emp_visible": doc_emp_visible,
        "doc_admin_only": doc_admin_only,
        "doc_emp2_private": doc_emp2_private,
        "doc_beta": doc_beta,
        "chunk1": chunk1,
        "chunk2": chunk2,
        "chunk3": chunk3,
        "chunk4": chunk4,
    }


@pytest.mark.asyncio
async def test_employee_access_policy_sql_boundary(test_db_session: AsyncSession):
    """Verify an employee querying documents via policy filter sees only authorized docs."""
    data = await seed_test_hierarchy(test_db_session)
    emp1 = data["emp1_alpha"]

    stmt = select(Document).where(DocumentAccessPolicy.build_document_filter(emp1))
    result = await test_db_session.execute(stmt)
    docs = result.scalars().all()
    doc_ids = {d.id for d in docs}

    # emp1 should see:
    # 1. doc_emp_visible (min_role=employee in same tenant, also owned by emp1)
    assert data["doc_emp_visible"].id in doc_ids
    # emp1 must NOT see doc_admin_only (owned by admin)
    assert data["doc_admin_only"].id not in doc_ids
    # emp1 must NOT see doc_emp2_private (admin min_role, owned by emp2)
    assert data["doc_emp2_private"].id not in doc_ids
    # emp1 must NOT see doc_beta (different tenant)
    assert data["doc_beta"].id not in doc_ids


@pytest.mark.asyncio
async def test_owner_access_own_admin_only_document(test_db_session: AsyncSession):
    """Verify an employee who owns an admin-only document can access their own document."""
    data = await seed_test_hierarchy(test_db_session)
    emp2 = data["emp2_alpha"]

    stmt = select(Document).where(DocumentAccessPolicy.build_document_filter(emp2))
    result = await test_db_session.execute(stmt)
    docs = result.scalars().all()
    doc_ids = {d.id for d in docs}

    # emp2 sees doc_emp_visible (employee role)
    assert data["doc_emp_visible"].id in doc_ids
    # emp2 sees doc_emp2_private because emp2 is the OWNER
    assert data["doc_emp2_private"].id in doc_ids
    # emp2 does NOT see admin_alpha's admin-only document
    assert data["doc_admin_only"].id not in doc_ids


@pytest.mark.asyncio
async def test_admin_access_all_tenant_documents(test_db_session: AsyncSession):
    """Verify administrator sees all documents within their tenant, but none from other tenants."""
    data = await seed_test_hierarchy(test_db_session)
    admin = data["admin_alpha"]

    stmt = select(Document).where(DocumentAccessPolicy.build_document_filter(admin))
    result = await test_db_session.execute(stmt)
    docs = result.scalars().all()
    doc_ids = {d.id for d in docs}

    # Admin sees all tenant alpha documents
    assert data["doc_emp_visible"].id in doc_ids
    assert data["doc_admin_only"].id in doc_ids
    assert data["doc_emp2_private"].id in doc_ids
    # Admin does NOT see tenant beta documents
    assert data["doc_beta"].id not in doc_ids


@pytest.mark.asyncio
async def test_explicit_document_permission_lifecycle(test_db_session: AsyncSession):
    """Verify granting explicit user-level permission grants access, and revocation removes it."""
    data = await seed_test_hierarchy(test_db_session)
    emp1 = data["emp1_alpha"]
    admin_doc = data["doc_admin_only"]

    # Before grant: emp1 cannot see admin_doc
    stmt = select(Document).where(DocumentAccessPolicy.build_document_filter(emp1))
    res = await test_db_session.execute(stmt)
    assert admin_doc.id not in {d.id for d in res.scalars().all()}

    # Grant explicit read permission to emp1
    grant = DocumentPermission(
        document_id=admin_doc.id,
        user_id=emp1.id,
        tenant_id="alpha",
        permission="read",
    )
    test_db_session.add(grant)
    await test_db_session.flush()

    # After grant: emp1 CAN see admin_doc via SQL filter
    res_after = await test_db_session.execute(stmt)
    assert admin_doc.id in {d.id for d in res_after.scalars().all()}

    # Revoke grant
    await test_db_session.delete(grant)
    await test_db_session.flush()

    # After revocation: emp1 cannot see admin_doc again
    res_revoked = await test_db_session.execute(stmt)
    assert admin_doc.id not in {d.id for d in res_revoked.scalars().all()}


@pytest.mark.asyncio
async def test_cross_tenant_isolation_at_sql_boundary(test_db_session: AsyncSession):
    """Verify tenant isolation strictly prevents any cross-tenant visibility."""
    data = await seed_test_hierarchy(test_db_session)
    emp_beta = data["emp_beta"]

    stmt = select(Document).where(DocumentAccessPolicy.build_document_filter(emp_beta))
    result = await test_db_session.execute(stmt)
    docs = result.scalars().all()
    doc_ids = {d.id for d in docs}

    assert doc_ids == {data["doc_beta"].id}


@pytest.mark.asyncio
async def test_chunk_filter_excludes_unauthorized_chunks(test_db_session: AsyncSession):
    """Verify build_chunk_filter prevents unauthorized chunks from becoming query candidates."""
    data = await seed_test_hierarchy(test_db_session)
    emp1 = data["emp1_alpha"]

    stmt = select(DocumentChunk).where(DocumentAccessPolicy.build_chunk_filter(emp1))
    result = await test_db_session.execute(stmt)
    chunks = result.scalars().all()
    chunk_ids = {c.id for c in chunks}

    # emp1 sees chunk 1 (from doc_emp_visible)
    assert data["chunk1"].id in chunk_ids
    # emp1 does NOT see chunk 2 (admin only), chunk 3 (emp2 private), or chunk 4 (beta tenant)
    assert data["chunk2"].id not in chunk_ids
    assert data["chunk3"].id not in chunk_ids
    assert data["chunk4"].id not in chunk_ids


@pytest.mark.asyncio
async def test_python_level_policy_and_management_checks(test_db_session: AsyncSession):
    """Verify can_access_document and can_manage_document helper methods."""
    data = await seed_test_hierarchy(test_db_session)
    emp1 = data["emp1_alpha"]
    admin = data["admin_alpha"]
    doc_emp = data["doc_emp_visible"]
    doc_admin = data["doc_admin_only"]
    doc_beta = data["doc_beta"]

    # Access checks
    assert DocumentAccessPolicy.can_access_document(emp1, doc_emp) is True
    assert DocumentAccessPolicy.can_access_document(emp1, doc_admin) is False
    assert DocumentAccessPolicy.can_access_document(admin, doc_admin) is True
    assert DocumentAccessPolicy.can_access_document(emp1, doc_beta) is False  # Cross-tenant

    # Management checks (delete/edit): only owner or admin in same tenant
    assert DocumentAccessPolicy.can_manage_document(emp1, doc_emp) is True    # Owner
    assert DocumentAccessPolicy.can_manage_document(emp1, doc_admin) is False  # Neither owner nor admin
    assert DocumentAccessPolicy.can_manage_document(admin, doc_emp) is True   # Admin in tenant
    assert DocumentAccessPolicy.can_manage_document(admin, doc_beta) is False  # Cross-tenant admin blocked
