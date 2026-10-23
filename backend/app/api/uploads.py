from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, delete, select

from ..config import get_settings
from ..db import get_session
from ..models import (
    Clip,
    CopyVariant,
    InsightReport,
    MediaAsset,
    Project,
    Summary,
    TopicSegment,
    Transcript,
)
from ..pipeline.ingest import register_asset
from ..pipeline.orchestrator import active_job_for_project
from ..schemas import MediaAssetRead
from ..services.storage import project_dir, sanitize_filename
from ..utils.media import MediaError
from .serializers import asset_read

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["uploads"])


def _cleanup_previous_media(session: Session, project_id: str, keep_asset_id: str) -> None:
    clips = session.exec(select(Clip).where(Clip.project_id == project_id)).all()
    for clip in clips:
        session.exec(delete(CopyVariant).where(CopyVariant.clip_id == clip.id))
        for stored in (clip.render_path, clip.srt_path, clip.thumbnail_path):
            if stored:
                from ..services.storage import resolve_inside_data

                try:
                    path = resolve_inside_data(stored)
                    if path:
                        path.unlink(missing_ok=True)
                except ValueError:
                    pass
    session.exec(delete(Clip).where(Clip.project_id == project_id))
    session.exec(delete(Summary).where(Summary.project_id == project_id))
    session.exec(delete(InsightReport).where(InsightReport.project_id == project_id))
    old_assets = session.exec(select(MediaAsset).where(MediaAsset.project_id == project_id)).all()
    for asset in old_assets:
        if asset.id == keep_asset_id:
            continue
        session.exec(delete(TopicSegment).where(TopicSegment.asset_id == asset.id))
        session.exec(delete(Transcript).where(Transcript.asset_id == asset.id))
        if asset.path and not asset.path.startswith(("http://", "https://")):
            try:
                from ..services.storage import resolve_inside_data

                old_source = resolve_inside_data(asset.path)
                if old_source and old_source.exists():
                    old_source.unlink(missing_ok=True)
            except (ValueError, OSError):
                logger.warning("Could not remove replaced upload %s", asset.path)
        session.delete(asset)
    session.commit()
    # Remove old generated artifacts but leave the newly uploaded file untouched.
    import shutil

    for bucket in ("processed", "renders"):
        directory = get_settings().data_dir / bucket / project_id
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)


@router.post("/{project_id}/upload", response_model=MediaAssetRead, status_code=201)
async def upload_media(
    project_id: str,
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    rights_attested: bool = Form(default=False),
    kind_hint: str | None = Form(default=None),
    session: Session = Depends(get_session),
) -> MediaAssetRead:
    settings = get_settings()
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not rights_attested:
        raise HTTPException(
            status_code=400,
            detail="You must confirm you have the rights to upload and process this content",
        )
    if active_job_for_project(project_id):
        raise HTTPException(status_code=409, detail="Wait for the active job before replacing media")
    if not file and not (text and text.strip()):
        raise HTTPException(status_code=400, detail="Provide a file or pasted text")

    upload_dir = project_dir("uploads", project_id)
    stored_path: Path | None = None
    try:
        if text and text.strip():
            if len(text) > 2_000_000:
                raise HTTPException(status_code=413, detail="Pasted text is too long (2M character limit)")
            filename = f"pasted-text-{uuid4().hex[:8]}.txt"
            stored_path = upload_dir / filename
            stored_path.write_text(text.strip(), encoding="utf-8")
            original_name = "pasted-transcript.txt"
        else:
            assert file is not None
            original_name = sanitize_filename(file.filename or "upload")
            suffix = Path(original_name).suffix.lower() or ".bin"
            if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
                suffix = ".bin"
            max_bytes = settings.max_upload_mb * 1024 * 1024
            stored_path = upload_dir / f"{uuid4().hex[:10]}-{Path(original_name).stem[:60]}{suffix}"
            size = 0
            with stored_path.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        handle.close()
                        stored_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds the {settings.max_upload_mb} MB upload limit",
                        )
                    handle.write(chunk)
            await file.close()
            if size == 0:
                stored_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="The uploaded file is empty")
        asset = register_asset(
            session,
            project_id=project_id,
            path=stored_path,
            original_filename=original_name,
            kind_hint=kind_hint,
        )
        _cleanup_previous_media(session, project_id, keep_asset_id=asset.id)
        project = session.get(Project, project_id)
        if project:
            project.status = "uploaded"
            project.error = None
            project.updated_at = datetime.now(UTC)
            session.add(project)
            session.commit()
        return asset_read(asset)
    except HTTPException:
        if stored_path and stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise
    except MediaError as exc:
        if stored_path and stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Upload failed")
        if stored_path and stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc


@router.get("/{project_id}/upload/limits")
def upload_limits() -> dict:
    settings = get_settings()
    return {
        "max_upload_mb": settings.max_upload_mb,
        "max_duration_s": settings.max_duration_s,
        "accepted": "video, audio, .txt, .md, .srt, .vtt",
    }
