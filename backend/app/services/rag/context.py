import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from backend.app.services.retrieval.pipeline import RetrievalResult


@dataclass
class AssembledContext:
    context_text: str
    citation_map: Dict[str, RetrievalResult]  # e.g. "DOC-1" -> RetrievalResult
    total_chunks: int
    total_chars: int


def escape_document_content(text: str) -> str:
    """Neutralize potential delimiter injection tags inside untrusted document chunks."""
    if not text:
        return ""
    # Neutralize any attempts to close or manipulate the untrusted_documents quarantine blocks
    sanitized = re.sub(r"</?untrusted_documents>", "[untrusted_documents_escaped]", text, flags=re.IGNORECASE)
    sanitized = re.sub(r"</?document(\s*[^>]*)?>", "[document_tag_escaped]", sanitized, flags=re.IGNORECASE)
    return sanitized


def assemble_rag_context(
    candidates: List[RetrievalResult],
    max_chunks: int = 5,
    max_chars: int = 16000,
) -> AssembledContext:
    """Assemble a bounded, delimited context from authorized retrieval results.

    Enforces:
    1. Server-assigned sequential citation IDs: DOC-1, DOC-2, ...
    2. Character budget cap cleanly at full chunk boundaries.
    3. Neutralization of boundary-escaping markers in chunk texts.
    4. Preservation of document basename and physical page number.
    """
    if not candidates:
        return AssembledContext(context_text="", citation_map={}, total_chunks=0, total_chars=0)

    citation_map: Dict[str, RetrievalResult] = {}
    doc_blocks: List[str] = []
    current_chars = 0

    selected_candidates = candidates[:max_chunks]

    for idx, candidate in enumerate(selected_candidates, start=1):
        citation_id = f"DOC-{idx}"
        sanitized_content = escape_document_content(candidate.content)

        page_str = f" page=\"{candidate.page_number}\"" if candidate.page_number is not None else ""
        # Filename only (never server path)
        block = (
            f'<document id="{citation_id}" filename="{candidate.filename}"{page_str}>\n'
            f'{sanitized_content}\n'
            f'</document>'
        )

        block_len = len(block)
        # Bounded truncation at clean chunk boundary
        if current_chars + block_len > max_chars and doc_blocks:
            break

        doc_blocks.append(block)
        citation_map[citation_id] = candidate
        current_chars += block_len

    if not doc_blocks:
        return AssembledContext(context_text="", citation_map={}, total_chunks=0, total_chars=0)

    context_text = "<untrusted_documents>\n" + "\n".join(doc_blocks) + "\n</untrusted_documents>"
    return AssembledContext(
        context_text=context_text,
        citation_map=citation_map,
        total_chunks=len(doc_blocks),
        total_chars=len(context_text),
    )
