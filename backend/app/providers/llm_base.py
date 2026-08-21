# LLM provider interface (swappable LLM sources, mirrors NewsProvider).
#
# New concept: the provider returns a structured LLMResult (not a bare str) so
# callers get token usage and the echoed model at call time — no need to
# reconstruct usage separately for cost logging.

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResult:
    """Structured LLM completion result."""

    text: str
    # Total tokens used (prompt + completion). None if the endpoint omits usage.
    tokens_used: int | None
    # Model echoed by the provider; falls back to the configured model.
    model: str


class LLMError(Exception):
    """Raised when an LLM provider fails (network, non-2xx, or malformed body)."""


class LLMProvider(ABC):
    """Contract every LLM source must implement."""

    @abstractmethod
    async def generate(self, system: str, user: str) -> LLMResult:
        """Return a completion for the given system/user messages.

        Args:
            system: system-prompt instructions (the output contract).
            user: the grounded facts to narrate.

        Returns:
            An LLMResult with text, token usage, and the model name.

        Raises:
            LLMError if the provider cannot return a usable completion.
        """
        ...