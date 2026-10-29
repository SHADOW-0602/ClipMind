from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

# Presets only fill fields the user did not set explicitly. Any LLM_* or ASR_*
# environment variable still wins, so every preset can be pointed at a proxy or
# a different model without changing code.
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    # Free tier: OpenAI-compatible chat + Whisper transcription with one key.
    # GPT-OSS 120B replaced Llama 3.3 70B on Groq's free tier in August 2026.
    "groq": {
        "llm_base_url": "https://api.groq.com/openai/v1",
        "llm_model": "openai/gpt-oss-120b",
        "llm_asr_model": "whisper-large-v3-turbo",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "llm_max_tokens_field": "max_completion_tokens",
        "llm_reasoning_effort": "low",
        "asr_provider": "openai_compatible",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    # Free tier: strong multimodal text models. ASR falls back to local Whisper.
    "gemini": {
        "llm_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "llm_model": "gemini-2.5-flash",
        "llm_asr_model": "",
        "llm_vision": True,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    # Free models are available with a ":free" suffix. ASR is not offered.
    "openrouter": {
        "llm_base_url": "https://openrouter.ai/api/v1",
        "llm_model": "meta-llama/llama-3.3-70b-instruct:free",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    # Fully local and free. Start Ollama and pull a model first.
    "ollama": {
        "llm_base_url": "http://localhost:11434/v1",
        "llm_model": "llama3.2",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    # Fully local and free. Load a model in LM Studio first.
    "lmstudio": {
        "llm_base_url": "http://localhost:1234/v1",
        "llm_model": "local-model",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    "mistral": {
        "llm_base_url": "https://api.mistral.ai/v1",
        "llm_model": "mistral-small-latest",
        "llm_asr_model": "voxtral-mini-latest",
        "llm_vision": True,
        "llm_json_mode": "auto",
        "asr_provider": "openai_compatible",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    "cerebras": {
        "llm_base_url": "https://api.cerebras.ai/v1",
        "llm_model": "llama-3.3-70b",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    "deepseek": {
        "llm_base_url": "https://api.deepseek.com/v1",
        "llm_model": "deepseek-chat",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.27,
        "llm_cached_input_price_per_m": 0.07,
        "llm_output_price_per_m": 1.10,
        "llm_asr_usd_per_hour": 0.0,
    },
    "together": {
        "llm_base_url": "https://api.together.xyz/v1",
        "llm_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "llm_asr_model": "whisper-large-v3",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "openai_compatible",
        "llm_input_price_per_m": 0.88,
        "llm_cached_input_price_per_m": 0.88,
        "llm_output_price_per_m": 0.88,
        "llm_asr_usd_per_hour": 0.36,
    },
    "openai": {
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-4o-mini",
        "llm_asr_model": "whisper-1",
        "llm_vision": True,
        "llm_json_mode": "auto",
        "asr_provider": "openai_compatible",
        "llm_input_price_per_m": 0.15,
        "llm_cached_input_price_per_m": 0.075,
        "llm_output_price_per_m": 0.60,
        "llm_asr_usd_per_hour": 0.36,
    },
    # Explicit alias for a generic OpenAI-compatible endpoint. Use PROVIDER=custom
    # when the base URL and model are not OpenAI's.
    "openai_compatible": {
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-4o-mini",
        "llm_asr_model": "whisper-1",
        "llm_vision": True,
        "llm_json_mode": "auto",
        "asr_provider": "openai_compatible",
        "llm_input_price_per_m": 0.15,
        "llm_cached_input_price_per_m": 0.075,
        "llm_output_price_per_m": 0.60,
        "llm_asr_usd_per_hour": 0.36,
    },
    "xai": {
        "llm_base_url": "https://api.x.ai/v1",
        "llm_model": "grok-2-latest",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 2.0,
        "llm_cached_input_price_per_m": 2.0,
        "llm_output_price_per_m": 10.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    "fireworks": {
        "llm_base_url": "https://api.fireworks.ai/inference/v1",
        "llm_model": "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 0.90,
        "llm_cached_input_price_per_m": 0.90,
        "llm_output_price_per_m": 0.90,
        "llm_asr_usd_per_hour": 0.0,
    },
    "perplexity": {
        "llm_base_url": "https://api.perplexity.ai",
        "llm_model": "sonar",
        "llm_asr_model": "",
        "llm_vision": False,
        "llm_json_mode": "auto",
        "asr_provider": "whisper",
        "llm_input_price_per_m": 1.0,
        "llm_cached_input_price_per_m": 1.0,
        "llm_output_price_per_m": 1.0,
        "llm_asr_usd_per_hour": 0.0,
    },
    # No preset: PROVIDER=custom requires LLM_BASE_URL and LLM_MODEL.
    "custom": {},
    # Native Meta Responses API. Uses the META_* settings below.
    "meta": {},
}

PROVIDER_REQUIRES_KEY = {
    "groq",
    "gemini",
    "openrouter",
    "mistral",
    "cerebras",
    "deepseek",
    "together",
    "openai",
    "openai_compatible",
    "xai",
    "fireworks",
    "perplexity",
    "meta",
}


class Settings(BaseSettings):
    """Runtime configuration, loaded from the repository-root .env file."""

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "ClipMind"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # Default is Groq's free tier. Other presets are listed in PROVIDER_PRESETS.
    provider: str = "groq"

    # Shared live-provider key. Provider-specific overrides are optional.
    model_api_key: str = ""
    llm_api_key: str = ""
    meta_api_key: str = ""

    # --- OpenAI-compatible Chat Completions provider -------------------------
    # Presets fill these unless the matching environment variable is set.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_asr_model: str = "whisper-large-v3-turbo"
    llm_timeout_s: float = 120.0
    llm_max_retries: int = 4
    llm_json_mode: Literal["auto", "json_schema", "json_object", "none"] = "auto"
    llm_max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    llm_reasoning_effort: str = ""
    llm_temperature: float | None = None
    llm_vision: bool = True

    # --- Meta Model API (optional native provider) ---------------------------
    meta_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    meta_asr_model: str = "muse-voice-transcribe-1.0"
    meta_timeout_s: float = 120.0
    meta_max_retries: int = 4
    meta_reasoning_effort: str = "low"

    # --- Speech-to-text selection -------------------------------------------
    # auto = Meta ASR for PROVIDER=meta, local Whisper for custom, and
    # OpenAI-compatible ASR for the other hosted presets.
    asr_provider: Literal["auto", "meta", "openai_compatible", "whisper"] = "auto"

    max_budget_usd: float = 100.0
    hackathon_credits_usd: float = 150.0
    meta_input_price_per_m: float = 1.25
    meta_cached_input_price_per_m: float = 0.15
    meta_output_price_per_m: float = 4.25
    meta_asr_usd_per_hour: float = 0.18
    llm_input_price_per_m: float = 0.0
    llm_cached_input_price_per_m: float = 0.0
    llm_output_price_per_m: float = 0.0
    llm_asr_usd_per_hour: float = 0.0

    data_dir: Path = Field(default=ROOT_DIR / "data")
    database_url: str = ""
    max_upload_mb: int = 500
    max_duration_s: int = 7200
    min_clip_s: int = 15
    max_clip_s: int = 60
    job_concurrency: int = 1
    auto_resume_jobs: bool = True
    rate_limit_per_minute: int = 60

    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    force_whisper: bool = False

    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    public_api_url: str = "http://localhost:8000"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("data_dir", mode="before")
    @classmethod
    def resolve_data_dir(cls, value: object) -> Path:
        path = Path(value) if value else ROOT_DIR / "data"
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path.resolve()

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str:
        normalized = str(value or "groq").strip().lower().replace("-", "_")
        if normalized not in PROVIDER_PRESETS:
            allowed = ", ".join(sorted(PROVIDER_PRESETS))
            raise ValueError(f"Unsupported PROVIDER={value!r}. Choose one of: {allowed}")
        return normalized

    @model_validator(mode="after")
    def apply_provider_preset(self) -> Settings:
        preset = PROVIDER_PRESETS[self.provider]
        for field, value in preset.items():
            if field not in self.model_fields_set:
                setattr(self, field, value)
        if self.provider == "custom":
            missing = [
                field.upper()
                for field in ("llm_base_url", "llm_model")
                if field not in self.model_fields_set
            ]
            if missing:
                raise ValueError(
                    "PROVIDER=custom requires " + " and ".join(missing) + " to be set."
                )
        return self

    @property
    def effective_provider(self) -> str:
        return "meta" if self.provider == "meta" else "openai_compatible"

    @property
    def provider_requires_key(self) -> bool:
        return self.provider in PROVIDER_REQUIRES_KEY

    @property
    def resolved_llm_api_key(self) -> str:
        return self.llm_api_key or self.model_api_key

    @property
    def resolved_meta_api_key(self) -> str:
        return self.meta_api_key or self.model_api_key

    @property
    def effective_asr_provider(self) -> str:
        if self.force_whisper:
            return "whisper"
        if self.asr_provider == "auto":
            if self.effective_provider == "meta":
                return "meta"
            if self.provider == "custom":
                return "whisper"
            return "openai_compatible"
        return self.asr_provider

    @property
    def active_model(self) -> str:
        return self.meta_model if self.effective_provider == "meta" else self.llm_model

    @property
    def active_asr_model(self) -> str:
        provider = self.effective_asr_provider
        if provider == "meta":
            return self.meta_asr_model
        if provider == "openai_compatible":
            return self.llm_asr_model
        return self.whisper_model

    @property
    def active_input_price_per_m(self) -> float:
        return self.meta_input_price_per_m if self.effective_provider == "meta" else self.llm_input_price_per_m

    @property
    def active_cached_input_price_per_m(self) -> float:
        return (
            self.meta_cached_input_price_per_m
            if self.effective_provider == "meta"
            else self.llm_cached_input_price_per_m
        )

    @property
    def active_output_price_per_m(self) -> float:
        return self.meta_output_price_per_m if self.effective_provider == "meta" else self.llm_output_price_per_m

    @property
    def active_asr_usd_per_hour(self) -> float:
        provider = self.effective_asr_provider
        if provider == "meta":
            return self.meta_asr_usd_per_hour
        if provider == "openai_compatible":
            return self.llm_asr_usd_per_hour
        return 0.0

    @property
    def provider_base_url(self) -> str:
        return self.meta_base_url if self.effective_provider == "meta" else self.llm_base_url

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("sqlite:///./"):
                tail = self.database_url.removeprefix("sqlite:///./")
                return f"sqlite:///{(ROOT_DIR / tail).as_posix()}"
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'clipmind.db').as_posix()}"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.uploads_dir,
            self.processed_dir,
            self.renders_dir,
            self.cache_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
