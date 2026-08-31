import uuid
from backend.app.services.rag.citations import CitationItem
from backend.app.services.rag.grounding import (
    GroundingStatus,
    evaluate_grounding_deterministically,
)


def _make_item(citation_id: str) -> CitationItem:
    return CitationItem(
        citation_id=citation_id,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="doc.pdf",
        page_number=1,
        snippet="Snippet",
    )


def test_grounding_zero_context_is_refusal():
    res = evaluate_grounding_deterministically(
        answer="I cannot answer this.",
        valid_citations=[],
        fabricated_citation_ids=[],
        context_chunks_count=0,
    )
    assert res.status == GroundingStatus.REFUSAL
    assert res.is_refusal is True


def test_grounding_explicit_refusal_phrase():
    res = evaluate_grounding_deterministically(
        answer="I do not have enough information in the provided documents to answer.",
        valid_citations=[],
        fabricated_citation_ids=[],
        context_chunks_count=3,
    )
    assert res.status == GroundingStatus.REFUSAL
    assert res.is_refusal is True


def test_grounding_fully_grounded():
    item = _make_item("[DOC-1]")
    res = evaluate_grounding_deterministically(
        answer="MFA is mandatory for employees [DOC-1].",
        valid_citations=[item],
        fabricated_citation_ids=[],
        context_chunks_count=2,
    )
    assert res.status == GroundingStatus.FULLY_GROUNDED
    assert res.is_refusal is False


def test_grounding_with_fabricated_citations():
    item = _make_item("[DOC-1]")
    res = evaluate_grounding_deterministically(
        answer="Some statement [DOC-1] and another unverified [DOC-99].",
        valid_citations=[item],
        fabricated_citation_ids=["DOC-99"],
        context_chunks_count=2,
    )
    assert res.status == GroundingStatus.PARTIALLY_GROUNDED
    assert res.is_refusal is False


def test_grounding_no_citations_when_context_supplied():
    res = evaluate_grounding_deterministically(
        answer="The password policy requires 12 characters.",
        valid_citations=[],
        fabricated_citation_ids=[],
        context_chunks_count=2,
    )
    assert res.status == GroundingStatus.UNSUPPORTED_OR_FABRICATED
    assert res.is_refusal is False
