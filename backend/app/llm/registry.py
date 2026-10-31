from collections.abc import Callable

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLMProvider

_PROVIDERS: dict[str, Callable[[], LLMProvider]] = {
    "fake": FakeLLMProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the provider named in LLM_PROVIDER (ФТ-46)."""
    key = name or get_settings().llm_provider
    try:
        return _PROVIDERS[key]()
    except KeyError:
        raise ValueError(f"unknown LLM provider: {key}") from None
