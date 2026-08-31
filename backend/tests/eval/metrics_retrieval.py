"""Retrieval evaluation metrics: Recall@K, MRR, NDCG@K, and Candidate Overlap."""

import math
from typing import List, Set


def recall_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    """Calculate Recall@K: fraction of relevant items retrieved in top-k."""
    if not relevant_ids:
        # If no items are relevant (e.g. refusal or cross-tenant query), 
        # Recall is 1.0 if none retrieved, else 1.0 if not expecting any.
        return 1.0 if len(retrieved_ids) == 0 else 0.0

    top_k_retrieved = set(retrieved_ids[:k])
    hits = top_k_retrieved.intersection(relevant_ids)
    return len(hits) / len(relevant_ids)


def reciprocal_rank(retrieved_ids: List[str], relevant_ids: Set[str]) -> float:
    """Calculate Reciprocal Rank (RR): 1 / rank of the first relevant item."""
    if not relevant_ids:
        return 1.0 if len(retrieved_ids) == 0 else 0.0

    for rank_idx, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank_idx
    return 0.0


def ndcg_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    """Calculate Normalized Discounted Cumulative Gain at K (NDCG@K) with binary relevance."""
    if not relevant_ids:
        return 1.0 if len(retrieved_ids) == 0 else 0.0

    # Calculate DCG@K
    dcg = 0.0
    for i, chunk_id in enumerate(retrieved_ids[:k], start=1):
        rel = 1.0 if chunk_id in relevant_ids else 0.0
        dcg += rel / math.log2(i + 1)

    # Calculate ideal DCG@K (all relevant items ranked at top)
    idcg = 0.0
    ideal_hits = min(len(relevant_ids), k)
    for i in range(1, ideal_hits + 1):
        idcg += 1.0 / math.log2(i + 1)

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def candidate_overlap_ratio(lexical_ids: List[str], vector_ids: List[str]) -> float:
    """Calculate Jaccard overlap ratio between lexical and vector candidates."""
    s1, s2 = set(lexical_ids), set(vector_ids)
    union = s1.union(s2)
    if not union:
        return 0.0
    return len(s1.intersection(s2)) / len(union)
