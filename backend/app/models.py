from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class BrandProfile(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True)
    tone_description: str = ""
    voice_dos: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    voice_donts: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    banned_words: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    example_posts: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    target_audience: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Project(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    brand_profile_id: str | None = Field(default=None, foreign_key="brandprofile.id")
    status: str = Field(default="draft", index=True)
    source_url: str | None = None
    error: str | None = None


class MediaAsset(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    kind: str = "video"  # video | audio | text
    original_filename: str = ""
    path: str
    normalized_path: str | None = None
    audio_path: str | None = None
    duration_s: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    size_bytes: int = 0
    checksum: str = Field(default="", index=True)
    status: str = "ready"
    frames_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Transcript(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    asset_id: str = Field(foreign_key="mediaasset.id", index=True)
    language: str = "en"
    text: str = Field(default="", sa_column=Column(Text))
    segments_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    provider: str = "unknown"
    created_at: datetime = Field(default_factory=utcnow)


class TopicSegment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    asset_id: str = Field(foreign_key="mediaasset.id", index=True)
    start: float
    end: float
    topic: str
    summary: str = ""
    sentiment: str = "neutral"
    energy_score: float = 0.5
    speaker_intent: str = ""
    quotable: bool = False


class Clip(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    asset_id: str = Field(foreign_key="mediaasset.id")
    start: float
    end: float
    title: str
    hook: str = ""
    source_quote: str = Field(default="", sa_column=Column(Text))
    score: float = 0.0
    rationale: str = ""
    status: str = "selected"  # selected | rendered | failed | rejected
    render_path: str | None = None
    srt_path: str | None = None
    thumbnail_path: str | None = None
    risk_flags_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    critique_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CopyVariant(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    clip_id: str = Field(foreign_key="clip.id", index=True)
    platform: str
    caption: str = Field(default="", sa_column=Column(Text))
    hooks: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    hashtags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cta: str = ""
    version: int = 1
    created_at: datetime = Field(default_factory=utcnow)


class Summary(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", unique=True, index=True)
    tldr: str = ""
    bullets_json: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    chapters_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    quotes_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class InsightReport(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", unique=True, index=True)
    report_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    stage: str = "queued"
    status: str = "queued"  # queued | running | completed | failed | cancelled
    progress: float = 0.0
    error: str | None = None
    options_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    stages_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    events_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    checkpoint_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ModelCall(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    job_id: str | None = Field(default=None, foreign_key="job.id", index=True)
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    purpose: str = ""
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AsrCall(SQLModel, table=True):
    """Meta Voice Transcribe is billed per audio-second, not per token."""

    id: str = Field(default_factory=new_id, primary_key=True)
    job_id: str | None = Field(default=None, foreign_key="job.id", index=True)
    model: str
    audio_seconds: float = 0.0
    cost_usd: float = 0.0
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=utcnow, index=True)
