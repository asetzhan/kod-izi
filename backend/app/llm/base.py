"""LLM gateway interface (ФТ-46). Q-08/Q-09: production uses a local model (Ollama)."""

import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMRequest:
    system: str
    # Untrusted inputs (student code, explanation, book fragments) go here, never into
    # `system`; they are rendered as separate <data> blocks (spec 14.1).
    data_blocks: dict[str, str] = field(default_factory=dict)
    response_schema: dict[str, Any] | None = None
    prompt_version: str = "unversioned"
    model: str | None = None
    max_output_tokens: int = 2048


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

    def embed(self, texts: list[str]) -> list[list[float]]: ...


DATA_TAG = re.compile(r"</?\s*data", re.IGNORECASE)


def render_data_blocks(blocks: dict[str, str]) -> str:
    """Wrap each input in its own <data> block; a closing tag inside the data cannot end it."""
    parts = []
    for name, content in blocks.items():
        safe = DATA_TAG.sub(lambda m: m.group(0).replace("<", "<\\"), content)
        parts.append(f'<data name="{name}">\n{safe}\n</data>')
    return "\n\n".join(parts)
