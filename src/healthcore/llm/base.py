"""Provider-neutral interface, so cloud and local models are interchangeable and tests can use a fake."""
from dataclasses import dataclass
from typing import Protocol


class LLMError(RuntimeError):
    """A model call failed. Messages must never contain document content."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient(Protocol):
    name: str  # "cloud" or "local"; shown in the UI

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResult: ...
