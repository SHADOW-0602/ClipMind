from __future__ import annotations

from app.config import Settings


def test_cors_origins_accepts_comma_separated_env(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://one.example,http://two.example")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://one.example", "http://two.example"]
