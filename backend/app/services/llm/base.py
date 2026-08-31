from dataclasses import dataclass
from typing import NamedTuple, Protocol, runtime_checkable


class TokenUsage(NamedTuple):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    content: str
    token_usage: TokenUsage
    latency_ms: float
    model_name: str


class LLMError(Exception):
    """Base exception for LLM provider errors."""


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""


class LLMRateLimitError(LLMError):
    """Raised when LLM quota or rate limit is exceeded."""


class LLMProviderError(LLMError):
    """Raised when LLM upstream service encounters a permanent or unhandled failure."""


@runtime_checkable
class LLMService(Protocol):
    """Provider-agnostic interface for LLM text generation."""

    async def generate_response(
        self,
        system_instruction: str,
        prompt: str,
        max_output_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate response from system instruction and user prompt."""
        ...
