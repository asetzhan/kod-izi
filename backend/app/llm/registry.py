from collections.abc import Callable

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLMProvider
from app.llm.ollama import OllamaProvider


def _ollama() -> LLMProvider:
    settings = get_settings()
    return OllamaProvider(
        settings.ollama_url, settings.ollama_chat_model, settings.ollama_embed_model
    )


_PROVIDERS: dict[str, Callable[[], LLMProvider]] = {
    "fake": FakeLLMProvider,
    "ollama": _ollama,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the provider named in LLM_PROVIDER (ФТ-46)."""
    key = name or get_settings().llm_provider
    try:
        return _PROVIDERS[key]()
    except KeyError:
        raise ValueError(f"unknown LLM provider: {key}") from None
