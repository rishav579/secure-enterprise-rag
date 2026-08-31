import asyncio
import logging
import time
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.app.services.llm.base import (
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class GeminiLLMService:
    """Gemini LLM generation service using official google-genai SDK.

    Follows current Gemini 3.x API conventions:
    - Uses ThinkingConfig(thinking_budget=thinking_budget)
    - Does NOT use temperature=0.0 or deprecated sampling parameters
    - Uses actual provider usage metadata for token accounting
    - Implements bounded exponential backoff for transient rate limits and 503s
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.7-flash",
        thinking_budget: int = 0,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("API key must be provided for GeminiLLMService.")
        self.api_key = api_key
        self.model_name = model_name
        self.thinking_budget = thinking_budget
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = genai.Client(api_key=api_key)

    async def generate_response(
        self,
        system_instruction: str,
        prompt: str,
        max_output_tokens: int = 1024,
    ) -> LLMResponse:
        """Call Gemini generate_content asynchronously with bounded retry/backoff."""
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=self.thinking_budget),
        )

        attempts = 0
        backoff = 1.0

        while True:
            attempts += 1
            start_time = time.perf_counter()
            try:
                # Run synchronous SDK call in thread pool to prevent blocking asyncio loop
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._client.models.generate_content,
                        model=self.model_name,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=self.timeout_seconds,
                )

                latency_ms = (time.perf_counter() - start_time) * 1000.0

                # Extract content
                content = response.text or ""

                # Extract provider usage metadata
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0

                if response.usage_metadata:
                    prompt_tokens = response.usage_metadata.prompt_token_count or 0
                    completion_tokens = response.usage_metadata.candidates_token_count or 0
                    total_tokens = response.usage_metadata.total_token_count or (prompt_tokens + completion_tokens)

                return LLMResponse(
                    content=content,
                    token_usage=TokenUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    ),
                    latency_ms=round(latency_ms, 2),
                    model_name=self.model_name,
                )

            except asyncio.TimeoutError as exc:
                logger.warning("Gemini LLM request timed out (attempt %d/%d)", attempts, self.max_retries + 1)
                if attempts > self.max_retries:
                    raise LLMTimeoutError("LLM generation request timed out after multiple attempts.") from exc
                await asyncio.sleep(backoff)
                backoff *= 2

            except APIError as exc:
                code = getattr(exc, "code", None)
                if code == 429:
                    logger.warning("Gemini rate limit 429 received (attempt %d/%d)", attempts, self.max_retries + 1)
                    if attempts > self.max_retries:
                        raise LLMRateLimitError("Gemini rate limit exceeded.") from exc
                    await asyncio.sleep(backoff)
                    backoff *= 2
                elif code in (500, 502, 503, 504):
                    logger.warning("Gemini transient upstream error %s (attempt %d/%d)", code, attempts, self.max_retries + 1)
                    if attempts > self.max_retries:
                        raise LLMProviderError(f"Gemini upstream server error: {code}") from exc
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise LLMProviderError(f"Gemini API error ({code}): {exc}") from exc

            except Exception as exc:
                logger.error("Unhandled error during Gemini LLM generation: %s", type(exc).__name__)
                raise LLMProviderError(f"Unexpected LLM generation failure: {type(exc).__name__}") from exc
