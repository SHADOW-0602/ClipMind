from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from app.config import Settings
from app.providers.base import ImageInput, Message
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.services.asr import OpenAICompatibleTranscriber


def _settings(**overrides) -> Settings:
    values = {
        "provider": "groq",
        "llm_base_url": "https://example.test/v1",
        "llm_model": "test-model",
        "llm_api_key": "test-key",
        "llm_vision": False,
        "llm_input_price_per_m": 0.0,
        "llm_cached_input_price_per_m": 0.0,
        "llm_output_price_per_m": 0.0,
        "llm_asr_usd_per_hour": 0.0,
        "asr_provider": "openai_compatible",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.test/v1",
        headers={"Authorization": "Bearer test-key"},
    )


def test_chat_completions_parses_json_and_usage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "prompt_tokens_details": {"cached_tokens": 20},
                },
            },
        )

    async def run():
        async with _client(handler) as client:
            provider = OpenAICompatibleProvider(_settings(), client=client)
            return await provider.generate(
                system="Return JSON.",
                messages=[Message(role="user", content="Say ok.")],
                response_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
                cache_key="test:json-ok",
            )

    result = asyncio.run(run())

    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert result.parsed == {"ok": True}
    assert (result.input_tokens, result.output_tokens, result.cached_tokens) == (120, 30, 20)
    assert result.provider == "groq"
    assert result.repair_attempts == 0


def test_response_format_falls_back_to_json_object() -> None:
    calls = {"count": 0}
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        body = json.loads(request.content)
        bodies.append(body)
        if calls["count"] == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "response_format json_schema is not supported"}},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {}},
        )

    async def run():
        async with _client(handler) as client:
            provider = OpenAICompatibleProvider(_settings(), client=client)
            return await provider.generate(
                system="Return JSON.",
                messages=[Message(role="user", content="Say ok.")],
                response_schema={"type": "object", "required": ["ok"]},
                cache_key="test:format-fallback",
            )

    result = asyncio.run(run())

    assert calls["count"] == 2
    assert bodies[0]["response_format"]["type"] == "json_schema"
    assert bodies[1]["response_format"]["type"] == "json_object"
    assert result.parsed == {"ok": True}


def test_vision_can_be_disabled_per_provider() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "done"}}], "usage": {}},
        )

    async def run():
        async with _client(handler) as client:
            provider = OpenAICompatibleProvider(_settings(llm_vision=False), client=client)
            return await provider.generate(
                system="Analyze.",
                messages=[Message(role="user", content="Describe this.")],
                images=[ImageInput(data=b"not-an-image")],
                cache_key="test:vision-off",
            )

    result = asyncio.run(run())

    user_message = captured["body"]["messages"][-1]
    assert user_message["content"] == "Describe this."
    assert result.text == "done"


def test_openai_transcriber_parses_segments_and_words(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "text": "Hello world",
                "language": "en",
                "segments": [{"start": 0.0, "end": 1.2, "text": "Hello world"}],
                "words": [
                    {"start": 0.0, "end": 0.5, "word": "Hello"},
                    {"start": 0.5, "end": 1.2, "word": "world"},
                ],
            },
        )

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"RIFF-test")

    async def run():
        async with _client(handler) as client:
            transcriber = OpenAICompatibleTranscriber(_settings(), client=client)
            return await transcriber.transcribe(audio, 1.2, tmp_path)

    result = asyncio.run(run())

    assert captured["path"] == "/v1/audio/transcriptions"
    assert captured["authorization"] == "Bearer test-key"
    assert result["provider"] == "groq-asr"
    assert result["text"] == "Hello world"
    assert result["segments"][0]["words"][1]["word"] == "world"
