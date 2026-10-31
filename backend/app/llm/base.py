"""LLM gateway interface (ФТ-46). Real providers are added in stage 3."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMRequest:
    system: str
    # Untrusted inputs (student code, explanation, book fragments) go here, never into
    # `system`; providers render them as separate <data> blocks.
    data_blocks: dict[str, str] = field(default_factory=dict)
    response_schema: dict[str, Any] | None = None
    prompt_version: str = "unversioned"
    model: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...
