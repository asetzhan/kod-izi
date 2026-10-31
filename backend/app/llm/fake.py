"""Deterministic provider for tests and development: no network access (ФТ-46)."""

import hashlib
import json
from typing import Any

from app.llm.base import LLMRequest, LLMResponse


def _sample(schema: dict[str, Any]) -> Any:
    """Smallest value that satisfies a simple JSON schema."""
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {name: _sample(sub) for name, sub in schema.get("properties", {}).items()}
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    return "fake"


class FakeLLMProvider:
    name = "fake"

    def complete(self, request: LLMRequest) -> LLMResponse:
        canonical = json.dumps(
            {"system": request.system, "data": request.data_blocks}, sort_keys=True
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        if request.response_schema is not None:
            text = json.dumps(_sample(request.response_schema), sort_keys=True)
        else:
            text = json.dumps({"fake": True, "input_sha256": digest}, sort_keys=True)
        return LLMResponse(
            text=text,
            model=request.model or "fake-model",
            prompt_version=request.prompt_version,
            input_tokens=len(canonical.split()),
            output_tokens=len(text.split()),
        )
