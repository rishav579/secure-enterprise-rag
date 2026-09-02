import asyncio
import logging
from typing import List

from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.app.services.embedding.base import (
    EmbeddingDimensionError,
    EmbeddingProviderError,
)

logger = logging.getLogger(__name__)


class GeminiEmbeddingService:
    """Production Gemini vector embedding service targeting gemini-embedding-2.
    
    Security & Reliability:
    - Strictly configures 768 output dimensions (output_dimensionality=768).
    - Validates every returned vector has exactly 768 dimensions.
    - Slices inputs into configurable batches (default 32).
    - Bounded exponential backoff retry for transient API / rate limit failures.
    - Never logs document contents, raw PII, embedding vectors, or API keys.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-embedding-2",
        dimension: int = 768,
        batch_size: int = 32,
        max_retries: int = 3,
        base_delay_seconds: float = 1.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._dimension = dimension
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self._client = genai.Client(api_key=api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _embed_batch_with_retry(self, texts_batch: List[str]) -> List[List[float]]:
        """Call Gemini API with bounded exponential backoff on transient errors."""
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Wrap each text in a Content object so the SDK returns one embedding per input text
                contents = [
                    types.Content(parts=[types.Part.from_text(text=t)])
                    for t in texts_batch
                ]
                response = await asyncio.to_thread(
                    self._client.models.embed_content,
                    model=self.model_name,
                    contents=contents,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._dimension,
                    ),
                )

                # Extract and validate vectors
                batch_vectors: List[List[float]] = []
                embeddings = response.embeddings or []

                for idx, emb in enumerate(embeddings):
                    vec = emb.values
                    if len(vec) != self._dimension:
                        raise EmbeddingDimensionError(
                            f"Vector dimension mismatch at index {idx}: expected {self._dimension}, got {len(vec)}"
                        )
                    batch_vectors.append(vec)

                return batch_vectors

            except (APIError, Exception) as exc:
                last_exception = exc
                if isinstance(exc, EmbeddingDimensionError):
                    # Deterministic validation error; do not retry
                    raise

                if attempt < self.max_retries:
                    delay = self.base_delay_seconds * (2 ** (attempt - 1))
                    logger.warning(
                        "Transient embedding API error (attempt %d/%d). Retrying in %.1fs...",
                        attempt,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Embedding API failed after %d attempts.",
                        self.max_retries,
                    )

        raise EmbeddingProviderError(
            f"Embedding generation failed after {self.max_retries} attempts: {type(last_exception).__name__}"
        ) from last_exception

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Batch and embed a list of texts."""
        if not texts:
            return []

        all_vectors: List[List[float]] = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_vectors = await self._embed_batch_with_retry(batch)
            all_vectors.extend(batch_vectors)

        return all_vectors

    async def embed_query(self, query: str) -> List[float]:
        """Embed a single query string."""
        vectors = await self.embed_texts([query])
        if not vectors:
            raise EmbeddingProviderError("Failed to generate embedding for query.")
        return vectors[0]
