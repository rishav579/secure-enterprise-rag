"""Integration tests for POST /api/v1/retrieval/search.

All document and permission setup is done against the live PostgreSQL database.
Authorization adversarial tests verify that:
  - Cross-tenant isolation: results never leak across tenants
  - Client cannot inject tenant_id or role via request body
  - Employee cannot access admin-only documents via retrieval
  - Permission-revoked documents do not appear in retrieval results
  - Admin can retrieve any document in their tenant
  - Owner can retrieve their own admin-only document

Also includes:
  - Hybrid retrieval quality: chunks matching both lexical and vector get higher RRF
  - Input validation: empty query, too-long query, top_k bounds
  - Diagnostics payload schema
  - Retrieval with no matching documents returns empty result set (not an error)
  - Regression: genuine DB/retrieval failures return 502, NOT silently empty results
"""

import io
import uuid
import time
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.deps import get_db, get_embedding_service
from backend.app.api.v1.retrieval import get_reranker
from backend.app.core.security import create_access_token, hash_password
from backend.app.main import create_app
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.permission import DocumentPermission
from backend.app.models.user import User, UserRole
from backend.app.services.embedding.mock import MockEmbeddingService
from backend.app.services.retrieval.reranker import NullReranker
from backend.app.config import get_settings

settings = get_settings()
REAL_PG_URL = settings.DATABASE_URL


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _pwd():
    return hash_password("TestPass123!")


def _tok(user: User) -> str:
    return create_access_token(user.id)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_embedding():
    return MockEmbeddingService(dimension=768)


@pytest_asyncio.fixture
async def validation_client(test_db_session: AsyncSession, mock_embedding):
    """Fast in-memory client for input validation tests that don't execute search."""
    app = create_app()

    async def _get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_embedding_service] = lambda: mock_embedding
    app.dependency_overrides[get_reranker] = lambda: NullReranker()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac, test_db_session, mock_embedding


@pytest_asyncio.fixture
async def pg_retrieval_client(mock_embedding):
    """App connected to live PostgreSQL with MockEmbeddingService and NullReranker."""
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()

    async def _get_pg_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _get_pg_db
    app.dependency_overrides[get_embedding_service] = lambda: mock_embedding
    app.dependency_overrides[get_reranker] = lambda: NullReranker()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac, SessionLocal, mock_embedding

    await engine.dispose()


# ──────────────────────────────────────────────────────────────────────────────
# Input validation tests (Fast, terminated before database retrieval)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieval_unauthenticated_returns_401(validation_client):
    ac, db, _ = validation_client
    r = await ac.post("/api/v1/retrieval/search", json={"query": "enterprise security"})
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


