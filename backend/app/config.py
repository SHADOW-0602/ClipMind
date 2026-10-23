from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


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

    mock_mode: bool = True
    provider: Literal["meta", "mock"] = "mock"

    model_api_key: str = ""
    meta_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    meta_asr_model: str = "muse-voice-transcribe-1.0"
    use_meta_asr: bool = True
    meta_timeout_s: float = 120.0
    meta_max_retries: int = 4
    meta_reasoning_effort: str = "low"

    max_budget_usd: float = 100.0
    hackathon_credits_usd: float = 150.0
    meta_input_price_per_m: float = 1.25
    meta_cached_input_price_per_m: float = 0.15
    meta_output_price_per_m: float = 4.25

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

    @property
    def effective_provider(self) -> str:
        if self.mock_mode or self.provider == "mock":
            return "mock"
        return "meta"

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
