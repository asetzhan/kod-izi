"""Deterministic provider for tests and development: no network access (ФТ-46)."""

import hashlib
import json

from app.llm.base import LLMRequest, LLMResponse


class FakeLLMProvider:
    name = "fake"

    def complete(self, request: LLMRequest) -> LLMResponse:
        canonical = json.dumps(
            {"system": request.system, "data": request.data_blocks}, sort_keys=True
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        text = json.dumps({"fake": True, "input_sha256": digest}, sort_keys=True)
        return LLMResponse(
            text=text,
            model=request.model or "fake-model",
            prompt_version=request.prompt_version,
            input_tokens=len(canonical.split()),
            output_tokens=len(text.split()),
        )
