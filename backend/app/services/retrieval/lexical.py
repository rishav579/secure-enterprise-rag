"""Lexical (full-text) search against document_chunks using PostgreSQL tsvector.

Uses websearch_to_tsquery which safely parses plain user text (including quoted
phrases, OR, and -negation) without raising syntax errors on unbalanced input.
Ranking uses ts_rank_cd (cover density), which weights term proximity in addition
to frequency. This is PostgreSQL native FTS, NOT BM25.

Authorization:
  DocumentAccessPolicy.build_chunk_filter(user) is injected directly into the
  SQL WHERE clause. Unauthorized chunks never enter the candidate set.
"""

import uuid
from dataclasses import dataclass
from typing import List

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.authorization import DocumentAccessPolicy
from backend.app.models.document import Document, DocumentChunk
from backend.app.models.user import User


@dataclass
class LexicalSearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    tenant_id: str
    chunk_index: int
    content: str
    chunk_metadata: dict
    filename: str
    lexical_rank: int        # 1-indexed position in result list
    lexical_score: float     # ts_rank_cd score (higher = more relevant)


async def run_lexical_search(
    query: str,
    user: User,
    db: AsyncSession,
    k: int = 20,
) -> List[LexicalSearchResult]:
    """Execute PostgreSQL full-text search and return top-k authorized chunks.

    The authorization predicate is evaluated entirely within the SQL WHERE clause;
    no post-retrieval filtering occurs.
    """
    if not query or not query.strip():
        return []

    auth_filter = DocumentAccessPolicy.build_chunk_filter(user)

    # websearch_to_tsquery is chosen over to_tsquery because it never raises a
    # syntax error on unbalanced user input. It supports:
    #   quoted phrases ("exact phrase"), OR, and -negation.
    tsq = func.websearch_to_tsquery("english", query)
    rank_expr = func.ts_rank_cd(DocumentChunk.content_tsv, tsq).label("lex_score")

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.tenant_id,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            DocumentChunk.chunk_metadata,
            Document.filename,
            rank_expr,
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            and_(
                DocumentChunk.content_tsv.op("@@")(tsq),
                auth_filter,
                DocumentChunk.content_tsv.is_not(None),
            )
        )
        .order_by(rank_expr.desc())
        .limit(k)
    )

    rows = (await db.execute(stmt)).all()

    results: List[LexicalSearchResult] = []
    for rank_1indexed, row in enumerate(rows, start=1):
        results.append(
            LexicalSearchResult(
                chunk_id=row.id,
                document_id=row.document_id,
                tenant_id=row.tenant_id,
                chunk_index=row.chunk_index,
                content=row.content,
                chunk_metadata=row.chunk_metadata or {},
                filename=row.filename,
                lexical_rank=rank_1indexed,
                lexical_score=float(row.lex_score),
            )
        )
    return results
