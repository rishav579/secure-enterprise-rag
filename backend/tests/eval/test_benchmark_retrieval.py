"""Empirical retrieval benchmark comparing:
1. Lexical search only (PostgreSQL tsvector / websearch_to_tsquery)
2. Vector search only (pgvector cosine distance <=>)
3. Hybrid search (Reciprocal Rank Fusion k=60)
4. Hybrid + FlashRank Reranker

Executes live against PostgreSQL + pgvector and measures actual:
- Recall@3, Recall@5
- MRR
- NDCG@5
- p50 and p95 latencies (ms)
"""

import time
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import get_settings
from backend.app.core.security import hash_password
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.user import User, UserRole
from backend.app.services.embedding.mock import MockEmbeddingService
from backend.app.services.retrieval.lexical import run_lexical_search
from backend.app.services.retrieval.pipeline import RetrievalPipeline
from backend.app.services.retrieval.reranker import FlashRankReranker, NullReranker
from backend.app.services.retrieval.vector import run_vector_search
from backend.tests.eval.dataset import EVAL_CHUNKS, EVAL_QUERIES
from backend.tests.eval.metrics_retrieval import ndcg_at_k, recall_at_k, reciprocal_rank

settings = get_settings()
REAL_PG_URL = settings.DATABASE_URL


