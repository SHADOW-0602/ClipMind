from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

PRESET_ENV_VARS = (
    "PROVIDER",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_ASR_MODEL",
    "LLM_JSON_MODE",
    "LLM_VISION",
    "LLM_INPUT_PRICE_PER_M",
    "LLM_CACHED_INPUT_PRICE_PER_M",
    "LLM_OUTPUT_PRICE_PER_M",
    "LLM_ASR_USD_PER_HOUR",
    "ASR_PROVIDER",
)


def _clear_preset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in PRESET_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


def test_cors_origins_accepts_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://one.example,http://two.example")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://one.example", "http://two.example"]


def test_groq_is_the_free_default(monkeypatch) -> None:
    _clear_preset_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.provider == "groq"
    assert settings.effective_provider == "openai_compatible"
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.active_model == "openai/gpt-oss-120b"
    assert settings.effective_asr_provider == "openai_compatible"
    assert settings.active_asr_model == "whisper-large-v3-turbo"
    assert settings.llm_max_tokens_field == "max_completion_tokens"
    assert settings.llm_reasoning_effort == "low"
    assert settings.active_input_price_per_m == 0.0


def test_gemini_preset_uses_local_whisper_for_asr(monkeypatch) -> None:
    _clear_preset_env(monkeypatch)

    settings = Settings(_env_file=None, provider="gemini")

    assert settings.provider == "gemini"
    assert settings.effective_provider == "openai_compatible"
    assert settings.llm_base_url.startswith("https://generativelanguage.googleapis.com/")
    assert settings.active_model == "gemini-2.5-flash"
    assert settings.effective_asr_provider == "whisper"
    assert settings.active_asr_model == settings.whisper_model


def test_explicit_llm_model_wins_over_preset(monkeypatch) -> None:
    _clear_preset_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "my-private-model")

    settings = Settings(_env_file=None, provider="groq")

    assert settings.llm_model == "my-private-model"


def test_custom_provider_requires_base_url_and_model(monkeypatch) -> None:
    _clear_preset_env(monkeypatch)

    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(_env_file=None, provider="custom")


def test_unknown_provider_is_rejected(monkeypatch) -> None:
    _clear_preset_env(monkeypatch)

    with pytest.raises(ValidationError, match="Unsupported PROVIDER"):
        Settings(_env_file=None, provider="mock")
