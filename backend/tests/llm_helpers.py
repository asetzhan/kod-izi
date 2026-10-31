"""LLM stand-ins for tests: nothing leaves the machine (CLAUDE.md)."""

from collections.abc import Callable

from app.llm.base import LLMRequest, LLMResponse
from app.llm.fake import FakeLLMProvider, fake_embedding


class RecordingProvider(FakeLLMProvider):
    """The normal fake provider that also keeps every request it got."""

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return super().complete(request)


class ScriptedProvider:
    """Answers with the given texts in turn (or a function of the request)."""

    name = "scripted"

    def __init__(self, answers: list[str | Callable[[LLMRequest], str]]) -> None:
        self.answers = list(answers)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        text = answer(request) if callable(answer) else answer
        return LLMResponse(text, "scripted-model", request.prompt_version, 10, 10)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [fake_embedding(t) for t in texts]
