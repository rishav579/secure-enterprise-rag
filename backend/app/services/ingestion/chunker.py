from typing import List, NamedTuple


class ChunkPayload(NamedTuple):
    chunk_index: int
    content: str
    page_number: int
    char_start: int
    char_end: int
    char_count: int


class DeterministicChunker:
    """Deterministic page-scoped text chunker.
    
    Key Properties:
    1. Page-bounded: Chunks never cross physical page boundaries.
    2. Strict Offsets: char_start and char_end refer strictly to post-scrubbed page text.
    3. Invariant: page_text[char_start:char_end] == chunk.content.
    4. Deterministic: Identical inputs yield identical chunk sequences and indices.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 40,
        separators: List[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.separators = separators or ["\n\n", "\n", ". ", " "]

    def _find_split_point(self, text: str, start: int, target_end: int) -> int:
        """Find the best natural break point before target_end using hierarchical separators."""
        if target_end >= len(text):
            return len(text)

        window = text[start:target_end]

        for sep in self.separators:
            last_idx = window.rfind(sep)
            if last_idx != -1:
                # Include the separator or sentence dot in the current chunk
                split_at = start + last_idx + len(sep)
                # Ensure we make forward progress and don't produce an empty or tiny chunk
                if split_at > start + self.min_chunk_size:
                    return split_at

        # Fallback: hard cut at target_end
        return target_end

    def chunk_page(
        self,
        page_number: int,
        page_text: str,
        start_chunk_index: int = 0,
    ) -> tuple[List[ChunkPayload], int]:
        """Chunk text for a single page and return (chunks, next_chunk_index)."""
        if not page_text or not page_text.strip():
            return [], start_chunk_index

        chunks: List[ChunkPayload] = []
        current_idx = start_chunk_index
        text_len = len(page_text)

        # If page is smaller than target chunk size, return single chunk
        if text_len <= self.chunk_size:
            chunk = ChunkPayload(
                chunk_index=current_idx,
                content=page_text,
                page_number=page_number,
                char_start=0,
                char_end=text_len,
                char_count=text_len,
            )
            return [chunk], current_idx + 1

        current_pos = 0

        while current_pos < text_len:
            remaining = text_len - current_pos

            # If remaining text is small enough, take it all
            if remaining <= self.chunk_size:
                end_pos = text_len
            else:
                target_end = current_pos + self.chunk_size
                end_pos = self._find_split_point(page_text, current_pos, target_end)

            chunk_str = page_text[current_pos:end_pos]

            if chunk_str:
                chunks.append(
                    ChunkPayload(
                        chunk_index=current_idx,
                        content=chunk_str,
                        page_number=page_number,
                        char_start=current_pos,
                        char_end=end_pos,
                        char_count=len(chunk_str),
                    )
                )
                current_idx += 1

            if end_pos >= text_len:
                break

            # Advance position taking overlap into account
            next_pos = end_pos - self.chunk_overlap
            if next_pos <= current_pos:
                next_pos = end_pos  # Guarantee forward progress

            current_pos = next_pos

        return chunks, current_idx

    def chunk_document(
        self,
        pages: List[tuple[int, str]],  # list of (page_number, scrubbed_page_text)
    ) -> List[ChunkPayload]:
        """Process all pages sequentially with globally continuous chunk indexing."""
        all_chunks: List[ChunkPayload] = []
        current_chunk_idx = 0

        for page_num, text in pages:
            page_chunks, next_idx = self.chunk_page(
                page_number=page_num,
                page_text=text,
                start_chunk_index=current_chunk_idx,
            )
            all_chunks.extend(page_chunks)
            current_chunk_idx = next_idx

        return all_chunks
