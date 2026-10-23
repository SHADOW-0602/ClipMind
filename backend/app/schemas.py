from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PLATFORMS = ("instagram", "youtube", "tiktok", "linkedin", "x")


# ── API: brand profiles ──────────────────────────────────────────────────────


class BrandProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tone_description: str = ""
    voice_dos: list[str] = Field(default_factory=list)
    voice_donts: list[str] = Field(default_factory=list)
    banned_words: list[str] = Field(default_factory=list)
    example_posts: list[str] = Field(default_factory=list)
    target_audience: str = ""


class BrandProfileCreate(BrandProfileBase):
    pass


class BrandProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tone_description: str | None = None
    voice_dos: list[str] | None = None
    voice_donts: list[str] | None = None
    banned_words: list[str] | None = None
    example_posts: list[str] | None = None
    target_audience: str | None = None


class BrandProfileRead(BrandProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


# ── API: projects, media, jobs ──────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    brand_profile_id: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand_profile_id: str | None = None


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    kind: str
    original_filename: str
    path: str
    normalized_path: str | None
    audio_path: str | None
    duration_s: float
    width: int
    height: int
    fps: float
    size_bytes: int
    status: str
    created_at: datetime
    media_url: str | None = None
    audio_url: str | None = None
    frames: list[dict[str, Any]] = Field(default_factory=list)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    stage: str
    status: str
    progress: float
    error: str | None
    stages_json: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProcessRequest(BaseModel):
    n_clips: int = Field(default=8, ge=1, le=20)
    platforms: list[str] = Field(default_factory=lambda: list(PLATFORMS))
    min_clip_s: int = Field(default=15, ge=8, le=60)
    max_clip_s: int = Field(default=60, ge=15, le=120)
    brand_profile_id: str | None = None
    regenerate: bool = False

    @field_validator("platforms")
    @classmethod
    def valid_platforms(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(platform.strip().lower() for platform in value if platform.strip()))
        invalid = [platform for platform in cleaned if platform not in PLATFORMS]
        if invalid:
            raise ValueError(f"Unsupported platforms: {', '.join(invalid)}")
        if not cleaned:
            raise ValueError("Select at least one platform")
        return cleaned

    @field_validator("max_clip_s")
    @classmethod
    def valid_range(cls, value: int, info: Any) -> int:
        minimum = info.data.get("min_clip_s", 15)
        if value < minimum:
            raise ValueError("max_clip_s must be greater than or equal to min_clip_s")
        return value


class TranscriptRead(BaseModel):
    id: str
    asset_id: str
    language: str
    text: str
    segments_json: list[dict[str, Any]]
    provider: str


class SummaryRead(BaseModel):
    tldr: str
    bullets: list[str]
    chapters: list[dict[str, Any]]
    quotes: list[dict[str, Any]]


class InsightRead(BaseModel):
    report: dict[str, Any]


class UsageRead(BaseModel):
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int
    cost_usd: float
    asr_cost_usd: float
    total_cost_usd: float
    budget_usd: float
    remaining_usd: float
    credits_remaining_usd: float
    calls: int


# ── API: clips and copy ─────────────────────────────────────────────────────


class CopyVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    clip_id: str
    platform: str
    caption: str
    hooks: list[str] = Field(default_factory=list)
    hashtags: list[str]
    cta: str
    version: int


class ClipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    asset_id: str
    start: float
    end: float
    title: str
    hook: str
    source_quote: str = ""
    score: float
    rationale: str
    status: str
    render_path: str | None
    srt_path: str | None
    thumbnail_path: str | None
    risk_flags_json: list[str]
    copy_variants: list[CopyVariantRead] = Field(default_factory=list)
    media_url: str | None = None
    thumbnail_url: str | None = None
    srt_url: str | None = None


class CopyVariantUpdate(BaseModel):
    platform: str
    caption: str
    hooks: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    cta: str = ""


class ClipUpdate(BaseModel):
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    hook: str | None = None
    variants: list[CopyVariantUpdate] = Field(default_factory=list)


class ClipRegenerateRequest(BaseModel):
    kind: Literal["copy", "clip"] = "copy"
    platform: str | None = None
    feedback: str = ""


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    brand_profile_id: str | None
    status: str
    error: str | None
    brand_profile: BrandProfileRead | None = None
    assets: list[MediaAssetRead] = Field(default_factory=list)
    clips: list[ClipRead] = Field(default_factory=list)
    latest_job: JobRead | None = None


class ProjectListItem(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: str
    brand_profile_id: str | None
    duration_s: float = 0.0
    clip_count: int = 0
    thumbnail_url: str | None = None


# ── Structured model output schemas ────────────────────────────────────────


class UnderstandSegment(BaseModel):
    start: float
    end: float
    topic: str
    summary: str
    sentiment: Literal["positive", "neutral", "negative", "mixed"] = "neutral"
    energy_score: float = Field(ge=0, le=1)
    speaker_intent: str = ""
    quotable: bool = False


class UnderstandOutput(BaseModel):
    segments: list[UnderstandSegment]


class ClipProposal(BaseModel):
    start: float
    end: float
    title: str
    hook: str
    score: float = Field(ge=0, le=100)
    rationale: str
    quote: str = ""
    risk_flags: list[str] = Field(default_factory=list)


class ClipSelectionOutput(BaseModel):
    clips: list[ClipProposal]


class CritiqueItem(BaseModel):
    clip_index: int
    verdict: Literal["pass", "revise", "reject"]
    notes: str
    fixes: list[str] = Field(default_factory=list)


class CritiqueOutput(BaseModel):
    clips: list[CritiqueItem]


class CopyOutput(BaseModel):
    caption: str
    hooks: list[str]
    hashtags: list[str]
    cta: str


class SummaryChapter(BaseModel):
    start: float
    title: str
    summary: str = ""


class SummaryQuote(BaseModel):
    start: float
    text: str


class SummaryOutput(BaseModel):
    tldr: str
    bullets: list[str]
    chapters: list[SummaryChapter]
    quotes: list[SummaryQuote]


class InsightScores(BaseModel):
    hook_strength: int = Field(ge=0, le=100)
    pacing: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    emotional_peaks: int = Field(ge=0, le=100)


class InsightClip(BaseModel):
    clip_index: int
    scores: InsightScores
    predicted_performance: Literal["low", "medium", "high"]
    reasoning: str
    improvements: list[str]


class InsightOutput(BaseModel):
    headline: str
    summary: str
    overall: InsightScores
    predicted_performance: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"] = "medium"
    improvements: list[str]
    clips: list[InsightClip]
