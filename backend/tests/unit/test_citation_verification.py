import uuid
from backend.app.services.rag.citations import extract_and_verify_citations
from backend.app.services.retrieval.pipeline import RetrievalResult


def _make_candidate(doc_name: str = "doc.pdf", page: int = 1) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename=doc_name,
        page_number=page,
        char_start=0,
        char_end=50,
        content="Passage text verifying the statement.",
        retrieval_methods=["lexical"],
        rrf_score=0.016,
        lexical_rank=1,
        lexical_score=1.0,
        vector_rank=None,
        vector_distance=None,
        vector_similarity=None,
        reranker_score=None,
    )


def test_extract_valid_citations():
    c1 = _make_candidate("handbook.pdf", page=3)
    c2 = _make_candidate("security.pdf", page=7)
    citation_map = {"DOC-1": c1, "DOC-2": c2}

    answer = "Employees have 20 vacation days [DOC-1]. Security audits run quarterly [DOC-2]."
    eval_res = extract_and_verify_citations(answer, citation_map)

    assert len(eval_res.valid_citations) == 2
    assert eval_res.valid_citations[0].citation_id == "[DOC-1]"
    assert eval_res.valid_citations[0].filename == "handbook.pdf"
    assert eval_res.valid_citations[0].page_number == 3
    assert eval_res.valid_citations[1].citation_id == "[DOC-2]"
    assert eval_res.valid_citations[1].filename == "security.pdf"
    assert eval_res.valid_citations[1].page_number == 7
    assert eval_res.fabricated_ids == []


def test_reject_fabricated_citation_id():
    c1 = _make_candidate("handbook.pdf", page=1)
    citation_map = {"DOC-1": c1}

    # Model cited [DOC-1] and hallucinated [DOC-99]
    answer = "Vacation policy is verified [DOC-1], but bonus is guaranteed [DOC-99]."
    eval_res = extract_and_verify_citations(answer, citation_map)

    assert len(eval_res.valid_citations) == 1
    assert eval_res.valid_citations[0].citation_id == "[DOC-1]"
    assert "DOC-99" in eval_res.fabricated_ids
    # Fabricated tag should be removed from cleaned answer
    assert "[DOC-99]" not in eval_res.cleaned_answer


def test_multiple_citations_on_same_assertion():
    c1 = _make_candidate("a.pdf")
    c2 = _make_candidate("b.pdf")
    citation_map = {"DOC-1": c1, "DOC-2": c2}

    answer = "Both documents agree on this point [DOC-1][DOC-2]."
    eval_res = extract_and_verify_citations(answer, citation_map)

    assert len(eval_res.valid_citations) == 2
    assert eval_res.valid_citations[0].citation_id == "[DOC-1]"
    assert eval_res.valid_citations[1].citation_id == "[DOC-2]"


def test_empty_answer():
    eval_res = extract_and_verify_citations("", {})
    assert eval_res.valid_citations == []
    assert eval_res.referenced_ids == []
    assert eval_res.fabricated_ids == []