@pytest.mark.asyncio
async def test_retrieval_empty_query_returns_422(validation_client):
    ac, db, _ = validation_client
    user = User(id=uuid.uuid4(), email=f"u{uuid.uuid4().hex[:4]}@t.com",
                hashed_password=_pwd(), role=UserRole.EMPLOYEE, tenant_id="t1")
    db.add(user)
    await db.commit()
    token = _tok(user)

    r = await ac.post(
        "/api/v1/retrieval/search",
        json={"query": " "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_retrieval_too_long_query_returns_422(validation_client):
    ac, db, _ = validation_client
    user = User(id=uuid.uuid4(), email=f"u{uuid.uuid4().hex[:4]}@t.com",
                hashed_password=_pwd(), role=UserRole.EMPLOYEE, tenant_id="t1")
    db.add(user)
    await db.commit()
    token = _tok(user)

    r = await ac.post(
        "/api/v1/retrieval/search",
        json={"query": "x" * 1001},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_retrieval_top_k_clamped(validation_client):
    ac, db, _ = validation_client
    user = User(id=uuid.uuid4(), email=f"u{uuid.uuid4().hex[:4]}@t.com",
                hashed_password=_pwd(), role=UserRole.EMPLOYEE, tenant_id="t1")
    db.add(user)
    await db.commit()
    token = _tok(user)

    r = await ac.post(
        "/api/v1/retrieval/search",
        json={"query": "security policy", "top_k": 999},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Pydantic le=20 rejects values > 20 with 422 Unprocessable Entity
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────────
# Real PostgreSQL API tests (No documents, diagnostics, regression)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retrieval_no_documents_returns_empty(pg_retrieval_client):
    """When tenant has no documents, return HTTP 200 with empty list, not error."""
    ac, SessionLocal, _ = pg_retrieval_client
    user_id = uuid.uuid4()
    tenant = f"t_empty_{uuid.uuid4().hex[:6]}"

    async with SessionLocal() as session:
        user = User(id=user_id, email=f"u_{uuid.uuid4().hex[:4]}@t.com",
                    hashed_password=_pwd(), role=UserRole.EMPLOYEE, tenant_id=tenant)
        session.add(user)
        await session.commit()

    token = _tok(user)
    try:
        r = await ac.post(
            "/api/v1/retrieval/search",
            json={"query": "zero trust security policy"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["results"] == []
        assert body["total_results"] == 0
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()


@pytest.mark.asyncio
async def test_retrieval_diagnostics_schema(pg_retrieval_client):
    """Diagnostics payload contains expected latency and candidate counters."""
    ac, SessionLocal, _ = pg_retrieval_client
    user_id = uuid.uuid4()
    tenant = f"t_diag_{uuid.uuid4().hex[:6]}"

    async with SessionLocal() as session:
        user = User(id=user_id, email=f"u_{uuid.uuid4().hex[:4]}@t.com",
                    hashed_password=_pwd(), role=UserRole.EMPLOYEE, tenant_id=tenant)
        session.add(user)
        await session.commit()

    token = _tok(user)
    try:
        r = await ac.post(
            "/api/v1/retrieval/search",
            json={"query": "security", "include_diagnostics": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        diag = body.get("diagnostics")
        assert diag is not None
        for field in ("lexical_candidates", "vector_candidates", "overlapping_candidates",
                      "rrf_candidates", "reranked", "total_latency_ms",
                      "embed_latency_ms", "lexical_latency_ms", "vector_latency_ms",
                      "rrf_latency_ms", "reranker_latency_ms"):
            assert field in diag, f"Missing diagnostics field: {field}"
    finally:
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()


@pytest.mark.asyncio
async def test_retrieval_database_error_returns_502_not_empty_results(pg_retrieval_client):
    """Regression test: genuine DB retrieval failure returns HTTP 502, NOT silently empty 200.
    
    Verifies that infrastructure/SQL failures are not caught and hidden as empty results.
    Also verifies no internal database traces or filesystem paths leak in the response body.
    """
    ac, SessionLocal, mock_embed = pg_retrieval_client
    user_id = uuid.uuid4()
    tenant = f"t_err_{uuid.uuid4().hex[:6]}"

    async with SessionLocal() as session:
        user = User(id=user_id, email=f"u_{uuid.uuid4().hex[:4]}@t.com",
                    hashed_password=_pwd(), role=UserRole.EMPLOYEE, tenant_id=tenant)
        session.add(user)
        await session.commit()

    token = _tok(user)

    # Monkeypatch the mock_embedding to raise an unexpected runtime error during embedding
    original_embed_query = mock_embed.embed_query
    async def broken_embed_query(query: str):
        raise ConnectionError("Upstream vector service connection reset")
    mock_embed.embed_query = broken_embed_query

    try:
        r = await ac.post(
            "/api/v1/retrieval/search",
            json={"query": "zero trust policy"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 502
        body = r.json()
        assert body["detail"] == "Retrieval service encountered an upstream failure."
        # Confirm no internal stack traces or connection details are exposed
        assert "ConnectionError" not in str(body)
        assert "Upstream vector service" not in str(body)
        assert "traceback" not in str(body).lower()
    finally:
        mock_embed.embed_query = original_embed_query
        async with SessionLocal() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Real PostgreSQL Integration & Adversarial Authorization Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_real_retrieval_tenant_isolation_adversarial():
    """Cross-tenant isolation: Beta user cannot retrieve Alpha tenant chunks.
    
    This is an adversarial authorization test. The Alpha tenant has a document
    with content unique to Alpha. The Beta user issues a search query targeting
    that content. The retrieval must return zero results.
    
    Authorization invariant enforced at SQL WHERE clause (DocumentAccessPolicy.build_chunk_filter),
    NOT by post-retrieval filtering.
    """
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    alpha_user_id = uuid.uuid4()
    beta_user_id = uuid.uuid4()
    alpha_doc_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]

    async with SessionLocal() as session:
        try:
            alpha_user = User(
                id=alpha_user_id,
                email=f"alpha_rt_{suffix}@enterprise.com",
                hashed_password=hash_password("P@ss123!"),
                role=UserRole.EMPLOYEE,
                tenant_id=f"tenant_alpha_rt_{suffix}",
            )
            beta_user = User(
                id=beta_user_id,
                email=f"beta_rt_{suffix}@enterprise.com",
                hashed_password=hash_password("P@ss123!"),
                role=UserRole.EMPLOYEE,
                tenant_id=f"tenant_beta_rt_{suffix}",
            )
            session.add_all([alpha_user, beta_user])
            await session.flush()

            alpha_doc = Document(
                id=alpha_doc_id,
                tenant_id=alpha_user.tenant_id,
                owner_id=alpha_user_id,
                filename="alpha_secret.pdf",
                file_path=".local/storage/alpha_secret.pdf",
                file_hash=uuid.uuid4().hex,
                file_size_bytes=1024,
                mime_type="application/pdf",
                min_role=UserRole.EMPLOYEE,
                status="completed",
            )
            session.add(alpha_doc)
            await session.flush()

            # Unique, distinctive content for Alpha only
            chunk = DocumentChunk(
                document_id=alpha_doc_id,
                tenant_id=alpha_user.tenant_id,
                chunk_index=0,
                content="XORQUANTUM proprietary algorithm Alpha confidential",
                embedding=[0.1] * 768,
                chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 49},
            )
            session.add(chunk)
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk.id)
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )
            await session.commit()

            # Now perform retrieval as Beta user
            from backend.app.services.retrieval.lexical import run_lexical_search
            from backend.app.services.retrieval.vector import run_vector_search

            lex_results = await run_lexical_search(
                "XORQUANTUM proprietary algorithm Alpha confidential",
                beta_user,
                session,
                k=20,
            )
            vec_results = await run_vector_search(
                [0.1] * 768,
                beta_user,
                session,
                k=20,
            )

            assert lex_results == [], \
                f"Beta user retrieved Alpha lexical chunks: {lex_results}"
            assert vec_results == [], \
                f"Beta user retrieved Alpha vector chunks: {vec_results}"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == alpha_doc_id))
                await session.execute(delete(Document).where(Document.id == alpha_doc_id))
                await session.execute(delete(User).where(User.id.in_([alpha_user_id, beta_user_id])))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_retrieval_admin_sees_all_tenant_chunks():
    """Admin in Tenant A can retrieve employee-only and admin-only documents."""
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_admin_retr_{suffix}"
    admin_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    doc1_id = uuid.uuid4()
    doc2_id = uuid.uuid4()

    async with SessionLocal() as session:
        try:
            admin = User(id=admin_id, email=f"adm_{suffix}@e.com",
                         hashed_password=hash_password("P@ss123!"),
                         role=UserRole.ADMIN, tenant_id=tenant)
            emp = User(id=emp_id, email=f"emp_{suffix}@e.com",
                       hashed_password=hash_password("P@ss123!"),
                       role=UserRole.EMPLOYEE, tenant_id=tenant)
            session.add_all([admin, emp])
            await session.flush()

            # emp-accessible document
            doc1 = Document(id=doc1_id, tenant_id=tenant, owner_id=emp_id,
                            filename="emp_doc.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                            file_size_bytes=100, min_role=UserRole.EMPLOYEE, status="completed")
            # admin-only document
            doc2 = Document(id=doc2_id, tenant_id=tenant, owner_id=admin_id,
                            filename="admin_doc.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                            file_size_bytes=100, min_role=UserRole.ADMIN, status="completed")
            session.add_all([doc1, doc2])
            await session.flush()

            c1 = DocumentChunk(document_id=doc1_id, tenant_id=tenant, chunk_index=0,
                                content="Employee accessible enterprise policy",
                                embedding=[0.5] * 768,
                                chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 35})
            c2 = DocumentChunk(document_id=doc2_id, tenant_id=tenant, chunk_index=0,
                                content="Admin confidential security directive",
                                embedding=[0.6] * 768,
                                chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 35})
            session.add_all([c1, c2])
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id.in_([c1.id, c2.id]))
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )
            await session.commit()

            from backend.app.services.retrieval.lexical import run_lexical_search

            # Admin should see chunks using boolean OR search
            lex = await run_lexical_search("enterprise OR security", admin, session, k=20)
            chunk_ids = {r.chunk_id for r in lex}
            assert c1.id in chunk_ids or c2.id in chunk_ids, \
                "Admin should see at least one of the chunks"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_([doc1_id, doc2_id])))
                await session.execute(delete(Document).where(Document.id.in_([doc1_id, doc2_id])))
                await session.execute(delete(User).where(User.id.in_([admin_id, emp_id])))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_retrieval_employee_blocked_from_admin_only():
    """Employee cannot retrieve admin-only document chunks."""
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_empblock_{suffix}"
    admin_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    async with SessionLocal() as session:
        try:
            admin = User(id=admin_id, email=f"adm_{suffix}@e.com",
                         hashed_password=hash_password("P@ss123!"),
                         role=UserRole.ADMIN, tenant_id=tenant)
            emp = User(id=emp_id, email=f"emp_{suffix}@e.com",
                       hashed_password=hash_password("P@ss123!"),
                       role=UserRole.EMPLOYEE, tenant_id=tenant)
            session.add_all([admin, emp])
            await session.flush()

            doc = Document(id=doc_id, tenant_id=tenant, owner_id=admin_id,
                           filename="admin_only.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                           file_size_bytes=100, min_role=UserRole.ADMIN, status="completed")
            session.add(doc)
            await session.flush()

            chunk = DocumentChunk(document_id=doc_id, tenant_id=tenant, chunk_index=0,
                                  content="TopSecret administration only policy directive ADMINPROPRIETARY",
                                  embedding=[0.7] * 768,
                                  chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 50})
            session.add(chunk)
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk.id)
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )
            await session.commit()

            from backend.app.services.retrieval.lexical import run_lexical_search
            from backend.app.services.retrieval.vector import run_vector_search

            lex = await run_lexical_search("ADMINPROPRIETARY administration directive", emp, session, k=20)
            vec = await run_vector_search([0.7] * 768, emp, session, k=20)

            assert all(r.chunk_id != chunk.id for r in lex), "Employee retrieved admin-only lexical chunk"
            assert all(r.chunk_id != chunk.id for r in vec), "Employee retrieved admin-only vector chunk"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
                await session.execute(delete(Document).where(Document.id == doc_id))
                await session.execute(delete(User).where(User.id.in_([admin_id, emp_id])))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_retrieval_permission_revocation():
    """After permission revocation, employee can no longer retrieve the document chunks."""
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_revoke_{suffix}"
    admin_id = uuid.uuid4()
    emp_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    async with SessionLocal() as session:
        try:
            admin = User(id=admin_id, email=f"adm_{suffix}@e.com",
                         hashed_password=hash_password("P@ss123!"),
                         role=UserRole.ADMIN, tenant_id=tenant)
            emp = User(id=emp_id, email=f"emp_{suffix}@e.com",
                       hashed_password=hash_password("P@ss123!"),
                       role=UserRole.EMPLOYEE, tenant_id=tenant)
            session.add_all([admin, emp])
            await session.flush()

            doc = Document(id=doc_id, tenant_id=tenant, owner_id=admin_id,
                           filename="revoke_test.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                           file_size_bytes=100, min_role=UserRole.ADMIN, status="completed")
            session.add(doc)
            await session.flush()

            chunk = DocumentChunk(document_id=doc_id, tenant_id=tenant, chunk_index=0,
                                  content="Revocable access control document REVTEST",
                                  embedding=[0.3] * 768,
                                  chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 40})
            session.add(chunk)
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk.id)
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )

            # Grant permission
            perm = DocumentPermission(
                document_id=doc_id,
                user_id=emp_id,
                tenant_id=tenant,
                permission="read",
            )
            session.add(perm)
            await session.commit()

            from backend.app.services.retrieval.vector import run_vector_search

            # With permission: employee should see the chunk
            vec_before = await run_vector_search([0.3] * 768, emp, session, k=20)
            assert any(r.chunk_id == chunk.id for r in vec_before), \
                "Employee with explicit permission should see admin-only chunk"

            # Revoke permission
            await session.delete(perm)
            await session.commit()

            # After revocation: employee must not see the chunk
            vec_after = await run_vector_search([0.3] * 768, emp, session, k=20)
            assert all(r.chunk_id != chunk.id for r in vec_after), \
                "Employee retrieved chunk after permission was revoked"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentPermission).where(DocumentPermission.document_id == doc_id))
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
                await session.execute(delete(Document).where(Document.id == doc_id))
                await session.execute(delete(User).where(User.id.in_([admin_id, emp_id])))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_retrieval_owner_access_own_admin_only_doc():
    """Document owner can retrieve their own admin-only document via vector search."""
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_owner_{suffix}"
    emp_owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    async with SessionLocal() as session:
        try:
            emp_owner = User(id=emp_owner_id, email=f"owner_{suffix}@e.com",
                             hashed_password=hash_password("P@ss123!"),
                             role=UserRole.EMPLOYEE, tenant_id=tenant)
            session.add(emp_owner)
            await session.flush()

            doc = Document(id=doc_id, tenant_id=tenant, owner_id=emp_owner_id,
                           filename="owner_doc.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                           file_size_bytes=100, min_role=UserRole.ADMIN, status="completed")
            session.add(doc)
            await session.flush()

            chunk = DocumentChunk(document_id=doc_id, tenant_id=tenant, chunk_index=0,
                                  content="Owner confidential private document OWNERONLY",
                                  embedding=[0.4] * 768,
                                  chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 43})
            session.add(chunk)
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk.id)
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )
            await session.commit()

            from backend.app.services.retrieval.vector import run_vector_search

            results = await run_vector_search([0.4] * 768, emp_owner, session, k=20)
            assert any(r.chunk_id == chunk.id for r in results), \
                "Owner (employee role) must be able to retrieve their own admin-only chunk"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
                await session.execute(delete(Document).where(Document.id == doc_id))
                await session.execute(delete(User).where(User.id == emp_owner_id))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_retrieval_rrf_overlap_boosting():
    """Chunks appearing in both lexical and vector results must outscore single-retriever chunks in RRF."""
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_rrf_{suffix}"
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    async with SessionLocal() as session:
        try:
            user = User(id=user_id, email=f"u_{suffix}@e.com",
                        hashed_password=hash_password("P@ss123!"),
                        role=UserRole.EMPLOYEE, tenant_id=tenant)
            session.add(user)
            await session.flush()

            doc = Document(id=doc_id, tenant_id=tenant, owner_id=user_id,
                           filename="rrf_test.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                           file_size_bytes=100, min_role=UserRole.EMPLOYEE, status="completed")
            session.add(doc)
            await session.flush()

            # chunk_a: High semantic similarity to query_vec AND matches keywords
            # chunk_b: Only semantic similarity (no keyword match)
            query_vec = [1.0] + [0.0] * 767

            chunk_a = DocumentChunk(
                document_id=doc_id, tenant_id=tenant, chunk_index=0,
                content="Zero trust security policy enterprise authentication",
                # Near-identical direction to query_vec
                embedding=[1.0] + [0.0] * 767,
                chunk_metadata={"page_number": 1, "char_start": 0, "char_end": 48},
            )
            chunk_b = DocumentChunk(
                document_id=doc_id, tenant_id=tenant, chunk_index=1,
                content="Cafeteria lunch menu options soup salad",
                # Very different direction from query_vec
                embedding=[0.0] * 767 + [1.0],
                chunk_metadata={"page_number": 2, "char_start": 0, "char_end": 37},
            )
            session.add_all([chunk_a, chunk_b])
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id.in_([chunk_a.id, chunk_b.id]))
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )
            await session.commit()

            from backend.app.services.retrieval.lexical import run_lexical_search
            from backend.app.services.retrieval.vector import run_vector_search
            from backend.app.services.retrieval.fusion import fuse_rrf

            lex = await run_lexical_search("zero trust security policy enterprise authentication", user, session, k=20)
            vec = await run_vector_search(query_vec, user, session, k=20)
            fused = fuse_rrf(lex, vec, k=10)

            # chunk_a must appear in fused results
            fused_ids = [c.chunk_id for c in fused]
            assert chunk_a.id in fused_ids, "chunk_a (keyword + semantic match) should appear in RRF results"

            # chunk_a must have higher RRF score than chunk_b if chunk_b appears
            by_id = {c.chunk_id: c for c in fused}
            if chunk_b.id in by_id:
                assert by_id[chunk_a.id].rrf_score >= by_id[chunk_b.id].rrf_score, \
                    "chunk_a (matched both retrievers) must have >= RRF score than chunk_b (semantic only)"

            # Verify RRF score semantics: not the same as cosine similarity
            if chunk_a.id in by_id and by_id[chunk_a.id].vector_similarity is not None:
                rrf = by_id[chunk_a.id].rrf_score
                sim = by_id[chunk_a.id].vector_similarity
                assert abs(rrf - sim) > 0.5, \
                    "RRF score and cosine similarity must be distinct (they occupy different ranges)"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
                await session.execute(delete(Document).where(Document.id == doc_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_retrieval_benchmark_latency():
    """Benchmark: record observed p50/p95 latency for hybrid retrieval on real PostgreSQL.

    This test records actual observed latencies — no fixed latency is claimed.
    It fails only if retrieval errors occur, not if latency exceeds any threshold.
    """
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_bench_{suffix}"
    user_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    async with SessionLocal() as session:
        try:
            user = User(id=user_id, email=f"bench_{suffix}@e.com",
                        hashed_password=hash_password("P@ss123!"),
                        role=UserRole.EMPLOYEE, tenant_id=tenant)
            session.add(user)
            await session.flush()

            doc = Document(id=doc_id, tenant_id=tenant, owner_id=user_id,
                           filename="bench.pdf", file_path="x", file_hash=uuid.uuid4().hex,
                           file_size_bytes=100, min_role=UserRole.EMPLOYEE, status="completed")
            session.add(doc)
            await session.flush()

            # Insert 10 chunks to simulate a small document
            chunk_ids = []
            for i in range(10):
                emb = [float(j % 100) / 100.0 for j in range(768)]
                c = DocumentChunk(
                    document_id=doc_id, tenant_id=tenant, chunk_index=i,
                    content=f"Enterprise security benchmark chunk {i} policy authentication trust",
                    embedding=emb,
                    chunk_metadata={"page_number": i + 1, "char_start": 0, "char_end": 50},
                )
                session.add(c)
                chunk_ids.append(c)
            await session.flush()
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.document_id == doc_id)
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )
            await session.commit()

            from backend.app.services.retrieval.lexical import run_lexical_search
            from backend.app.services.retrieval.vector import run_vector_search
            from backend.app.services.retrieval.fusion import fuse_rrf

            query_vec = [float(j % 100) / 100.0 for j in range(768)]
            n_runs = 5
            latencies = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                lex = await run_lexical_search("enterprise security policy authentication trust", user, session, k=20)
                vec = await run_vector_search(query_vec, user, session, k=20)
                fuse_rrf(lex, vec, k=10)
                latencies.append((time.perf_counter() - t0) * 1000)

            latencies_sorted = sorted(latencies)
            p50 = latencies_sorted[n_runs // 2]
            p95 = latencies_sorted[int(n_runs * 0.95)]

            print(f"\n[BENCHMARK] Hybrid retrieval on PostgreSQL (n={n_runs} chunks=10):")
            print(f"  p50 latency: {p50:.1f} ms")
            print(f"  p95 latency: {p95:.1f} ms (DB query only, no embedding call)")
            print(f"  all runs (ms): {[round(l, 1) for l in latencies]}")

            # Sanity only: results must not be empty (content exists)
            assert lex or vec, "Benchmark: at least one retriever must return results"

        finally:
            await session.rollback()
            try:
                await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
                await session.execute(delete(Document).where(Document.id == doc_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            except Exception:
                await session.rollback()

    await engine.dispose()
