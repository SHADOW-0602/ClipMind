from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_session
from ..models import BrandProfile, Clip, CopyVariant, Job, MediaAsset, Project, Transcript
from ..pipeline.generate_copy import generate_copy_for_clips
from ..pipeline.render import render_clip
from ..pipeline.select_clips import _best_quote, _hook_from, generate_candidates
from ..schemas import (
    PLATFORMS,
    ClipRead,
    ClipRegenerateRequest,
    ClipUpdate,
)
from ..services.storage import resolve_inside_data
from ..utils.media import MediaError
from .serializers import clip_read

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clips", tags=["clips"])


def _clear_render(clip: Clip) -> None:
    for stored in (clip.render_path, clip.srt_path, clip.thumbnail_path):
        if not stored:
            continue
        try:
            path = resolve_inside_data(stored)
            if path:
                path.unlink(missing_ok=True)
        except ValueError:
            pass
    clip.render_path = None
    clip.srt_path = None
    clip.thumbnail_path = None


def _brand_for_project(session: Session, project: Project) -> BrandProfile | None:
    return session.get(BrandProfile, project.brand_profile_id) if project.brand_profile_id else None


def _check_banned(brand: BrandProfile | None, texts: list[str]) -> None:
    if not brand:
        return
    joined = "\n".join(texts)
    violations = [
        word
        for word in brand.banned_words
        if word and re.search(rf"(?<!\w){re.escape(word)}(?!\w)", joined, re.IGNORECASE)
    ]
    if violations:
        raise HTTPException(
            status_code=422,
            detail=f"Brand check failed. Remove banned words: {', '.join(violations)}",
        )


@router.get("/{clip_id}", response_model=ClipRead)
def get_clip(clip_id: str, session: Session = Depends(get_session)) -> ClipRead:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip_read(session, clip)


@router.patch("/{clip_id}", response_model=ClipRead)
def update_clip(
    clip_id: str,
    payload: ClipUpdate,
    session: Session = Depends(get_session),
) -> ClipRead:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    project = session.get(Project, clip.project_id)
    asset = session.get(MediaAsset, clip.asset_id)
    if not project or not asset:
        raise HTTPException(status_code=404, detail="Project or media not found")
    brand = _brand_for_project(session, project)

    start = payload.start if payload.start is not None else clip.start
    end = payload.end if payload.end is not None else clip.end
    if end <= start:
        raise HTTPException(status_code=422, detail="Clip end must be after start")
    if end - start < 8:
        raise HTTPException(status_code=422, detail="Clip must be at least 8 seconds")
    if end > asset.duration_s + 0.1:
        raise HTTPException(
            status_code=422, detail=f"Clip end exceeds media duration ({asset.duration_s:.1f}s)"
        )
    trim_changed = abs(start - clip.start) > 0.01 or abs(end - clip.end) > 0.01
    check_texts = []
    if payload.title is not None:
        check_texts.append(payload.title)
    for variant in payload.variants:
        if variant.platform not in PLATFORMS:
            raise HTTPException(status_code=422, detail=f"Unsupported platform: {variant.platform}")
        check_texts.extend([variant.caption, variant.cta, *variant.hashtags])
    _check_banned(brand, check_texts)

    if payload.title is not None:
        clip.title = payload.title.strip()
    if payload.hook is not None:
        clip.hook = payload.hook.strip()
    if trim_changed:
        clip.start = round(start, 2)
        clip.end = round(end, 2)
        _clear_render(clip)
        clip.status = "selected"

    for variant in payload.variants:
        existing = session.exec(
            select(CopyVariant).where(
                CopyVariant.clip_id == clip.id, CopyVariant.platform == variant.platform
            )
        ).first()
        if existing:
            existing.caption = variant.caption.strip()
            existing.hooks = variant.hooks
            existing.hashtags = variant.hashtags
            existing.cta = variant.cta
            existing.version += 1
            session.add(existing)
        else:
            session.add(
                CopyVariant(
                    clip_id=clip.id,
                    platform=variant.platform,
                    caption=variant.caption.strip(),
                    hooks=variant.hooks,
                    hashtags=variant.hashtags,
                    cta=variant.cta,
                )
            )
    clip.updated_at = datetime.now(UTC)
    project.updated_at = datetime.now(UTC)
    session.add(clip)
    session.add(project)
    session.commit()
    session.refresh(clip)
    return clip_read(session, clip)


