import hashlib
import math
from typing import List

from backend.app.services.embedding.base import EmbeddingService


class MockEmbeddingService:
    """Deterministic offline mock embedding service for testing.
    
    Features:
    - Produces unit-normalized 768-dimensional float vectors derived from input string SHA-256.
    - Records all received texts in `received_texts` to allow assertions that raw PII was never passed!
    """

    def __init__(self, dimension: int = 768) -> None:
        self._dimension = dimension
        self.received_texts: List[str] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    def _generate_vector(self, text: str) -> List[float]:
        # Generate deterministic pseudo-vector from text hash
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = []
        for i in range(self._dimension):
            byte_val = h[i % len(h)]
            raw.append(float(byte_val) / 255.0 - 0.5)

        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self.received_texts.extend(texts)
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, query: str) -> List[float]:
        self.received_texts.append(query)
        return self._generate_vector(query)
