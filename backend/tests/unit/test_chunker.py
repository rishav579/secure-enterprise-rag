from backend.app.services.ingestion.chunker import DeterministicChunker


def test_chunker_single_short_page():
    chunker = DeterministicChunker(chunk_size=500, chunk_overlap=50)
    text = "This is a short single-page document."
    chunks, next_idx = chunker.chunk_page(page_number=1, page_text=text)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == text
    assert chunks[0].page_number == 1
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert next_idx == 1


def test_chunker_page_offset_invariant():
    chunker = DeterministicChunker(chunk_size=200, chunk_overlap=30)
    # Generate long text with paragraphs
    paragraphs = [
        "First paragraph introducing the enterprise security policy in great detail.",
        "Second paragraph discussing access control lists and role-based access control.",
        "Third paragraph describing token authentication and zero-trust boundaries.",
        "Fourth paragraph wrapping up the compliance audit checklist.",
    ]
    page_text = "\n\n".join(paragraphs)

    chunks, _ = chunker.chunk_page(page_number=1, page_text=page_text)
    assert len(chunks) > 1

    # Invariant: page_text[chunk.char_start:chunk.char_end] MUST equal chunk.content
    for chunk in chunks:
        extracted_slice = page_text[chunk.char_start:chunk.char_end]
        assert extracted_slice == chunk.content
        assert chunk.page_number == 1


def test_chunker_page_boundaries_not_crossed():
    chunker = DeterministicChunker(chunk_size=150, chunk_overlap=20)
    page1 = "Page one content with sufficient length to test chunk boundaries accurately."
    page2 = "Page two content that should be isolated from page one completely."

    chunks = chunker.chunk_document([(1, page1), (2, page2)])

    page_1_chunks = [c for c in chunks if c.page_number == 1]
    page_2_chunks = [c for c in chunks if c.page_number == 2]

    assert len(page_1_chunks) >= 1
    assert len(page_2_chunks) >= 1

    # Invariants for page 1 chunks
    for c in page_1_chunks:
        assert page1[c.char_start:c.char_end] == c.content

    # Invariants for page 2 chunks
    for c in page_2_chunks:
        assert page2[c.char_start:c.char_end] == c.content

    # Globally sequential chunk indexing
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunker_overlap_presence():
    chunker = DeterministicChunker(chunk_size=100, chunk_overlap=25)
    text = (
        "Alpha section begins here. "
        "Beta section continues with more details. "
        "Gamma section follows right after. "
        "Delta section concludes the text."
    )
    chunks, _ = chunker.chunk_page(page_number=1, page_text=text)
    assert len(chunks) >= 2

    # Verify overlap exists between chunk 0 and chunk 1
    c0 = chunks[0]
    c1 = chunks[1]
    # c1.char_start should be before c0.char_end
    assert c1.char_start < c0.char_end


def test_chunker_deterministic_runs():
    chunker = DeterministicChunker()
    text = "Deterministic check. " * 50
    chunks1, _ = chunker.chunk_page(1, text)
    chunks2, _ = chunker.chunk_page(1, text)

    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.content == c2.content
        assert c1.char_start == c2.char_start
        assert c1.char_end == c2.char_end
