from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import asdict
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from ..config import Settings
from ..services import cache
from ..services.costs import (
    BudgetExceeded,
    ensure_budget,
    log_model_call,
    token_cost,
)
from .base import ImageInput, Message, ModelResult, ToolSpec, VideoInput

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
FORMAT_REJECTED_HINTS = (
    "response_format",
    "json_schema",
    "json schema",
    "structured output",
    "json mode",
    "unknown parameter",
    "unrecognized",
    "not supported",
    "unsupported",
    "invalid parameter",
)
IMAGE_REJECTED_HINTS = (
    "image",
    "vision",
    "multimodal",
    "image_url",
    "content must be",
)


class OpenAICompatibleError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FormatRejected(RuntimeError):
    """The endpoint rejected response_format; retry with a simpler JSON mode."""


class OpenAICompatibleProvider:
    """Chat Completions client for any OpenAI-compatible endpoint.

    This covers OpenAI, Groq, OpenRouter, Together, DeepSeek, Ollama, LM Studio,
    and similar services. The adapter uses the shared ``LLM_*`` settings, asks
    for JSON schema output when the endpoint supports it, and degrades to
    ``json_object`` or plain text when it does not.
    """

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.model = settings.llm_model
        self.provider = settings.provider
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClipMind/0.1",
        }
        if settings.resolved_llm_api_key:
            headers["Authorization"] = f"Bearer {settings.resolved_llm_api_key}"
        self._client = client or httpx.AsyncClient(
            base_url=settings.llm_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.llm_timeout_s, connect=20.0),
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _encode_image(self, image: ImageInput) -> str:
        mime = image.mime_type or "image/jpeg"
        if image.data is not None:
            payload = image.data
        elif image.path:
            payload = image.path.read_bytes()
        else:
            raise ValueError("ImageInput needs either data or path")
        return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"

    def _build_messages(
        self,
        system: str,
        messages: list[Message],
        images: list[ImageInput] | None,
        video: VideoInput | None,
    ) -> list[dict[str, Any]]:
        built: list[dict[str, Any]] = []
        if system:
            built.append({"role": "system", "content": system})
        for message in messages:
            role = (
                message.role
                if message.role in {"user", "assistant", "system", "developer"}
                else "user"
            )
            built.append({"role": role, "content": message.content})
        if images:
            if not built or built[-1]["role"] != "user":
                built.append({"role": "user", "content": []})
            content = built[-1]["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}] if content else []
                built[-1]["content"] = content
            for image in images:
                image_url: dict[str, Any] = {"url": self._encode_image(image)}
                if image.detail:
                    image_url["detail"] = image.detail
                content.append({"type": "image_url", "image_url": image_url})
        if video:
            # Chat Completions has no portable video block. ClipMind's main path
            # sends transcripts and still frames, so warn instead of failing.
            logger.warning("Video input is not supported by the OpenAI-compatible adapter; ignoring it")
        return built

    def _tool_payload(self, tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _cache_key(
        self,
        system: str,
        messages: list[Message],
        images: list[ImageInput] | None,
        video: VideoInput | None,
        schema: dict[str, Any] | None,
        explicit: str | None,
    ) -> str:
        image_fingerprints = []
        for image in images or []:
            if image.data is not None:
                image_fingerprints.append(hashlib.sha256(image.data).hexdigest())
            elif image.path:
                stat = image.path.stat()
                image_fingerprints.append(f"{image.path.name}:{stat.st_size}:{int(stat.st_mtime)}")
        material = json.dumps(
            {
                "key": explicit,
                "system": system,
                "messages": [asdict(message) for message in messages],
                "schema": schema,
                "provider": self.provider,
                "model": self.model,
                "base_url": str(self.settings.llm_base_url),
                "images": image_fingerprints,
                "video": video.path.stat().st_size if video and video.path else None,
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return str(payload.get("text") or "").strip()
        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") in {"text", "output_text"}:
                        chunks.append(str(part.get("text", "")))
                    elif isinstance(part.get("text"), str):
                        chunks.append(part["text"])
            return "".join(chunks).strip()
        return str(content or choice.get("text") or "").strip()

    @staticmethod
    def _extract_usage(payload: dict[str, Any]) -> tuple[int, int, int]:
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        cached_tokens = int(
            details.get("cached_tokens")
            or usage.get("prompt_cache_hit_tokens")
            or usage.get("cached_tokens")
            or 0
        )
        return input_tokens, output_tokens, cached_tokens

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].lstrip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError("Structured output must be a JSON object")
        return value

    def _format_candidates(self, schema: dict[str, Any] | None) -> list[str | None]:
        if not schema:
            return [None]
        mode = self.settings.llm_json_mode
        if mode == "none":
            return [None]
        if mode == "json_schema":
            return ["json_schema"]
        if mode == "json_object":
            return ["json_object"]
        return ["json_schema", "json_object", None]

    def _request_body(
        self,
        *,
        system: str,
        messages: list[Message],
        images: list[ImageInput] | None,
        video: VideoInput | None,
        tools: list[ToolSpec] | None,
        schema: dict[str, Any] | None,
        max_output_tokens: int,
        format_mode: str | None,
    ) -> dict[str, Any]:
        request_system = system
        if format_mode == "json_object":
            request_system = (
                f"{system}\n\nReturn only a valid JSON object. "
                "Do not wrap it in markdown fences or add commentary."
            ).strip()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(request_system, messages, images, video),
            self.settings.llm_max_tokens_field: max(16, max_output_tokens),
        }
        if self.settings.llm_temperature is not None:
            body["temperature"] = self.settings.llm_temperature
        tool_payload = self._tool_payload(tools)
        if tool_payload:
            body["tools"] = tool_payload
        if schema and format_mode == "json_schema":
            title = re.sub(r"[^A-Za-z0-9_-]+", "_", str(schema.get("title") or "ClipMindOutput"))
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": title[:64] or "ClipMindOutput",
                    "schema": schema,
                    "strict": False,
                },
            }
        elif schema and format_mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    async def _post_with_retry(
        self, body: dict[str, Any], *, format_mode: str | None
    ) -> dict[str, Any]:
        max_retries = max(0, self.settings.llm_max_retries)
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            ensure_budget()
            try:
                response = await self._client.post("/chat/completions", json=body)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                await asyncio.sleep(min(20.0, (0.5 * 2**attempt) + random.uniform(0, 0.3)))
                continue
            if response.status_code in {400, 422} and format_mode:
                message = self._error_message(response)
                if any(hint in message.lower() for hint in FORMAT_REJECTED_HINTS):
                    raise _FormatRejected(message)
            if response.status_code in RETRYABLE_STATUS and attempt < max_retries:
                retry_after = response.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else 0.5 * 2**attempt
                except ValueError:
                    delay = 0.5 * 2**attempt
                delay += random.uniform(0, 0.4)
                logger.warning(
                    "Provider %s returned %s on attempt %d; retrying in %.1fs",
                    self.settings.llm_base_url,
                    response.status_code,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(min(30.0, delay))
                last_error = OpenAICompatibleError(
                    self._error_message(response), status_code=response.status_code
                )
                continue
            if response.status_code >= 400:
                raise OpenAICompatibleError(
                    self._error_message(response), status_code=response.status_code
                )
            return response.json()
        raise OpenAICompatibleError(
            f"Provider unavailable after retries at {self.settings.llm_base_url}: {last_error}"
        )

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error") or {}
            message = error.get("message") or payload.get("message") or response.text
            code = error.get("code") or error.get("type")
            return (
                f"OpenAI-compatible API {response.status_code}: {message}"
                + (f" ({code})" if code else "")
            )
        except (ValueError, AttributeError):
            return f"OpenAI-compatible API {response.status_code}: {response.text[:500]}"

    async def _chat(
        self,
        *,
        system: str,
        messages: list[Message],
        images: list[ImageInput] | None,
        video: VideoInput | None,
        tools: list[ToolSpec] | None,
        schema: dict[str, Any] | None,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        request_images = images if self.settings.llm_vision else None
        for format_mode in self._format_candidates(schema):
            body = self._request_body(
                system=system,
                messages=messages,
                images=request_images,
                video=video,
                tools=tools,
                schema=schema,
                max_output_tokens=max_output_tokens,
                format_mode=format_mode,
            )
            try:
                return await self._post_with_retry(body, format_mode=format_mode)
            except _FormatRejected as exc:
                last_error = exc
                logger.warning(
                    "Endpoint rejected response_format=%s; trying a simpler JSON mode: %s",
                    format_mode,
                    exc,
                )
                continue
            except OpenAICompatibleError as exc:
                if (
                    request_images
                    and exc.status_code in {400, 422}
                    and any(hint in str(exc).lower() for hint in IMAGE_REJECTED_HINTS)
                ):
                    logger.warning(
                        "Endpoint rejected image input; retrying without keyframes: %s", exc
                    )
                    request_images = None
                    retry_body = self._request_body(
                        system=system,
                        messages=messages,
                        images=None,
                        video=video,
                        tools=tools,
                        schema=schema,
                        max_output_tokens=max_output_tokens,
                        format_mode=format_mode,
                    )
                    return await self._post_with_retry(retry_body, format_mode=format_mode)
                raise
        raise OpenAICompatibleError(
            f"Endpoint rejected every configured JSON mode: {last_error}"
        )

    async def generate(
        self,
        *,
        system: str,
        messages: list[Message],
        images: list[ImageInput] | None = None,
        video: VideoInput | None = None,
        tools: list[ToolSpec] | None = None,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int = 2000,
        cache_key: str | None = None,
    ) -> ModelResult:
        key = self._cache_key(system, messages, images, video, response_schema, cache_key)
        cached = cache.get_json(key)
        if cached:
            result = ModelResult(
                text=cached.get("text", ""),
                parsed=cached.get("parsed"),
                input_tokens=int(cached.get("input_tokens", 0)),
                output_tokens=int(cached.get("output_tokens", 0)),
                cached_tokens=int(cached.get("cached_tokens", 0)),
                cost_usd=0.0,
                latency_ms=0,
                model=self.model,
                provider=self.provider,
                cache_hit=True,
            )
            log_model_call(
                provider=self.provider,
                model=self.model,
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                cost_usd=0.0,
                latency_ms=0,
                purpose=(cache_key or "unknown").split(":", 1)[0],
                cache_hit=True,
            )
            return result

        purpose = (cache_key or "unknown").split(":", 1)[0]
        started = time.perf_counter()
        try:
            payload = await self._chat(
                system=system,
                messages=messages,
                images=images,
                video=video,
                tools=tools,
                schema=response_schema,
                max_output_tokens=max_output_tokens,
            )
        except BudgetExceeded:
            raise
        except Exception as exc:
            if isinstance(exc, OpenAICompatibleError):
                raise
            raise OpenAICompatibleError(str(exc)) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = self._extract_text(payload)
        input_tokens, output_tokens, cached_tokens = self._extract_usage(payload)
        cost = token_cost(input_tokens, cached_tokens, output_tokens, model=self.model).cost_usd
        log_model_call(
            provider=self.provider,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            purpose=purpose,
        )
        result = ModelResult(
            text=text,
            parsed=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            model=self.model,
            provider=self.provider,
            raw=payload,
        )
        if not response_schema:
            cache.put_json(
                key,
                {
                    "text": result.text,
                    "parsed": None,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cached_tokens": result.cached_tokens,
                },
            )
            return result

        try:
            parsed = self._parse_json(text)
            validate(instance=parsed, schema=response_schema)
            result.parsed = parsed
        except (ValueError, ValidationError) as exc:
            logger.warning("Structured output failed validation, repairing once: %s", exc)
            repair_messages = [
                *messages,
                Message(role="assistant", content=text or "(empty)"),
                Message(
                    role="user",
                    content=(
                        "Your previous response did not validate against the JSON schema. "
                        f"Validation error: {exc}. Return only corrected JSON matching the schema."
                    ),
                ),
            ]
            repair_started = time.perf_counter()
            repair_payload = await self._chat(
                system=system,
                messages=repair_messages,
                images=images,
                video=video,
                tools=tools,
                schema=response_schema,
                max_output_tokens=max_output_tokens,
            )
            repair_latency = int((time.perf_counter() - repair_started) * 1000)
            repair_text = self._extract_text(repair_payload)
            r_in, r_out, r_cached = self._extract_usage(repair_payload)
            r_cost = token_cost(r_in, r_cached, r_out, model=self.model).cost_usd
            log_model_call(
                provider=self.provider,
                model=self.model,
                input_tokens=r_in,
                output_tokens=r_out,
                cached_tokens=r_cached,
                cost_usd=r_cost,
                latency_ms=repair_latency,
                purpose=f"{purpose}_repair",
            )
            result.input_tokens += r_in
            result.output_tokens += r_out
            result.cached_tokens += r_cached
            result.cost_usd += r_cost
            result.latency_ms += repair_latency
            result.text = repair_text
            result.raw = repair_payload
            result.repair_attempts = 1
            try:
                parsed = self._parse_json(repair_text)
                validate(instance=parsed, schema=response_schema)
                result.parsed = parsed
            except (ValueError, ValidationError) as repair_exc:
                raise OpenAICompatibleError(
                    "Provider returned invalid structured JSON after one repair attempt: "
                    f"{repair_exc}"
                ) from repair_exc

        cache.put_json(
            key,
            {
                "text": result.text,
                "parsed": result.parsed,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cached_tokens": result.cached_tokens,
            },
        )
        return result
