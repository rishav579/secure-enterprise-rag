import re
from typing import NamedTuple, Protocol, Set


class ScrubResult(NamedTuple):
    scrubbed_text: str
    redactions_count: int
    redaction_types: Set[str]


class PIIScrubber(Protocol):
    """Protocol for PII detection and redaction."""

    def scrub(self, text: str) -> ScrubResult: ...


class RegexPIIScrubber:
    """MVP baseline regex scrubber for structured sensitive identifiers.
    
    Runs strictly BEFORE chunking and embedding generation.
    Note: Regex is an MVP baseline and does not provide comprehensive PII detection
    for unstructured named entities (which can be added via Presidio/NER later).
    """

    PATTERNS = [
        (
            "SSN",
            re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b"),
            "[REDACTED_SSN]",
        ),
        (
            "CREDIT_CARD",
            re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
            "[REDACTED_CREDIT_CARD]",
        ),
        (
            "EMAIL",
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            "[REDACTED_EMAIL]",
        ),
        (
            "PHONE",
            re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "[REDACTED_PHONE]",
        ),
        (
            "API_KEY",
            re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,}|gho_[a-zA-Z0-9]{20,}|xox[baprs]-[a-zA-Z0-9]{10,})\b"),
            "[REDACTED_API_KEY]",
        ),
    ]

    def scrub(self, text: str) -> ScrubResult:
        if not text:
            return ScrubResult(scrubbed_text="", redactions_count=0, redaction_types=set())

        scrubbed = text
        total_redactions = 0
        redaction_types: Set[str] = set()

        for label, pattern, replacement in self.PATTERNS:
            matches = list(pattern.finditer(scrubbed))
            if matches:
                total_redactions += len(matches)
                redaction_types.add(label)
                scrubbed = pattern.sub(replacement, scrubbed)

        return ScrubResult(
            scrubbed_text=scrubbed,
            redactions_count=total_redactions,
            redaction_types=redaction_types,
        )
