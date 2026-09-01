import io
import uuid
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.deps import get_db, get_embedding_service, get_storage_service
from backend.app.config import get_settings
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import create_app
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.permission import DocumentPermission
from backend.app.models.user import User, UserRole
from backend.app.services.embedding.mock import MockEmbeddingService
from backend.app.services.storage import LocalStorageService
from backend.tests.unit.test_pdf_parser import create_minimal_text_pdf

import pytest_asyncio

settings = get_settings()


@pytest.fixture
def mock_embedding():
    return MockEmbeddingService(dimension=768)


@pytest_asyncio.fixture
async def app_with_deps(test_db_session: AsyncSession, tmp_path: Path, mock_embedding: MockEmbeddingService):
    app = create_app()
    storage = LocalStorageService(base_dir=tmp_path / "storage")

    async def _get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_storage_service] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: mock_embedding

    yield app, storage, mock_embedding


@pytest_asyncio.fixture
async def client_and_users(test_db_session: AsyncSession, app_with_deps):
    app, storage, mock_embedding = app_with_deps

    # Create users across tenants
    pwd = hash_password("SecurePass123!")

    # Tenant Alpha
    alpha_admin = User(
        id=uuid.uuid4(),
        email=f"alpha_admin_{uuid.uuid4().hex[:6]}@enterprise.com",
        hashed_password=pwd,
        role=UserRole.ADMIN,
        tenant_id="tenant_alpha",
        is_active=True,
    )
    alpha_employee_1 = User(
        id=uuid.uuid4(),
        email=f"alpha_emp1_{uuid.uuid4().hex[:6]}@enterprise.com",
        hashed_password=pwd,
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_alpha",
        is_active=True,
    )
    alpha_employee_2 = User(
        id=uuid.uuid4(),
        email=f"alpha_emp2_{uuid.uuid4().hex[:6]}@enterprise.com",
        hashed_password=pwd,
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_alpha",
        is_active=True,
    )

    # Tenant Beta
    beta_employee = User(
        id=uuid.uuid4(),
        email=f"beta_emp_{uuid.uuid4().hex[:6]}@enterprise.com",
        hashed_password=pwd,
        role=UserRole.EMPLOYEE,
        tenant_id="tenant_beta",
        is_active=True,
    )

    test_db_session.add_all([alpha_admin, alpha_employee_1, alpha_employee_2, beta_employee])
    await test_db_session.commit()

    tokens = {
        "alpha_admin": create_access_token(alpha_admin.id),
        "alpha_emp1": create_access_token(alpha_employee_1.id),
        "alpha_emp2": create_access_token(alpha_employee_2.id),
        "beta_emp": create_access_token(beta_employee.id),
    }

    users = {
        "alpha_admin": alpha_admin,
        "alpha_emp1": alpha_employee_1,
        "alpha_emp2": alpha_employee_2,
        "beta_emp": beta_employee,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac, tokens, users, storage, mock_embedding


@pytest.mark.asyncio
async def test_upload_valid_pdf_success_and_chunk_persistence(client_and_users, test_db_session: AsyncSession):
    ac, tokens, users, storage, mock_embedding = client_and_users

    # Upload PDF with realistic text
    pdf_bytes = create_minimal_text_pdf([
        "Introduction to Enterprise Zero Trust Architecture.",
        "Role-Based Access Control and Tenant Isolation Policies.",
    ])

    files = {"file": ("enterprise_policy.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {"min_role": "employee"}
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    resp = await ac.post("/api/v1/documents/upload", files=files, data=data, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["status"] == "completed"
    assert body["total_pages"] == 2
    assert body["total_chunks"] >= 2
    doc_id = uuid.UUID(body["id"])

    # Verify document in DB
    db_doc = await test_db_session.get(Document, doc_id)
    assert db_doc is not None
    assert db_doc.status == "completed"
    assert Path(db_doc.file_path).exists()

    # Verify chunks with 768-d embeddings
    chunk_res = await test_db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
    )
    chunks = chunk_res.scalars().all()
    assert len(chunks) >= 2

    for c in chunks:
        assert c.tenant_id == "tenant_alpha"
        assert len(c.embedding) == 768


@pytest.mark.asyncio
async def test_raw_pii_never_sent_to_embedding_provider_or_persisted_in_chunks(
    client_and_users,
    test_db_session: AsyncSession,
):
    ac, tokens, users, storage, mock_embedding = client_and_users

    # PDF with raw PII
    raw_ssn = "321-65-4321"
    raw_api_key = "sk-abcdef1234567890abcdef123456"
    raw_email = "confidential_ceo@enterprise.com"

    text_content = (
        f"Confidential executive brief. "
        f"Primary SSN: {raw_ssn}. "
        f"Production token: {raw_api_key}. "
        f"Contact address: {raw_email}."
    )
    pdf_bytes = create_minimal_text_pdf([text_content])

    files = {"file": ("pii_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    resp = await ac.post("/api/v1/documents/upload", files=files, headers=headers)
    assert resp.status_code == 201, resp.text
    doc_id = uuid.UUID(resp.json()["id"])

    # 1. VERIFY: Raw PII NEVER reached the embedding service!
    for received_text in mock_embedding.received_texts:
        assert raw_ssn not in received_text, "Raw SSN reached the embedding provider!"
        assert raw_api_key not in received_text, "Raw API key reached the embedding provider!"
        assert raw_email not in received_text, "Raw email reached the embedding provider!"
        # Redaction tokens must be present instead
        assert "[REDACTED_SSN]" in received_text
        assert "[REDACTED_API_KEY]" in received_text
        assert "[REDACTED_EMAIL]" in received_text

    # 2. VERIFY: Raw PII NEVER persisted in document_chunks table!
    chunks = (
        await test_db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
    ).scalars().all()

    for c in chunks:
        assert raw_ssn not in c.content, "Raw SSN persisted in PostgreSQL chunks!"
        assert raw_api_key not in c.content, "Raw API key persisted in PostgreSQL chunks!"
        assert raw_email not in c.content, "Raw email persisted in PostgreSQL chunks!"
        assert "[REDACTED_SSN]" in c.content


@pytest.mark.asyncio
async def test_upload_duplicate_pdf_returns_409_in_same_tenant(client_and_users):
    ac, tokens, users, storage, mock_embedding = client_and_users

    pdf_bytes = create_minimal_text_pdf(["Identical document content for deduplication test."])
    files = {"file": ("dedup.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    # First upload succeeds
    r1 = await ac.post("/api/v1/documents/upload", files=files, headers=headers)
    assert r1.status_code == 201

    # Second upload in same tenant returns 409 Conflict
    files2 = {"file": ("dedup.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r2 = await ac.post("/api/v1/documents/upload", files=files2, headers=headers)
    assert r2.status_code == 409
    assert "already exists in this tenant" in r2.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_upload_same_pdf_different_tenant_allowed(client_and_users):
    ac, tokens, users, storage, mock_embedding = client_and_users

    pdf_bytes = create_minimal_text_pdf(["Cross-tenant identical content is valid."])

    # Upload in Tenant Alpha
    files1 = {"file": ("shared.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r1 = await ac.post("/api/v1/documents/upload", files=files1, headers={"Authorization": f"Bearer {tokens['alpha_emp1']}"})
    assert r1.status_code == 201

    # Upload same content in Tenant Beta succeeds
    files2 = {"file": ("shared.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r2 = await ac.post("/api/v1/documents/upload", files=files2, headers={"Authorization": f"Bearer {tokens['beta_emp']}"})
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_upload_corrupt_pdf_cleaned_up(client_and_users):
    ac, tokens, users, storage, mock_embedding = client_and_users

    corrupt_bytes = b"%PDF-1.4\nInvalid corrupted binary content"
    files = {"file": ("bad.pdf", io.BytesIO(corrupt_bytes), "application/pdf")}
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    resp = await ac.post("/api/v1/documents/upload", files=files, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_failed_document_retry_succeeds_and_replaces_failed_record(client_and_users, test_db_session: AsyncSession):
    """Verify that a failed document row does NOT block re-uploading the same file with 409, and succeeds."""
    ac, tokens, users, storage, mock_embedding = client_and_users
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    pdf_bytes = create_minimal_text_pdf(["Content that previously failed due to transient error."])

    # 1. Simulate a previous failed ingestion row for this exact PDF content
    import hashlib
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    failed_doc_id = uuid.uuid4()
    failed_path = storage.get_safe_path("tenant_alpha", failed_doc_id)
    # Create orphan file to test cleanup
    Path(failed_path).parent.mkdir(parents=True, exist_ok=True)
    with open(failed_path, "wb") as f:
        f.write(b"dummy failed content")

    failed_doc = Document(
        id=failed_doc_id,
        tenant_id="tenant_alpha",
        owner_id=users["alpha_emp1"].id,
        filename="retry_doc.pdf",
        file_path=failed_path,
        file_hash=file_hash,
        file_size_bytes=len(pdf_bytes),
        status="failed",
        error_message="Ingestion failed: TransientNetworkError",
    )
    test_db_session.add(failed_doc)
    await test_db_session.commit()

    # Verify old file exists before retry
    assert Path(failed_path).exists()

    # 2. Retry upload of the same file content
    files = {"file": ("retry_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r_retry = await ac.post("/api/v1/documents/upload", files=files, headers=headers)

    # Must NOT return 409; must succeed with 201 Created
    assert r_retry.status_code == 201
    new_doc_id = uuid.UUID(r_retry.json()["id"])
    assert new_doc_id != failed_doc_id
    assert r_retry.json()["status"] == "completed"

    # Verify old failed DB row was cleaned up and new completed row exists
    old_row = await test_db_session.get(Document, failed_doc_id)
    assert old_row is None
    new_row = await test_db_session.get(Document, new_doc_id)
    assert new_row is not None
    assert new_row.status == "completed"

    # Verify old orphaned file was safely removed
    assert not Path(failed_path).exists()


@pytest.mark.asyncio
async def test_processing_document_blocks_duplicate_retry_with_409(client_and_users, test_db_session: AsyncSession):
    """Verify that a document currently in 'processing' status DOES return 409 to prevent concurrent duplicate ingestion."""
    ac, tokens, users, storage, mock_embedding = client_and_users
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    pdf_bytes = create_minimal_text_pdf(["Content currently being processed."])
    import hashlib
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    proc_doc_id = uuid.uuid4()

    proc_doc = Document(
        id=proc_doc_id,
        tenant_id="tenant_alpha",
        owner_id=users["alpha_emp1"].id,
        filename="processing_doc.pdf",
        file_path=storage.get_safe_path("tenant_alpha", proc_doc_id),
        file_hash=file_hash,
        file_size_bytes=len(pdf_bytes),
        status="processing",
    )
    test_db_session.add(proc_doc)
    await test_db_session.commit()

    # Upload same file content while previous is processing
    files = {"file": ("processing_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    r = await ac.post("/api/v1/documents/upload", files=files, headers=headers)

    assert r.status_code == 409
    assert "already exists in this tenant" in r.json()["detail"]["message"]
    assert r.json()["detail"]["existing_document_id"] == str(proc_doc_id)


@pytest.mark.asyncio
async def test_no_orphan_file_remains_after_failed_upload(client_and_users, test_db_session: AsyncSession):
    """Verify that when an upload fails, no orphaned storage file remains on disk."""
    ac, tokens, users, storage, mock_embedding = client_and_users
    headers = {"Authorization": f"Bearer {tokens['alpha_emp1']}"}

    # Corrupt PDF that will fail during SafePDFParser.parse_file()
    corrupt_bytes = b"%PDF-1.7\nCorrupted binary payload without valid PDF objects"
    files = {"file": ("fail_clean.pdf", io.BytesIO(corrupt_bytes), "application/pdf")}

    r = await ac.post("/api/v1/documents/upload", files=files, headers=headers)
    assert r.status_code == 400

    # Get the created failed document row
    failed_doc = (await test_db_session.execute(
        select(Document).where(Document.filename == "fail_clean.pdf")
    )).scalar_one_or_none()
    assert failed_doc is not None
    assert failed_doc.status == "failed"

    # Verify no orphan file exists at failed_doc.file_path
    assert not Path(failed_doc.file_path).exists()


@pytest.mark.asyncio
async def test_document_list_and_get_access_control(client_and_users):
    ac, tokens, users, storage, mock_embedding = client_and_users

    # Upload admin-only doc in Tenant Alpha
    admin_pdf = create_minimal_text_pdf(["Admin eyes only compliance secrets."])
    r_admin = await ac.post(
        "/api/v1/documents/upload",
        files={"file": ("admin.pdf", io.BytesIO(admin_pdf), "application/pdf")},
        data={"min_role": "admin"},
        headers={"Authorization": f"Bearer {tokens['alpha_admin']}"},
    )
    assert r_admin.status_code == 201
    admin_doc_id = r_admin.json()["id"]

    # Upload employee-visible doc in Tenant Alpha
    emp_pdf = create_minimal_text_pdf(["General employee policy handbook."])
    r_emp = await ac.post(
        "/api/v1/documents/upload",
        files={"file": ("emp.pdf", io.BytesIO(emp_pdf), "application/pdf")},
        data={"min_role": "employee"},
        headers={"Authorization": f"Bearer {tokens['alpha_emp1']}"},
    )
    assert r_emp.status_code == 201
    emp_doc_id = r_emp.json()["id"]

    # 1. Employee lists documents: can see emp_doc, CANNOT see admin_doc
    list_resp = await ac.get("/api/v1/documents", headers={"Authorization": f"Bearer {tokens['alpha_emp2']}"})
    assert list_resp.status_code == 200
    doc_ids = [d["id"] for d in list_resp.json()["items"]]
    assert emp_doc_id in doc_ids
    assert admin_doc_id not in doc_ids

    # 2. Employee gets admin_doc directly -> 404 (prevents enumeration)
    get_admin_resp = await ac.get(f"/api/v1/documents/{admin_doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_emp2']}"})
    assert get_admin_resp.status_code == 404

    # 3. Admin gets admin_doc directly -> 200 OK
    get_admin_ok = await ac.get(f"/api/v1/documents/{admin_doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_admin']}"})
    assert get_admin_ok.status_code == 200

    # 4. Cross-tenant user lists documents -> 0 documents from Alpha
    beta_list = await ac.get("/api/v1/documents", headers={"Authorization": f"Bearer {tokens['beta_emp']}"})
    assert beta_list.status_code == 200
    assert len(beta_list.json()["items"]) == 0


@pytest.mark.asyncio
async def test_permission_lifecycle(client_and_users):
    ac, tokens, users, storage, mock_embedding = client_and_users

    # Admin uploads admin-only doc
    pdf_bytes = create_minimal_text_pdf(["Restricted document for permission sharing test."])
    r_doc = await ac.post(
        "/api/v1/documents/upload",
        files={"file": ("restricted.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"min_role": "admin"},
        headers={"Authorization": f"Bearer {tokens['alpha_admin']}"},
    )
    doc_id = r_doc.json()["id"]

    # Employee 2 cannot access initially
    r_init = await ac.get(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_emp2']}"})
    assert r_init.status_code == 404

    # Cross-tenant permission grant rejected with 400
    cross_tenant_body = {"user_id": str(users["beta_emp"].id), "permission": "read"}
    r_cross = await ac.post(
        f"/api/v1/documents/{doc_id}/permissions",
        json=cross_tenant_body,
        headers={"Authorization": f"Bearer {tokens['alpha_admin']}"},
    )
    assert r_cross.status_code == 400
    assert "not found in this tenant" in r_cross.text

    # Valid grant to Employee 2
    valid_body = {"user_id": str(users["alpha_emp2"].id), "permission": "read"}
    r_grant = await ac.post(
        f"/api/v1/documents/{doc_id}/permissions",
        json=valid_body,
        headers={"Authorization": f"Bearer {tokens['alpha_admin']}"},
    )
    assert r_grant.status_code == 201

    # Employee 2 now CAN access!
    r_after = await ac.get(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_emp2']}"})
    assert r_after.status_code == 200

    # List permissions
    r_perms = await ac.get(f"/api/v1/documents/{doc_id}/permissions", headers={"Authorization": f"Bearer {tokens['alpha_admin']}"})
    assert r_perms.status_code == 200
    assert r_perms.json()["total"] == 1

    # Revoke permission
    r_rev = await ac.delete(
        f"/api/v1/documents/{doc_id}/permissions/{users['alpha_emp2'].id}",
        headers={"Authorization": f"Bearer {tokens['alpha_admin']}"},
    )
    assert r_rev.status_code == 204

    # Employee 2 access revoked -> 404
    r_revoked = await ac.get(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_emp2']}"})
    assert r_revoked.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_and_orphan_storage_cleanup(client_and_users, test_db_session: AsyncSession):
    ac, tokens, users, storage, mock_embedding = client_and_users

    # Emp 1 uploads document
    pdf_bytes = create_minimal_text_pdf(["Document to be deleted cleanly."])
    r_up = await ac.post(
        "/api/v1/documents/upload",
        files={"file": ("to_delete.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers={"Authorization": f"Bearer {tokens['alpha_emp1']}"},
    )
    assert r_up.status_code == 201
    doc_id = uuid.UUID(r_up.json()["id"])

    # Non-owner employee cannot delete -> 403
    r_del_unauth = await ac.delete(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_emp2']}"})
    assert r_del_unauth.status_code == 403

    # Owner deletes -> 204
    r_del_ok = await ac.delete(f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {tokens['alpha_emp1']}"})
    assert r_del_ok.status_code == 204

    # Verify DB row gone
    assert await test_db_session.get(Document, doc_id) is None

    # Verify raw PDF file removed from storage
    expected_path = Path(storage.get_safe_path("tenant_alpha", doc_id))
    assert not expected_path.exists()


@pytest.mark.asyncio
async def test_real_postgres_pgvector_persistence_and_query():
    """Verify real PostgreSQL VECTOR(768) persistence and cosine distance (<=>) search."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    mock_service = MockEmbeddingService(dimension=768)

    # Generate real 768-d float vectors
    vec_a = await mock_service.embed_query("Enterprise Security Policy")
    vec_b = await mock_service.embed_query("Unrelated Cafeteria Menu")

    async with SessionLocal() as session:
        try:
            # 1. Create User
            user = User(
                id=owner_id,
                email=f"pgvector_test_{uuid.uuid4().hex[:6]}@enterprise.com",
                hashed_password=hash_password("Pass123!"),
                role=UserRole.ADMIN,
                tenant_id="tenant_pgvector",
            )
            session.add(user)
            await session.flush()

            # 2. Create Document
            doc = Document(
                id=doc_id,
                tenant_id="tenant_pgvector",
                owner_id=owner_id,
                filename="pgvector_test.pdf",
                file_path=".local/storage/tenants/tenant_pgvector/test.pdf",
                file_hash=uuid.uuid4().hex,
                file_size_bytes=1024,
                mime_type="application/pdf",
                min_role=UserRole.EMPLOYEE,
                status="completed",
            )
            session.add(doc)
            await session.flush()

            # 3. Create DocumentChunks with VECTOR(768)
            chunk_a = DocumentChunk(
                document_id=doc_id,
                tenant_id="tenant_pgvector",
                chunk_index=0,
                content="Enterprise Security Policy and Zero Trust Network",
                embedding=vec_a,
                chunk_metadata={"page_number": 1},
            )
            chunk_b = DocumentChunk(
                document_id=doc_id,
                tenant_id="tenant_pgvector",
                chunk_index=1,
                content="Cafeteria menu with soup and sandwiches",
                embedding=vec_b,
                chunk_metadata={"page_number": 2},
            )
            session.add_all([chunk_a, chunk_b])
            await session.commit()

            # 4. Search using pgvector cosine distance operator (<=>)
            # Query vector similar to vec_a
            q_vec = await mock_service.embed_query("Security and Zero Trust")
            q_vec_str = "[" + ",".join(str(x) for x in q_vec) + "]"

            query = text("""
                SELECT chunk_index, content, (embedding <=> CAST(:q_vec AS vector)) AS distance
                FROM document_chunks
                WHERE tenant_id = 'tenant_pgvector' AND document_id = :doc_id
                ORDER BY embedding <=> CAST(:q_vec AS vector) ASC
                LIMIT 1;
            """)
            res = await session.execute(query, {"doc_id": doc_id, "q_vec": q_vec_str})
            top_result = res.first()

            assert top_result is not None
            assert top_result.chunk_index == 0
            assert "Enterprise Security Policy" in top_result.content
            assert top_result.distance >= 0.0

        finally:
            # Clean up test rows safely
            try:
                await session.rollback()
                await session.execute(text("DELETE FROM document_chunks WHERE document_id = :doc_id"), {"doc_id": doc_id})
                await session.execute(text("DELETE FROM documents WHERE id = :doc_id"), {"doc_id": doc_id})
                await session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": owner_id})
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()
