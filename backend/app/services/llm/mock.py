from typing import Callable, Optional

from backend.app.services.llm.base import LLMResponse, TokenUsage


class MockLLMService:
    """Deterministic Mock LLM Service for testing without external API calls or billing."""

    def __init__(
        self,
        default_response: str = "This is a grounded answer citing the source [DOC-1].",
        model_name: str = "mock-gemini-3.7-flash",
        prompt_tokens: int = 150,
        completion_tokens: int = 35,
        latency_ms: float = 12.5,
    ) -> None:
        self.default_response = default_response
        self.model_name = model_name
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.latency_ms = latency_ms
        self.recorded_calls = []
        self.custom_handler: Optional[Callable[[str, str], str]] = None

    async def generate_response(
        self,
        system_instruction: str,
        prompt: str,
        max_output_tokens: int = 1024,
    ) -> LLMResponse:
        self.recorded_calls.append({
            "system_instruction": system_instruction,
            "prompt": prompt,
            "max_output_tokens": max_output_tokens,
        })

        if self.custom_handler:
            content = self.custom_handler(system_instruction, prompt)
        else:
            content = self.default_response

        return LLMResponse(
            content=content,
            token_usage=TokenUsage(
                prompt_tokens=self.prompt_tokens,
                completion_tokens=self.completion_tokens,
                total_tokens=self.prompt_tokens + self.completion_tokens,
            ),
            latency_ms=self.latency_ms,
            model_name=self.model_name,
        )
