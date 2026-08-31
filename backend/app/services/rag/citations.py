import re
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel

from backend.app.services.retrieval.pipeline import RetrievalResult


class CitationItem(BaseModel):
    citation_id: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    snippet: str


@dataclass
class CitationValidationResult:
    valid_citations: List[CitationItem]
    referenced_ids: List[str]
    fabricated_ids: List[str]
    cleaned_answer: str


# Matches citation tags like [DOC-1], [DOC-2], case-insensitive
CITATION_REGEX = re.compile(r"\[(DOC-\d+)\]", re.IGNORECASE)


def extract_and_verify_citations(
    answer: str,
    server_citation_map: Dict[str, RetrievalResult],
    snippet_len: int = 150,
) -> CitationValidationResult:
    """Extract in-text citation tags, resolve against server-owned map, and reject fabrications.

    Invariants:
    1. Server-owned mapping: The model may only cite DOC-N keys that exist in server_citation_map.
    2. Any citation ID not in server_citation_map is classified as fabricated and pruned from valid citations.
    3. The citation item resolves strictly to the server's immutable RetrievalResult metadata.
    """
    if not answer:
        return CitationValidationResult(
            valid_citations=[],
            referenced_ids=[],
            fabricated_ids=[],
            cleaned_answer="",
        )

    # Find all cited IDs preserving order of first appearance
    matches = CITATION_REGEX.findall(answer)
    # Normalize match to uppercase (e.g. doc-1 -> DOC-1)
    normalized_ids = [m.upper() for m in matches]

    seen_ids: Set[str] = set()
    valid_citations: List[CitationItem] = []
    referenced_ids: List[str] = []
    fabricated_ids: List[str] = []

    for cid in normalized_ids:
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        referenced_ids.append(cid)

        if cid in server_citation_map:
            candidate = server_citation_map[cid]
            snippet = candidate.content[:snippet_len].strip()
            if len(candidate.content) > snippet_len:
                snippet += "..."

            valid_citations.append(
                CitationItem(
                    citation_id=f"[{cid}]",
                    chunk_id=candidate.chunk_id,
                    document_id=candidate.document_id,
                    filename=candidate.filename,
                    page_number=candidate.page_number,
                    char_start=candidate.char_start,
                    char_end=candidate.char_end,
                    snippet=snippet,
                )
            )
        else:
            fabricated_ids.append(cid)

    # Optional clean-up: if fabricated citation IDs appear in text, we can strip them or leave them intact
    cleaned_answer = answer
    for fab_id in fabricated_ids:
        # Strip brackets around fabricated citations: e.g. [DOC-99] -> (unverified reference)
        pattern = re.compile(rf"\[{re.escape(fab_id)}\]", re.IGNORECASE)
        cleaned_answer = pattern.sub("", cleaned_answer)

    # Clean double spaces caused by removal
    cleaned_answer = re.sub(r" +", " ", cleaned_answer).strip()

    return CitationValidationResult(
        valid_citations=valid_citations,
        referenced_ids=referenced_ids,
        fabricated_ids=fabricated_ids,
        cleaned_answer=cleaned_answer,
    )
