import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from backend.app.services.rag.citations import CitationItem
from backend.app.services.retrieval.pipeline import RetrievalResult


class GroundingStatus(str, Enum):
    FULLY_GROUNDED = "FULLY_GROUNDED"
    PARTIALLY_GROUNDED = "PARTIALLY_GROUNDED"
    REFUSAL = "REFUSAL"
    UNSUPPORTED_OR_FABRICATED = "UNSUPPORTED_OR_FABRICATED"


# Common refusal patterns indicating model explicitly detected insufficient context
REFUSAL_PATTERNS = [
    re.compile(r"i do not have enough information", re.IGNORECASE),
    re.compile(r"i don't have enough information", re.IGNORECASE),
    re.compile(r"not enough information in the provided", re.IGNORECASE),
    re.compile(r"the provided documents do not contain", re.IGNORECASE),
    re.compile(r"none of the provided documents mention", re.IGNORECASE),
    re.compile(r"i cannot answer this question based on the provided", re.IGNORECASE),
    re.compile(r"no information is provided regarding", re.IGNORECASE),
]


@dataclass
class GroundingEvaluation:
    status: GroundingStatus
    is_refusal: bool
    explanation: str


def evaluate_grounding_deterministically(
    answer: str,
    valid_citations: List[CitationItem],
    fabricated_citation_ids: List[str],
    context_chunks_count: int,
) -> GroundingEvaluation:
    """Evaluate answer grounding primarily through deterministic enforcement rules.

    Enforces:
    1. Zero-context -> Immediate REFUSAL.
    2. Explicit insufficient-evidence refusal phrase -> REFUSAL.
    3. Citations with fabricated context IDs -> UNSUPPORTED_OR_FABRICATED.
    4. Answers with 1+ valid citations and 0 fabricated citations -> FULLY_GROUNDED.
    5. Answers with valid citations alongside unverified references -> PARTIALLY_GROUNDED.
    6. Non-refusal answers with zero citations when context was provided -> UNSUPPORTED_OR_FABRICATED.
    """
    if context_chunks_count == 0:
        return GroundingEvaluation(
            status=GroundingStatus.REFUSAL,
            is_refusal=True,
            explanation="No authorized documents matched the query.",
        )

    # Check for explicit refusal phrases
    for pattern in REFUSAL_PATTERNS:
        if pattern.search(answer):
            return GroundingEvaluation(
                status=GroundingStatus.REFUSAL,
                is_refusal=True,
                explanation="Model correctly identified that provided documents do not contain sufficient evidence.",
            )

    # If the model cited fabricated IDs
    if fabricated_citation_ids:
        if valid_citations:
            return GroundingEvaluation(
                status=GroundingStatus.PARTIALLY_GROUNDED,
                is_refusal=False,
                explanation=f"Answer contains valid citations but also referenced {len(fabricated_citation_ids)} non-existent source IDs.",
            )
        return GroundingEvaluation(
            status=GroundingStatus.UNSUPPORTED_OR_FABRICATED,
            is_refusal=False,
            explanation="Answer cited non-existent source documents not present in the authorized context.",
        )

    # If the model provided an answer but cited zero sources
    if not valid_citations:
        return GroundingEvaluation(
            status=GroundingStatus.UNSUPPORTED_OR_FABRICATED,
            is_refusal=False,
            explanation="Answer made factual claims without citing any provided document sources.",
        )

    return GroundingEvaluation(
        status=GroundingStatus.FULLY_GROUNDED,
        is_refusal=False,
        explanation=f"All {len(valid_citations)} citations map directly to verified chunks in the authorized context.",
    )
