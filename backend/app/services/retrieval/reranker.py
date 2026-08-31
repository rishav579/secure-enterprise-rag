"""Reranking stage: cross-encoder reranking over already-authorized candidates.

FlashRank is a lightweight ONNX-based cross-encoder reranker.
  - No PyTorch or CUDA dependency; runs on CPU.
  - Default model: ms-marco-MiniLM-L-12-v2 (~70MB ONNX).
  - Authorization: only already-authorized FusedCandidates (post-SQL, post-RRF) are
    passed here. The reranker re-scores content only; it has no access to the database
    and cannot introduce unauthorized results.

Graceful degradation:
  If FlashRank is unavailable, model fails to load, or raises at inference time,
  NullReranker returns candidates in their existing RRF order.

Actual latency must be benchmarked locally — no fixed figure is claimed here.
"""

import logging
from typing import List, Protocol, runtime_checkable

from backend.app.services.retrieval.fusion import FusedCandidate

logger = logging.getLogger(__name__)


@runtime_checkable
class RerankerService(Protocol):
    """Protocol for reranking services."""

    def rerank(
        self,
        query: str,
        candidates: List[FusedCandidate],
        top_k: int,
    ) -> List[FusedCandidate]:
        """Return candidates reranked and truncated to top_k.

        Must not add new candidates; must only reorder and slice existing ones.
        Reranker_score should be populated on returned candidates.
        """
        ...


class NullReranker:
    """Passthrough reranker — returns top_k candidates in existing RRF order.

    Used as fallback when FlashRank is unavailable or raises an error.
    """

    def rerank(
        self,
        query: str,
        candidates: List[FusedCandidate],
        top_k: int,
    ) -> List[FusedCandidate]:
        return candidates[:top_k]


class FlashRankReranker:
    """Cross-encoder reranker using the FlashRank library (ONNX runtime).

    Falls back to NullReranker if flashrank is not installed or model load fails.
    Actual p50/p95 reranking latency is recorded in tests/benchmarks.
    """

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2", cache_dir: str | None = None) -> None:
        self._ranker = None
        self._fallback = NullReranker()
        try:
            from flashrank import Ranker  # type: ignore[import]
            kwargs = {"model_name": model_name}
            if cache_dir:
                kwargs["cache_dir"] = cache_dir
            self._ranker = Ranker(**kwargs)
            logger.info("FlashRankReranker loaded model: %s", model_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FlashRank unavailable (%s); reranking disabled, using RRF order.", exc
            )

    def rerank(
        self,
        query: str,
        candidates: List[FusedCandidate],
        top_k: int,
    ) -> List[FusedCandidate]:
        if not candidates:
            return []

        if self._ranker is None:
            return self._fallback.rerank(query, candidates, top_k)

        try:
            from flashrank import RerankRequest  # type: ignore[import]

            passages = [
                {"id": str(c.chunk_id), "text": c.content}
                for c in candidates
            ]
            req = RerankRequest(query=query, passages=passages)
            ranked = self._ranker.rerank(req)

            # Build id → candidate map for fast lookup
            id_map = {str(c.chunk_id): c for c in candidates}

            reranked: List[FusedCandidate] = []
            for item in ranked[:top_k]:
                cid = item.get("id") or item.get("text", "")  # id key varies by flashrank version
                if not cid and "meta" in item:
                    cid = item["meta"].get("id", "")
                # Try to resolve chunk by id; fall back to position-based lookup
                candidate = id_map.get(cid)
                if candidate is None:
                    continue
                candidate.reranker_score = float(item.get("score", 0.0))
                reranked.append(candidate)

            # If reranked is empty (API mismatch), fall back
            if not reranked:
                logger.warning("FlashRank returned no scorable results; falling back to RRF order.")
                return self._fallback.rerank(query, candidates, top_k)

            return reranked

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "FlashRank reranking failed (%s); falling back to RRF order.", exc
            )
            return self._fallback.rerank(query, candidates, top_k)
