from __future__ import annotations

import inspect
from functools import lru_cache

from ..config import get_settings
from .base import LLMProvider
from .meta import MetaProvider
from .mock import MockProvider


@lru_cache
def get_provider() -> LLMProvider:
    """Return one process-wide provider so HTTP connections are reused.

    The provider owns a long-lived httpx client in Meta mode. ``close_provider``
    is called from the FastAPI lifespan shutdown hook; tests can call
    ``reset_provider`` after changing settings.
    """
    settings = get_settings()
    if settings.effective_provider == "meta":
        if not settings.model_api_key:
            raise RuntimeError(
                "PROVIDER=meta requires MODEL_API_KEY. Set it in .env or use MOCK_MODE=true."
            )
        return MetaProvider(settings)
    return MockProvider(settings)


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
    "MockProvider",
    "close_provider",
    "get_provider",
    "reset_provider",
]
