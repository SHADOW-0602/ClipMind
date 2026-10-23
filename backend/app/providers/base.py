from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ImageInput:
    path: Path | None = None
    data: bytes | None = None
    mime_type: str = "image/jpeg"
    detail: str | None = None

    @property
    def size_bytes(self) -> int:
        if self.data is not None:
            return len(self.data)
        if self.path:
            return self.path.stat().st_size
        return 0


@dataclass(slots=True)
class VideoInput:
    path: Path | None = None
    mime_type: str = "video/mp4"


@dataclass(slots=True)
class Message:
    role: str
    content: str


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = False


@dataclass(slots=True)
class ModelResult:
    text: str
    parsed: dict[str, Any] | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    repair_attempts: int = 0


@runtime_checkable
class LLMProvider(Protocol):
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
    ) -> ModelResult: ...
