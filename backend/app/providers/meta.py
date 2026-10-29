from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import random
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


class MetaAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MetaProvider:
    """Responses API client for Meta Model API (https://dev.meta.ai/docs).

    Auth is `Authorization: Bearer MODEL_API_KEY`; base URL defaults to
    https://api.meta.ai/v1. Structured output is requested with `text.format`
    on /responses, as required by the current docs.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.meta_model
        self._client = httpx.AsyncClient(
            base_url=settings.meta_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.meta_timeout_s, connect=20.0),
            headers={
                "Authorization": f"Bearer {settings.resolved_meta_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ClipMind/0.1",
            },
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

    def _build_input(
        self,
        messages: list[Message],
        images: list[ImageInput] | None,
        video: VideoInput | None,
    ) -> list[dict[str, Any]]:
        built: list[dict[str, Any]] = []
        for message in messages:
            role = message.role if message.role in {"user", "assistant", "system", "developer"} else "user"
            block_type = "output_text" if role == "assistant" else "input_text"
            built.append(
                {
                    "type": "message",
                    "role": role,
                    "content": [{"type": block_type, "text": message.content}],
                }
            )
        if images:
            if not built or built[-1]["role"] != "user":
                built.append({"type": "message", "role": "user", "content": []})
            for image in images:
                built[-1]["content"].append(
                    {"type": "input_image", "image_url": self._encode_image(image)}
                )
        if video:
            if not built or built[-1]["role"] != "user":
                built.append({"type": "message", "role": "user", "content": []})
            if video.path:
                encoded = base64.b64encode(video.path.read_bytes()).decode("ascii")
                built[-1]["content"].append(
                    {
                        "type": "input_video",
                        "video_url": f"data:{video.mime_type};base64,{encoded}",
                    }
                )
            # TODO(verify): large videos should use the Files API rather than inline
            # data URLs. ClipMind's main path uses transcripts and still frames.
        return built

    def _tool_payload(self, tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": tool.strict,
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
        if explicit:
            material = json.dumps(
                {
                    "key": explicit,
                    "system": system,
                    "messages": [asdict(message) for message in messages],
                    "schema": schema,
                    "model": self.model,
                    "images": image_fingerprints,
                    "video": video.path.stat().st_size if video and video.path else None,
                },
                sort_keys=True,
            )
        else:
            material = json.dumps(
                {
                    "system": system,
                    "messages": [asdict(message) for message in messages],
                    "schema": schema,
                    "model": self.model,
                    "images": image_fingerprints,
                },
                sort_keys=True,
            )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        if payload.get("output_text"):
            return str(payload["output_text"])
        chunks: list[str] = []
        for item in payload.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        chunks.append(str(content.get("text", "")))
        return "".join(chunks).strip()

    @staticmethod
    def _extract_usage(payload: dict[str, Any]) -> tuple[int, int, int]:
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
        cached_tokens = int(details.get("cached_tokens") or 0)
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

    async def _post_with_retry(self, body: dict[str, Any]) -> dict[str, Any]:
        max_retries = max(0, self.settings.meta_max_retries)
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            ensure_budget()
            try:
                response = await self._client.post("/responses", json=body)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                await asyncio.sleep(min(20.0, (0.5 * 2**attempt) + random.uniform(0, 0.3)))
                continue
            if response.status_code in RETRYABLE_STATUS and attempt < max_retries:
                retry_after = response.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after else 0.5 * 2**attempt
                except ValueError:
                    delay = 0.5 * 2**attempt
                delay += random.uniform(0, 0.4)
                logger.warning(
                    "Meta API %s on attempt %d; retrying in %.1fs",
                    response.status_code,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(min(30.0, delay))
                last_error = MetaAPIError(
                    self._error_message(response), status_code=response.status_code
                )
                continue
            if response.status_code >= 400:
                raise MetaAPIError(self._error_message(response), status_code=response.status_code)
            return response.json()
        raise MetaAPIError(f"Meta API unavailable after retries: {last_error}")

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error") or {}
            message = error.get("message") or payload.get("message") or response.text
            code = error.get("code") or error.get("type")
            return f"Meta API {response.status_code}: {message}" + (f" ({code})" if code else "")
        except (ValueError, AttributeError):
            return f"Meta API {response.status_code}: {response.text[:500]}"

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
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": system,
            "input": self._build_input(messages, images, video),
            "max_output_tokens": max(16, max_output_tokens),
            "store": False,
            "reasoning": {"effort": self.settings.meta_reasoning_effort},
        }
        tool_payload = self._tool_payload(tools)
        if tool_payload:
            body["tools"] = tool_payload
        if schema:
            title = str(schema.get("title") or "ClipMindOutput").replace(" ", "")
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": title[:64] or "ClipMindOutput",
                    "schema": schema,
                    "strict": False,
                }
            }
        return body

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
                provider="meta",
                cache_hit=True,
            )
            log_model_call(
                provider="meta",
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
        body = self._request_body(
            system=system,
            messages=messages,
            images=images,
            video=video,
            tools=tools,
            schema=response_schema,
            max_output_tokens=max_output_tokens,
        )
        started = time.perf_counter()
        try:
            payload = await self._post_with_retry(body)
        except BudgetExceeded:
            raise
        except Exception as exc:
            # Legacy budget exceptions and exhausted retries should surface clearly.
            if isinstance(exc, MetaAPIError):
                raise
            raise MetaAPIError(str(exc)) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = self._extract_text(payload)
        input_tokens, output_tokens, cached_tokens = self._extract_usage(payload)
        cost = token_cost(input_tokens, cached_tokens, output_tokens, model=self.model).cost_usd
        log_model_call(
            provider="meta",
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
            provider="meta",
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
            repair_body = self._request_body(
                system=system,
                messages=repair_messages,
                images=images,
                video=video,
                tools=tools,
                schema=response_schema,
                max_output_tokens=max_output_tokens,
            )
            repair_started = time.perf_counter()
            repair_payload = await self._post_with_retry(repair_body)
            repair_latency = int((time.perf_counter() - repair_started) * 1000)
            repair_text = self._extract_text(repair_payload)
            r_in, r_out, r_cached = self._extract_usage(repair_payload)
            r_cost = token_cost(r_in, r_cached, r_out, model=self.model).cost_usd
            log_model_call(
                provider="meta",
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
                raise MetaAPIError(
                    f"Meta returned invalid structured JSON after one repair attempt: {repair_exc}"
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
