from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select
from starlette.background import BackgroundTask

from ..config import get_settings
from ..db import get_session
from ..models import Clip, CopyVariant, InsightReport, Project, Summary
from ..services.storage import resolve_inside_data, sanitize_filename
from ..services.transcripts import timestamp_label

router = APIRouter(prefix="/api/projects", tags=["export"])


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "clipmind"


def _summary_markdown(project: Project, summary: Summary | None, clips: list[Clip]) -> str:
    lines = [f"# {project.name}", ""]
    if summary:
        lines.extend(["## TL;DR", "", summary.tldr, "", "## Key takeaways", ""])
        lines.extend(f"- {bullet}" for bullet in summary.bullets_json)
        lines.extend(["", "## Chapters", ""])
        for chapter in summary.chapters_json:
            lines.append(
                f"- **{timestamp_label(float(chapter.get('start', 0)))}** — {chapter.get('title', '')}. "
                f"{chapter.get('summary', '')}"
            )
        lines.extend(["", "## Key quotes", ""])
        for quote in summary.quotes_json:
            lines.append(
                f"> {quote.get('text', '')}\n\n— {timestamp_label(float(quote.get('start', 0)))}"
            )
    lines.extend(["", "## Clips", ""])
    for clip in clips:
        lines.append(
            f"- **{clip.title}** ({timestamp_label(clip.start)}–{timestamp_label(clip.end)}, score {clip.score:.0f})"
        )
        lines.append(f"  - Hook: {clip.hook}")
    lines.extend(
        [
            "",
            "---",
            "Generated with ClipMind. Engagement scores are modeled estimates, not guarantees.",
        ]
    )
    return "\n".join(lines)


@router.get("/{project_id}/export")
def export_project(project_id: str, session: Session = Depends(get_session)) -> FileResponse:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    clips = session.exec(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.start)
    ).all()
    variants = session.exec(
        select(CopyVariant).where(
            CopyVariant.clip_id.in_([clip.id for clip in clips])  # type: ignore[attr-defined]
        )
    ).all() if clips else []
    summary = session.exec(select(Summary).where(Summary.project_id == project_id)).first()
    insight = session.exec(select(InsightReport).where(InsightReport.project_id == project_id)).first()
    variants_by_clip: dict[str, list[CopyVariant]] = {}
    for variant in variants:
        variants_by_clip.setdefault(variant.clip_id, []).append(variant)

    settings = get_settings()
    settings.ensure_dirs()
    temp = tempfile.NamedTemporaryFile(
        prefix=f"clipmind-{_slug(project.name)}-", suffix=".zip", dir=settings.data_dir, delete=False
    )
    temp.close()
    zip_path = Path(temp.name)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for index, clip in enumerate(clips, start=1):
                prefix = f"{index:02d}-{_slug(clip.title)}"
                if clip.render_path:
                    media = resolve_inside_data(clip.render_path)
                    if media and media.exists():
                        archive.write(media, f"clips/{prefix}.mp4")
                if clip.srt_path:
                    srt = resolve_inside_data(clip.srt_path)
                    if srt and srt.exists():
                        archive.write(srt, f"captions/{prefix}.srt")
                if clip.thumbnail_path:
                    thumb = resolve_inside_data(clip.thumbnail_path)
                    if thumb and thumb.exists():
                        archive.write(thumb, f"thumbnails/{prefix}.jpg")
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["clip", "start_s", "end_s", "score", "platform", "hook", "caption", "hashtags", "cta"])
            for clip in clips:
                for variant in variants_by_clip.get(clip.id, []):
                    writer.writerow(
                        [
                            clip.title,
                            f"{clip.start:.2f}",
                            f"{clip.end:.2f}",
                            f"{clip.score:.1f}",
                            variant.platform,
                            clip.hook,
                            variant.caption,
                            " ".join(variant.hashtags),
                            variant.cta,
                        ]
                    )
            archive.writestr("copy.csv", buffer.getvalue())
            archive.writestr("summary.md", _summary_markdown(project, summary, clips))
            if insight:
                archive.writestr("insights.json", json.dumps(insight.report_json, indent=2, ensure_ascii=False))
            manifest = {
                "project": project.name,
                "project_id": project.id,
                "created_at": project.created_at.isoformat(),
                "clip_count": len(clips),
                "platforms": sorted({variant.platform for variant in variants}),
                "note": "Engagement scores are modeled estimates, not platform guarantees.",
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            archive.writestr(
                "README.txt",
                (
                    "ClipMind export\n"
                    "================\n\n"
                    "clips/ contains 9:16 MP4s with burned-in captions.\n"
                    "captions/ contains matching SRT files.\n"
                    "copy.csv contains platform-specific captions and hashtags.\n"
                    "summary.md contains the TL;DR, chapters, and verified quotes.\n"
                    "insights.json contains the full engagement report.\n\n"
                    "Review all clips before publishing. AI-generated performance predictions are estimates.\n"
                ),
            )
    except Exception as exc:  # noqa: BLE001
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not build export: {exc}") from exc

    filename = f"{sanitize_filename(_slug(project.name))}-clipmind.zip"

    def cleanup() -> None:
        zip_path.unlink(missing_ok=True)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(cleanup),
    )
