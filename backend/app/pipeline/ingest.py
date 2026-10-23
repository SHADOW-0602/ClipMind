from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from ..config import get_settings
from ..models import MediaAsset, Project
from ..services.storage import (
    project_dir,
    relative_path,
    resolve_path,
    sanitize_filename,
    sha256_file,
)
from ..services.transcripts import build_segments_from_text
from ..utils.media import (
    MediaError,
    create_placeholder_video,
    extract_audio,
    extract_keyframes,
    media_metadata,
    normalize_audio,
    normalize_video,
)

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".txt", ".md", ".srt", ".vtt", ".json"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"}


def kind_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    return "video"


def register_asset(
    session: Session,
    *,
    project_id: str,
    path: Path,
    original_filename: str,
    kind_hint: str | None = None,
) -> MediaAsset:
    """Register an uploaded file. Heavy normalization runs in the ingest stage."""
    settings = get_settings()
    kind = kind_from_filename(original_filename)
    if kind_hint in {"video", "audio", "text"}:
        kind = kind_hint

    checksum = sha256_file(path)
    size = path.stat().st_size
    if kind == "text":
        raw = path.read_text(encoding="utf-8", errors="replace")
        if not raw.strip():
            raise MediaError("The uploaded text file is empty")
        sentences = build_segments_from_text(raw)
        duration = max(5.0, sentences[-1]["end"] if sentences else 5.0)
        width = height = 0
        fps = 0.0
    else:
        metadata = media_metadata(path)
        duration = float(metadata["duration_s"])
        if duration <= 0:
            raise MediaError("Could not read a duration from this media file")
        if metadata["has_video"]:
            kind = "video"
            width, height = int(metadata["width"]), int(metadata["height"])
            fps = float(metadata["fps"])
        elif metadata["has_audio"]:
            kind = "audio"
            width = height = 0
            fps = 0.0
        else:
            raise MediaError("The file has no playable audio or video stream")

    if duration > settings.max_duration_s:
        raise MediaError(
            f"Media is {duration / 60:.1f} minutes; the current limit is "
            f"{settings.max_duration_s / 60:.0f} minutes."
        )

    asset = MediaAsset(
        project_id=project_id,
        kind=kind,
        original_filename=sanitize_filename(original_filename),
        path=relative_path(path),
        duration_s=round(duration, 3),
        width=width,
        height=height,
        fps=fps,
        size_bytes=size,
        checksum=checksum,
        status="uploaded",
    )
    session.add(asset)
    project = session.get(Project, project_id)
    if project:
        project.status = "uploaded"
        project.error = None
        project.updated_at = datetime.now(UTC)
        session.add(project)
    session.commit()
    session.refresh(asset)
    return asset


def _existing_asset(session: Session, asset_id: str) -> MediaAsset:
    asset = session.get(MediaAsset, asset_id)
    if not asset:
        raise MediaError("Media asset not found")
    return asset


def ingest_asset(session: Session, asset_id: str, *, force: bool = False) -> MediaAsset:
    settings = get_settings()
    asset = _existing_asset(session, asset_id)
    if asset.status == "ready" and not force and (asset.kind == "text" or asset.normalized_path):
        return asset

    source = resolve_path(asset.path)
    if not source or not source.exists():
        raise MediaError("Uploaded source file is missing from storage")
    out_dir = project_dir("processed", asset.project_id)
    if asset.kind == "text":
        asset.status = "ready"
        if not asset.normalized_path:
            placeholder = out_dir / "text-visual.mp4"
            if not placeholder.exists():
                create_placeholder_video(
                    placeholder,
                    max(5.0, asset.duration_s),
                    title=asset.original_filename.rsplit(".", 1)[0],
                )
            asset.normalized_path = relative_path(placeholder)
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return asset

    if asset.kind == "video":
        normalized = out_dir / "source.mp4"
        if force or not normalized.exists():
            logger.info("Normalizing video %s", source)
            normalize_video(source, normalized)
        audio = out_dir / "audio-16k.wav"
        if force or not audio.exists():
            extract_audio(normalized, audio)
        frames_dir = out_dir / "frames"
        frames = extract_keyframes(normalized, frames_dir, asset.duration_s, max_frames=8)
        asset.frames_json = [
            {
                "timestamp": frame["timestamp"],
                "path": relative_path(frames_dir / frame["path"]),
            }
            for frame in frames
        ]
        asset.normalized_path = relative_path(normalized)
        asset.audio_path = relative_path(audio)
    elif asset.kind == "audio":
        normalized = out_dir / "source.m4a"
        if force or not normalized.exists():
            logger.info("Normalizing audio %s", source)
            normalize_audio(source, normalized)
        audio = out_dir / "audio-16k.wav"
        if force or not audio.exists():
            extract_audio(normalized, audio)
        asset.normalized_path = relative_path(normalized)
        asset.audio_path = relative_path(audio)
        asset.frames_json = []

    asset.status = "ready"
    session.add(asset)
    session.commit()
    session.refresh(asset)
    settings.ensure_dirs()
    return asset


def asset_text(asset: MediaAsset) -> str:
    """Text input is stored originally as UTF-8; use it directly for synthetic timestamps."""
    if asset.kind != "text":
        return ""
    path = resolve_path(asset.path)
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def find_project_asset(session: Session, project_id: str) -> MediaAsset | None:
    return session.exec(
        select(MediaAsset).where(MediaAsset.project_id == project_id).order_by(MediaAsset.created_at.desc())
    ).first()