@pytest_asyncio.fixture
async def benchmark_db():
    engine = create_async_engine(REAL_PG_URL)
    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    user_alpha = User(
        id=uuid.uuid4(), email=f"user_alpha_{uuid.uuid4().hex[:6]}@t.com",
        hashed_password=hash_password("Pass123!"), role=UserRole.EMPLOYEE, tenant_id="tenant_alpha"
    )
    admin_alpha = User(
        id=uuid.uuid4(), email=f"admin_alpha_{uuid.uuid4().hex[:6]}@t.com",
        hashed_password=hash_password("Pass123!"), role=UserRole.ADMIN, tenant_id="tenant_alpha"
    )

    created_doc_ids = []
    created_chunk_ids = []
    chunk_uuid_map = {}

    async with SessionLocal() as session:
        session.add_all([user_alpha, admin_alpha])
        await session.flush()

        for c in EVAL_CHUNKS:
            doc_uuid = uuid.uuid4()
            created_doc_ids.append(doc_uuid)
            owner_id = admin_alpha.id if c.min_role == "admin" else user_alpha.id
            doc = Document(
                id=doc_uuid, tenant_id=c.tenant_id, owner_id=owner_id,
                filename=c.filename, file_path="path", file_hash=uuid.uuid4().hex,
                file_size_bytes=500, min_role=UserRole(c.min_role), status="completed"
            )
            session.add(doc)
            await session.flush()

            # Deterministic mock embedding based on hash
            mock_emb = [(hash(c.content + str(i)) % 100) / 100.0 for i in range(768)]
            # Normalize
            norm = sum(x * x for x in mock_emb) ** 0.5 or 1.0
            mock_emb = [x / norm for x in mock_emb]

            chunk = DocumentChunk(
                document_id=doc_uuid, tenant_id=c.tenant_id, chunk_index=0,
                content=c.content,
                embedding=mock_emb,
                chunk_metadata={"page_number": c.page_number, "char_start": 0, "char_end": len(c.content)},
            )
            session.add(chunk)
            await session.flush()

            chunk_uuid_map[c.chunk_id] = str(chunk.id)
            created_chunk_ids.append(chunk.id)

            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk.id)
                .values(content_tsv=func.to_tsvector("english", DocumentChunk.content))
            )

        await session.commit()

    yield SessionLocal, user_alpha, admin_alpha, chunk_uuid_map

    async with SessionLocal() as session:
        await session.execute(delete(DocumentChunk).where(DocumentChunk.id.in_(created_chunk_ids)))
        await session.execute(delete(Document).where(Document.id.in_(created_doc_ids)))
        await session.execute(delete(User).where(User.id.in_([user_alpha.id, admin_alpha.id])))
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_retrieval_benchmark_comparative(benchmark_db):
    """Execute comparative benchmark and print actual observed metrics."""
    SessionLocal, user_alpha, admin_alpha, chunk_uuid_map = benchmark_db

    embedding_service = MockEmbeddingService(dimension=768)
    hybrid_pipeline = RetrievalPipeline(embedding_service=embedding_service, reranker=NullReranker(), embedding_dim=768)
    reranked_pipeline = RetrievalPipeline(embedding_service=embedding_service, reranker=FlashRankReranker(), embedding_dim=768)

    strategies = {
        "Lexical Only": {"recalls_3": [], "recalls_5": [], "mrrs": [], "ndcgs": [], "latencies": []},
        "Vector Only": {"recalls_3": [], "recalls_5": [], "mrrs": [], "ndcgs": [], "latencies": []},
        "Hybrid RRF": {"recalls_3": [], "recalls_5": [], "mrrs": [], "ndcgs": [], "latencies": []},
        "Hybrid + FlashRank": {"recalls_3": [], "recalls_5": [], "mrrs": [], "ndcgs": [], "latencies": []},
    }

    # Filter to factual queries for retrieval evaluation
    eval_queries = [q for q in EVAL_QUERIES if len(q.expected_relevant_chunk_ids) > 0]

    async with SessionLocal() as session:
        for q in eval_queries:
            user = admin_alpha if q.user_role == "admin" else user_alpha
            expected_uuids = {chunk_uuid_map[cid] for cid in q.expected_relevant_chunk_ids if cid in chunk_uuid_map}

            # 1. Lexical Only
            t0 = time.perf_counter()
            lex_res = await run_lexical_search(query=q.query, user=user, db=session, k=10)
            lat_lex = (time.perf_counter() - t0) * 1000.0
            lex_ids = [str(r.chunk_id) for r in lex_res]
            strategies["Lexical Only"]["recalls_3"].append(recall_at_k(lex_ids, expected_uuids, 3))
            strategies["Lexical Only"]["recalls_5"].append(recall_at_k(lex_ids, expected_uuids, 5))
            strategies["Lexical Only"]["mrrs"].append(reciprocal_rank(lex_ids, expected_uuids))
            strategies["Lexical Only"]["ndcgs"].append(ndcg_at_k(lex_ids, expected_uuids, 5))
            strategies["Lexical Only"]["latencies"].append(lat_lex)

            # 2. Vector Only
            q_emb = await embedding_service.embed_query(q.query)
            t0 = time.perf_counter()
            vec_res = await run_vector_search(query_embedding=q_emb, user=user, db=session, k=10, embedding_dim=768)
            lat_vec = (time.perf_counter() - t0) * 1000.0
            vec_ids = [str(r.chunk_id) for r in vec_res]
            strategies["Vector Only"]["recalls_3"].append(recall_at_k(vec_ids, expected_uuids, 3))
            strategies["Vector Only"]["recalls_5"].append(recall_at_k(vec_ids, expected_uuids, 5))
            strategies["Vector Only"]["mrrs"].append(reciprocal_rank(vec_ids, expected_uuids))
            strategies["Vector Only"]["ndcgs"].append(ndcg_at_k(vec_ids, expected_uuids, 5))
            strategies["Vector Only"]["latencies"].append(lat_vec)

            # 3. Hybrid RRF
            t0 = time.perf_counter()
            hyb_res, _ = await hybrid_pipeline.search(query=q.query, user=user, db=session, top_k=5)
            lat_hyb = (time.perf_counter() - t0) * 1000.0
            hyb_ids = [str(r.chunk_id) for r in hyb_res]
            strategies["Hybrid RRF"]["recalls_3"].append(recall_at_k(hyb_ids, expected_uuids, 3))
            strategies["Hybrid RRF"]["recalls_5"].append(recall_at_k(hyb_ids, expected_uuids, 5))
            strategies["Hybrid RRF"]["mrrs"].append(reciprocal_rank(hyb_ids, expected_uuids))
            strategies["Hybrid RRF"]["ndcgs"].append(ndcg_at_k(hyb_ids, expected_uuids, 5))
            strategies["Hybrid RRF"]["latencies"].append(lat_hyb)

            # 4. Hybrid + FlashRank
            t0 = time.perf_counter()
            rerank_res, _ = await reranked_pipeline.search(query=q.query, user=user, db=session, top_k=5)
            lat_rerank = (time.perf_counter() - t0) * 1000.0
            rerank_ids = [str(r.chunk_id) for r in rerank_res]
            strategies["Hybrid + FlashRank"]["recalls_3"].append(recall_at_k(rerank_ids, expected_uuids, 3))
            strategies["Hybrid + FlashRank"]["recalls_5"].append(recall_at_k(rerank_ids, expected_uuids, 5))
            strategies["Hybrid + FlashRank"]["mrrs"].append(reciprocal_rank(rerank_ids, expected_uuids))
            strategies["Hybrid + FlashRank"]["ndcgs"].append(ndcg_at_k(rerank_ids, expected_uuids, 5))
            strategies["Hybrid + FlashRank"]["latencies"].append(lat_rerank)

    # Print actual measured results for documentation recording
    print("\n" + "=" * 85)
    print(f"{'Strategy':<22} | {'Recall@3':<8} | {'Recall@5':<8} | {'MRR':<6} | {'NDCG@5':<6} | {'p50 (ms)':<8} | {'p95 (ms)':<8}")
    print("-" * 85)
    for name, s in strategies.items():
        avg_r3 = sum(s["recalls_3"]) / len(s["recalls_3"])
        avg_r5 = sum(s["recalls_5"]) / len(s["recalls_5"])
        avg_mrr = sum(s["mrrs"]) / len(s["mrrs"])
        avg_ndcg = sum(s["ndcgs"]) / len(s["ndcgs"])
        lats = sorted(s["latencies"])
        p50 = lats[len(lats) // 2]
        p95 = lats[int(len(lats) * 0.95)]
        print(f"{name:<22} | {avg_r3:<8.3f} | {avg_r5:<8.3f} | {avg_mrr:<6.3f} | {avg_ndcg:<6.3f} | {p50:<8.2f} | {p95:<8.2f}")
    print("=" * 85 + "\n")

    # Assertions
    # Lexical and Hybrid both achieve strong recall on policy queries
    assert sum(strategies["Hybrid RRF"]["recalls_5"]) / len(strategies["Hybrid RRF"]["recalls_5"]) >= 0.80
    assert sum(strategies["Hybrid + FlashRank"]["recalls_5"]) / len(strategies["Hybrid + FlashRank"]["recalls_5"]) >= 0.80
