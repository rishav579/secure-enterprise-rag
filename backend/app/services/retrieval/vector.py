"""Vector (pgvector cosine similarity) search against document_chunks.

Authorization:
  DocumentAccessPolicy.build_chunk_filter(user) is injected directly into the SQL WHERE
  clause. Unauthorized chunks never enter the candidate set.

Exact vs Approximate scan:
  MVP uses exact flat scan (no HNSW index). With a flat scan and a WHERE predicate,
  PostgreSQL evaluates all rows matching the filter and returns the k nearest by
  cosine distance. Security correctness rests on the WHERE authorization predicate,
  not on the choice of exact vs approximate search.

  When an HNSW index is present: pgvector performs approximate filtering — it scans
  the index graph and then applies WHERE predicates. With selective filters (e.g.
  small tenant), this can return fewer than k results because filtered-out candidates
  are not replaced by the index scan. Mitigation strategies at larger scale include
  iterative index scans (increasing ef_search), partial indexes per tenant, or
  partitioned tables. These are out of scope for MVP.

  HNSW should be introduced only after benchmark evidence (recall@k, p50/p95 latency)
  justifies the trade-off for a given tenant data volume.
"""

import uuid
from dataclasses import dataclass
from typing import List

from sqlalchemy import and_, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.authorization import DocumentAccessPolicy
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.user import User


@dataclass
class VectorSearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    tenant_id: str
    chunk_index: int
    content: str
    chunk_metadata: dict
    filename: str
    vector_rank: int          # 1-indexed position in result list
    vector_distance: float    # cosine distance: lower = more similar (range [0, 2])
    vector_similarity: float  # 1.0 - distance (range [-1, 1], [0,1] for normalized embeddings)


async def run_vector_search(
    query_embedding: List[float],
    user: User,
    db: AsyncSession,
    k: int = 20,
    embedding_dim: int = 768,
) -> List[VectorSearchResult]:
    """Execute pgvector cosine distance search and return top-k authorized chunks.

    The authorization predicate is evaluated entirely within the SQL WHERE clause;
    no post-retrieval filtering occurs.

    Uses CAST(:q_vec AS vector) with literal_column and text binding to allow asyncpg
    parameterization while avoiding type processor conflicts with the distance float.

    Args:
        query_embedding: Must have exactly embedding_dim dimensions. Validated here.
        user: Authenticated user; tenant_id and role taken from this object only.
        db: Async SQLAlchemy session.
        k: Maximum candidates to return.
        embedding_dim: Expected vector dimension (must match stored chunk embeddings).
    """
    if len(query_embedding) != embedding_dim:
        raise ValueError(
            f"Query embedding dimension {len(query_embedding)} "
            f"does not match expected {embedding_dim}"
        )

    auth_filter = DocumentAccessPolicy.build_chunk_filter(user)
    q_vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Use literal_column on the table column with .op('<=>')(text('CAST(:q_vec AS vector)'))
    # to avoid SQLAlchemy inheriting Vector(768) type processor on the float result.
    # Parameter :q_vec is bound via asyncpg.
    dist_expr = (
        literal_column("document_chunks.embedding")
        .op("<=>")(text("CAST(:q_vec AS vector)"))
        .label("vec_dist")
    )

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.tenant_id,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            DocumentChunk.chunk_metadata,
            Document.filename,
            dist_expr,
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            and_(
                auth_filter,
                DocumentChunk.embedding.is_not(None),
            )
        )
        .order_by(dist_expr.asc())
        .limit(k)
    )

    # Note: No broad exception swallowing. Legitimate database errors bubble up.
    rows = (await db.execute(stmt, {"q_vec": q_vec_str})).all()

    results: List[VectorSearchResult] = []
    for rank_1indexed, row in enumerate(rows, start=1):
        dist = float(row.vec_dist)
        results.append(
            VectorSearchResult(
                chunk_id=row.id,
                document_id=row.document_id,
                tenant_id=row.tenant_id,
                chunk_index=row.chunk_index,
                content=row.content,
                chunk_metadata=row.chunk_metadata or {},
                filename=row.filename,
                vector_rank=rank_1indexed,
                vector_distance=dist,
                vector_similarity=1.0 - dist,
            )
        )
    return results
