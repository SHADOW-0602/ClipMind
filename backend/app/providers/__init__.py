from __future__ import annotations

import inspect
from functools import lru_cache

from ..config import get_settings
from .base import LLMProvider
from .meta import MetaProvider
from .openai_compatible import OpenAICompatibleProvider

# Tests inject a deterministic provider here. This is deliberately not a
# user-facing mode: production always selects a live provider from settings.
_provider_override: LLMProvider | None = None


def set_provider_override(provider: LLMProvider | None) -> None:
    global _provider_override
    _provider_override = provider
    get_provider.cache_clear()


@lru_cache
def get_provider() -> LLMProvider:
    """Return one process-wide provider so HTTP connections are reused.

    The provider owns a long-lived httpx client in live mode. ``close_provider``
    is called from the FastAPI lifespan shutdown hook; tests can call
    ``reset_provider`` after changing settings.
    """
    if _provider_override is not None:
        return _provider_override
    settings = get_settings()
    if settings.effective_provider == "meta":
        if not settings.resolved_meta_api_key:
            raise RuntimeError(
                f"PROVIDER={settings.provider} requires MODEL_API_KEY (or META_API_KEY). "
                "Set it in .env."
            )
        return MetaProvider(settings)
    if settings.provider_requires_key and not settings.resolved_llm_api_key:
        raise RuntimeError(
            f"PROVIDER={settings.provider} requires MODEL_API_KEY (or LLM_API_KEY). "
            "Set it in .env, or use PROVIDER=ollama/lmstudio for a keyless local endpoint."
        )
    return OpenAICompatibleProvider(settings)


async def close_provider() -> None:
    if get_provider.cache_info().currsize == 0:
        return
    provider = get_provider()
    close = getattr(provider, "aclose", None)
    if close is not None:
        result = close()
        if inspect.isawaitable(result):
            await result
    reset_provider()


def reset_provider() -> None:
    get_provider.cache_clear()


__all__ = [
    "LLMProvider",
    "MetaProvider",
    "OpenAICompatibleProvider",
    "close_provider",
    "get_provider",
    "reset_provider",
    "set_provider_override",
]