@router.post("/{clip_id}/regenerate", response_model=ClipRead)
async def regenerate_clip(
    clip_id: str,
    payload: ClipRegenerateRequest,
    session: Session = Depends(get_session),
) -> ClipRead:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    project = session.get(Project, clip.project_id)
    asset = session.get(MediaAsset, clip.asset_id)
    transcript = session.exec(select(Transcript).where(Transcript.asset_id == clip.asset_id)).first()
    if not project or not asset or not transcript:
        raise HTTPException(status_code=404, detail="Clip context is incomplete")
    brand = _brand_for_project(session, project)
    if payload.platform and payload.platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail=f"Unsupported platform: {payload.platform}")

    if payload.kind == "clip":
        other_clips = session.exec(
            select(Clip).where(Clip.project_id == project.id, Clip.id != clip.id)
        ).all()
        latest_job = session.exec(
            select(Job).where(Job.project_id == project.id).order_by(Job.created_at.desc())
        ).first()
        options = (latest_job.options_json if latest_job else {}) or {}
        min_s = int(options.get("min_clip_s", get_settings().min_clip_s))
        max_s = int(options.get("max_clip_s", get_settings().max_clip_s))
        candidates = generate_candidates(transcript, min_s=min_s, max_s=max_s, limit=40)
        feedback_words = set(re.findall(r"[a-z]{4,}", payload.feedback.lower()))
        viable = []
        for candidate in candidates:
            if candidate.start < clip.end - 1 and candidate.end > clip.start + 1:
                continue
            if any(
                candidate.start < other.end - 1 and candidate.end > other.start + 1
                for other in other_clips
            ):
                continue
            bonus = len(feedback_words & set(re.findall(r"[a-z]{4,}", candidate.text.lower()))) * 2
            viable.append((candidate.score + bonus, candidate))
        if not viable:
            raise HTTPException(status_code=409, detail="No alternate non-overlapping moment is available")
        _, candidate = max(viable, key=lambda item: item[0])
        clip.start = candidate.start
        clip.end = candidate.end
        clip.title = candidate.title
        clip.hook = _hook_from(candidate.text)
        clip.source_quote = _best_quote(candidate.text)
        clip.score = candidate.score
        clip.rationale = "Re-picked from a different transcript-grounded moment using your feedback."
        clip.risk_flags_json = candidate.risk_flags
        clip.status = "selected"
        _clear_render(clip)
        session.add(clip)
        session.commit()

    platforms = [payload.platform] if payload.platform else list(PLATFORMS)
    await generate_copy_for_clips(
        session,
        project.id,
        [clip],
        platforms,
        brand,
        feedback=payload.feedback,
        only_clip_id=clip.id,
    )
    session.refresh(clip)
    return clip_read(session, clip)


@router.post("/{clip_id}/render", response_model=ClipRead)
async def render_clip_endpoint(clip_id: str, session: Session = Depends(get_session)) -> ClipRead:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    try:
        clip = await asyncio.to_thread(render_clip, session, clip, force=True)
    except MediaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Render endpoint failed")
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc
    return clip_read(session, clip)


@router.delete("/{clip_id}")
def delete_clip(clip_id: str, session: Session = Depends(get_session)) -> dict:
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    for variant in session.exec(select(CopyVariant).where(CopyVariant.clip_id == clip.id)).all():
        session.delete(variant)
    _clear_render(clip)
    session.delete(clip)
    session.commit()
    return {"deleted": True, "clip_id": clip_id}
